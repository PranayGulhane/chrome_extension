import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserResponse
from auth.service import auth_service
from auth.service.auth_service import UserNotFoundError
from core.database import get_db
from core.dependencies import AdminUser
from metrics.schemas import AdminOverviewResponse, AdminUserAccessUpdateRequest, AdminUserRow
from metrics.service import admin_metrics_service

router = APIRouter(prefix="/admin", tags=["admin"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(admin: AdminUser, db: DbSession) -> AdminOverviewResponse:
    return await admin_metrics_service.get_admin_overview(db)


@router.get("/users", response_model=list[AdminUserRow])
async def list_admin_users(admin: AdminUser, db: DbSession) -> list[AdminUserRow]:
    return await admin_metrics_service.list_admin_users(db)


@router.post("/users/{user_id}/revoke-access", response_model=UserResponse)
async def revoke_user_access(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> UserResponse:
    try:
        user = await auth_service.revoke_user_access(db, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/restore-access", response_model=UserResponse)
async def restore_user_access(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> UserResponse:
    try:
        user = await auth_service.restore_user_access(db, user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/access", response_model=UserResponse)
async def update_user_access(
    user_id: uuid.UUID, payload: AdminUserAccessUpdateRequest, admin: AdminUser, db: DbSession
) -> UserResponse:
    try:
        user = await auth_service.update_user_access(db, user_id, payload.access_expires_at, payload.admin_notes)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
    return UserResponse.model_validate(user)
