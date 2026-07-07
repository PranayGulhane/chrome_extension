import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import (
    CreateInviteCodeRequest,
    InviteCodeResponse,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from auth.service import auth_service
from auth.service.auth_service import (
    AccessExpiredError,
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidInviteCodeError,
    InviteCodeAlreadyUsedError,
    InviteCodeNotFoundError,
    UserNotFoundError,
)
from core.database import get_db
from core.dependencies import AdminUser, CurrentUser
from core.security import REFRESH_TOKEN_COOKIE, clear_auth_cookies, set_auth_cookies

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, response: Response, db: DbSession) -> TokenResponse:
    try:
        _, tokens = await auth_service.register_user(db, payload)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from exc
    except InvalidInviteCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invite code is invalid or already used"
        ) from exc
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response, db: DbSession) -> TokenResponse:
    try:
        _, tokens = await auth_service.authenticate_user(db, payload.email, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password") from exc
    except AccountDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your access has been revoked — contact the admin",
        ) from exc
    except AccessExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your access period has expired — contact the admin to extend it",
        ) from exc
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request, response: Response, db: DbSession, payload: RefreshRequest | None = None
) -> TokenResponse:
    # Extension clients send the refresh token in the body (no access to their own cookie jar
    # semantics needed, since they don't use cookies at all). The web app can't put its httpOnly
    # refresh cookie into a JS-constructed body — it can't read it — so it calls this with no body
    # and we fall back to the cookie.
    refresh_token = payload.refresh_token if payload else request.cookies.get(REFRESH_TOKEN_COOKIE)
    if refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        tokens = await auth_service.refresh_tokens(db, refresh_token)
    except (InvalidCredentialsError, UserNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    # No auth required: an already-expired session should still be able to clear its own cookies.
    # No-op for extension clients (they don't have these cookies to begin with) but required for
    # the web app — JS can't clear an httpOnly cookie itself, only the server can.
    clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/invite-codes", response_model=InviteCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_invite_code(
    admin: AdminUser, db: DbSession, payload: CreateInviteCodeRequest | None = None
) -> InviteCodeResponse:
    invite = await auth_service.create_invite_code(db, admin.id, payload.expires_at if payload else None)
    return InviteCodeResponse.model_validate(invite)


@router.get("/invite-codes", response_model=list[InviteCodeResponse])
async def list_invite_codes(admin: AdminUser, db: DbSession) -> list[InviteCodeResponse]:
    return await auth_service.list_invite_codes_with_users(db)


@router.post("/invite-codes/{invite_id}/revoke", response_model=InviteCodeResponse)
async def revoke_invite_code(invite_id: uuid.UUID, admin: AdminUser, db: DbSession) -> InviteCodeResponse:
    try:
        invite = await auth_service.revoke_invite_code(db, invite_id)
    except InviteCodeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found") from exc
    except InviteCodeAlreadyUsedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This invite code has already been used"
        ) from exc
    return InviteCodeResponse.model_validate(invite)
