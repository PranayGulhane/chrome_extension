from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import RoleEnum, User
from core.database import get_db
from core.security import ACCESS_TOKEN_COOKIE, InvalidTokenError, TokenType, decode_token

# HTTPBearer (not OAuth2PasswordBearer) so Swagger's "Authorize" dialog is a plain token-paste box.
# /auth/login takes a JSON body, not OAuth2's form-encoded grant, so OAuth2PasswordBearer's built-in
# login form in Swagger would not work here anyway.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Extension clients send Authorization: Bearer; the web app sends the access_token cookie
    # instead (see core/security.py for why). Either is accepted here.
    token = credentials.credentials if credentials else request.cookies.get(ACCESS_TOKEN_COOKIE)
    if token is None:
        raise credentials_error

    try:
        user_id = decode_token(token, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise credentials_error from exc

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    # Feature 10 — default 30-day access window for new signups (NULL = unlimited, existing users
    # grandfathered). Same enforcement point for both the extension and the Web SPA.
    if user.access_expires_at is not None and user.access_expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your access period has expired — contact the admin to extend it",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
