import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from agents.resume_parser.schemas import ResumeUploadResult
from core.database import SerializationConflictError, get_db, with_serialization_retry
from core.dependencies import CurrentUser
from profiles.schemas import (
    CloneProfileRequest,
    ProfileResponse,
    ProfileSummaryResponse,
    ProfileWriteRequest,
    ResumeUploadResponse,
)
from profiles.service import profile_service, resume_upload_service
from profiles.service.profile_service import ProfileNotFoundError
from profiles.service.resume_upload_service import InvalidResumeFileError, ResumeParsingError

router = APIRouter(prefix="/profiles", tags=["profiles"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

_CONFLICT_DETAIL = "This profile was updated by another request at the same time — please retry."


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(payload: ProfileWriteRequest, user: CurrentUser, db: DbSession) -> ProfileResponse:
    try:
        return await with_serialization_retry(db, profile_service.create_profile, db, user.id, payload)
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.get("", response_model=list[ProfileSummaryResponse])
async def list_profiles(user: CurrentUser, db: DbSession) -> list[ProfileSummaryResponse]:
    profiles = await profile_service.list_profiles(db, user.id)
    return [ProfileSummaryResponse.model_validate(p) for p in profiles]


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProfileResponse:
    try:
        return await profile_service.get_profile(db, user.id, profile_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: uuid.UUID, payload: ProfileWriteRequest, user: CurrentUser, db: DbSession
) -> ProfileResponse:
    try:
        return await with_serialization_retry(db, profile_service.update_profile, db, user.id, profile_id, payload)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    try:
        await with_serialization_retry(db, profile_service.delete_profile, db, user.id, profile_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.post("/{profile_id}/set-default", response_model=ProfileResponse)
async def set_default_profile(profile_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProfileResponse:
    try:
        return await with_serialization_retry(db, profile_service.set_default_profile, db, user.id, profile_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.post("/{profile_id}/clone", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def clone_profile(
    profile_id: uuid.UUID, payload: CloneProfileRequest, user: CurrentUser, db: DbSession
) -> ProfileResponse:
    try:
        return await with_serialization_retry(
            db, profile_service.clone_profile, db, user.id, profile_id, payload.target_job_title
        )
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.post("/{profile_id}/resume", response_model=ResumeUploadResult, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    profile_id: uuid.UUID, user: CurrentUser, db: DbSession, file: UploadFile = File(...)
) -> ResumeUploadResult:
    file_bytes = await file.read()
    try:
        return await resume_upload_service.upload_and_parse_resume(
            db, user.id, profile_id, file.filename or "resume.pdf", file_bytes
        )
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except InvalidResumeFileError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ResumeParsingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.get("/{profile_id}/resume", response_model=ResumeUploadResponse)
async def get_active_resume(profile_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ResumeUploadResponse:
    try:
        resume = await resume_upload_service.get_active_resume(db, user.id, profile_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No resume uploaded for this profile")
    return ResumeUploadResponse.model_validate(resume)
