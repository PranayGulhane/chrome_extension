import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import InviteCode, RoleEnum, User
from auth.schemas import SignupRequest, TokenResponse
from core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


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


def _issue_token_pair(user_id: uuid.UUID) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


async def register_user(db: AsyncSession, payload: SignupRequest) -> tuple[User, TokenResponse]:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise EmailAlreadyRegisteredError(payload.email)

    invite = await db.scalar(
        select(InviteCode).where(InviteCode.code == payload.invite_code).with_for_update()
    )
    if invite is None or invite.is_used:
        raise InvalidInviteCodeError(payload.invite_code)

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=RoleEnum.JOBSEEKER,
    )
    db.add(user)
    await db.flush()  # populate user.id before referencing it from invite

    invite.is_used = True
    invite.used_by = user.id
    invite.used_at = datetime.now(UTC)

    await db.commit()
    return user, _issue_token_pair(user.id)


async def authenticate_user(db: AsyncSession, email: str, password: str) -> tuple[User, TokenResponse]:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError(email)
    if not user.is_active:
        raise InvalidCredentialsError(email)
    return user, _issue_token_pair(user.id)


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenResponse:
    try:
        user_id = decode_token(refresh_token, TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise InvalidCredentialsError("invalid refresh token") from exc

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise UserNotFoundError(str(user_id))

    return _issue_token_pair(user.id)


async def create_invite_code(db: AsyncSession, created_by: uuid.UUID) -> InviteCode:
    invite = InviteCode(code=secrets.token_urlsafe(9), created_by=created_by)
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite
