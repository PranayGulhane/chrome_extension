from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import CurrentUser
from metrics.schemas import UserMetricsResponse
from metrics.service import metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/me", response_model=UserMetricsResponse)
async def get_my_metrics(user: CurrentUser, db: DbSession) -> UserMetricsResponse:
    return await metrics_service.get_user_metrics(db, user.id)
