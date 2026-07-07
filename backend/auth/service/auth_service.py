import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import InviteCode, RoleEnum, User
from auth.schemas import InviteCodeResponse, SignupRequest, TokenResponse
from core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

_DEFAULT_ACCESS_PERIOD_DAYS = 30


class AuthError(Exception):
    """Base class for auth-flow errors the router translates into HTTP responses."""


class EmailAlreadyRegisteredError(AuthError):
    pass


class InvalidInviteCodeError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class UserNotFoundError(AuthError):
    pass


class AccessExpiredError(AuthError):
    pass


class AccountDisabledError(AuthError):
    pass


class InviteCodeNotFoundError(AuthError):
    pass


class InviteCodeAlreadyUsedError(AuthError):
    pass


def _issue_token_pair(user_id: uuid.UUID) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


async def register_user(db: AsyncSession, payload: SignupRequest) -> tuple[User, TokenResponse]:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise EmailAlreadyRegisteredError(payload.email)

    now = datetime.now(UTC)
    invite = await db.scalar(
        select(InviteCode).where(InviteCode.code == payload.invite_code).with_for_update()
    )
    # Feature 10: a code is redeemable only if unused, not manually revoked, and (no expiry or
    # still in the future) — same InvalidInviteCodeError for all three, matching the existing
    # "invalid or already used" message (deliberately vague to avoid leaking *why* a code failed).
    if (
        invite is None
        or invite.is_used
        or invite.revoked_at is not None
        or (invite.expires_at is not None and invite.expires_at < now)
    ):
        raise InvalidInviteCodeError(payload.invite_code)

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=RoleEnum.JOBSEEKER,
        access_expires_at=now + timedelta(days=_DEFAULT_ACCESS_PERIOD_DAYS),
    )
    db.add(user)
    await db.flush()  # populate user.id before referencing it from invite

    invite.is_used = True
    invite.used_by = user.id
    invite.used_at = now
    user.last_login_at = now

    await db.commit()
    return user, _issue_token_pair(user.id)


async def authenticate_user(db: AsyncSession, email: str, password: str) -> tuple[User, TokenResponse]:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError(email)
    # Deliberately distinct from InvalidCredentialsError (unlike the wrong-email/wrong-password
    # case, which stays vague on purpose) — a revoked or expired user should be told exactly why
    # they can't log in, not left guessing whether they mistyped their password.
    if not user.is_active:
        raise AccountDisabledError(email)
    if user.access_expires_at is not None and user.access_expires_at < datetime.now(UTC):
        raise AccessExpiredError(email)

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return user, _issue_token_pair(user.id)


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenResponse:
    try:
        user_id = decode_token(refresh_token, TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise InvalidCredentialsError("invalid refresh token") from exc

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise UserNotFoundError(str(user_id))
    # A user whose access expired mid-session shouldn't be able to silently keep renewing their
    # access token every ~15 min until it naturally lapses — same enforcement as authenticate_user.
    if user.access_expires_at is not None and user.access_expires_at < datetime.now(UTC):
        raise UserNotFoundError(str(user_id))

    return _issue_token_pair(user.id)


async def create_invite_code(
    db: AsyncSession, created_by: uuid.UUID, expires_at: datetime | None = None
) -> InviteCode:
    invite = InviteCode(code=secrets.token_urlsafe(9), created_by=created_by, expires_at=expires_at)
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def revoke_invite_code(db: AsyncSession, invite_id: uuid.UUID) -> InviteCode:
    invite = await db.scalar(select(InviteCode).where(InviteCode.id == invite_id))
    if invite is None:
        raise InviteCodeNotFoundError(str(invite_id))
    if invite.is_used:
        raise InviteCodeAlreadyUsedError(str(invite_id))
    invite.revoked_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(invite)
    return invite


async def list_invite_codes_with_users(db: AsyncSession) -> list[InviteCodeResponse]:
    """Replaces the ad-hoc query that used to live directly in the router — outer-joins User on
    used_by so the admin dashboard can show *who* redeemed a code (the FK already existed, it was
    just never surfaced)."""
    rows = await db.execute(
        select(InviteCode, User.email)
        .outerjoin(User, InviteCode.used_by == User.id)
        .order_by(InviteCode.created_at.desc())
    )
    return [
        InviteCodeResponse.model_validate(invite, from_attributes=True).model_copy(update={"used_by_email": email})
        for invite, email in rows
    ]


async def _get_user_owned(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise UserNotFoundError(str(user_id))
    return user


async def revoke_user_access(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Reuses the existing is_active column — there was previously no endpoint to flip it."""
    user = await _get_user_owned(db, user_id)
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user


async def restore_user_access(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await _get_user_owned(db, user_id)
    user.is_active = True
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_access(
    db: AsyncSession, user_id: uuid.UUID, access_expires_at: datetime | None, admin_notes: str | None
) -> User:
    """Combined action (both fields always set, never a partial patch) — see docs/PROGRESS.md's
    Feature 10 log for why: a generic PATCH would leave "clear the expiry to make it unlimited"
    ambiguous with "field omitted, leave unchanged"."""
    user = await _get_user_owned(db, user_id)
    user.access_expires_at = access_expires_at
    user.admin_notes = admin_notes
    await db.commit()
    await db.refresh(user)
    return user
