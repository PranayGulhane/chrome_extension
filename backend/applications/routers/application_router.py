import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from applications.schemas import (
    ApplicationResponse,
    ApplicationUpdateRequest,
    DraftEmailRequest,
    DuplicateCheckResponse,
    PostExtractionRequest,
    PostExtractionResponse,
)
from applications.service import application_service
from applications.service.application_service import (
    ApplicationNotFoundError,
    EmailDraftingError,
    JDParsingError,
    NoDraftError,
    NoRecipientError,
    NoResumeError,
    NotDiscardableError,
    NotYetSentError,
    WrongOutreachTypeError,
)
from core.database import SerializationConflictError, get_db, with_serialization_retry
from core.dependencies import CurrentUser
from gmail.service.gmail_service import GmailApiError, GmailNotConnectedError
from profiles.service.profile_service import ProfileNotFoundError

router = APIRouter(prefix="/applications", tags=["applications"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

_CONFLICT_DETAIL = "This application was updated by another request at the same time — please retry."


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(user: CurrentUser, db: DbSession) -> list[ApplicationResponse]:
    applications = await application_service.list_applications(db, user.id)
    return [ApplicationResponse.model_validate(application) for application in applications]


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationResponse:
    try:
        application = await application_service.get_application(db, user.id, application_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    return ApplicationResponse.model_validate(application)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    """Feature 11 — narrow "discard" action for the duplicate-contact warning, not a general
    delete: application_service.delete_application only permits it while status=extracted."""
    try:
        await application_service.delete_application(db, user.id, application_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    except NotDiscardableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application already has a draft or was sent — it can't be discarded.",
        ) from exc


@router.post("/extract", response_model=PostExtractionResponse, status_code=status.HTTP_201_CREATED)
async def extract_post(
    payload: PostExtractionRequest, user: CurrentUser, db: DbSession
) -> PostExtractionResponse:
    try:
        application, parsed = await application_service.create_from_extraction(db, user.id, payload)
    except JDParsingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
    return PostExtractionResponse(
        application=ApplicationResponse.model_validate(application), is_hiring=parsed.is_hiring
    )


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: uuid.UUID, payload: ApplicationUpdateRequest, user: CurrentUser, db: DbSession
) -> ApplicationResponse:
    try:
        application = await with_serialization_retry(
            db,
            application_service.update_application,
            db,
            user.id,
            application_id,
            email=payload.parsed_email,
            post_url=payload.post_url,
            drafted_email=payload.drafted_email,
            outreach_type=payload.outreach_type,
            outreach_note=payload.outreach_note,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
    return ApplicationResponse.model_validate(application)


@router.post("/{application_id}/draft", response_model=ApplicationResponse)
async def draft_application_email(
    application_id: uuid.UUID, payload: DraftEmailRequest, user: CurrentUser, db: DbSession
) -> ApplicationResponse:
    try:
        application = await application_service.create_draft(db, user.id, application_id, payload.profile_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except EmailDraftingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
    return ApplicationResponse.model_validate(application)


@router.post("/{application_id}/send", response_model=ApplicationResponse)
async def send_application_email(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationResponse:
    try:
        application = await application_service.send_application_email(db, user.id, application_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    except NoDraftError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except NoRecipientError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except NoResumeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except GmailNotConnectedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GmailApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
    return ApplicationResponse.model_validate(application)


@router.get("/{application_id}/duplicate-check", response_model=DuplicateCheckResponse)
async def check_duplicate_contact(
    application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> DuplicateCheckResponse:
    try:
        result = await application_service.check_duplicate_contact(db, user.id, application_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    if result is None:
        return DuplicateCheckResponse(is_duplicate=False)
    existing, matched_via = result
    return DuplicateCheckResponse(
        is_duplicate=True,
        matched_via=matched_via,
        existing_application=ApplicationResponse.model_validate(existing),
    )


@router.post("/{application_id}/mark-sent", response_model=ApplicationResponse)
async def mark_application_sent(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationResponse:
    try:
        application = await application_service.mark_sent_manually(db, user.id, application_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    except WrongOutreachTypeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
    return ApplicationResponse.model_validate(application)


@router.post("/{application_id}/mark-replied", response_model=ApplicationResponse)
async def mark_application_replied(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationResponse:
    try:
        application = await application_service.mark_replied(db, user.id, application_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    except NotYetSentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
    return ApplicationResponse.model_validate(application)


@router.post("/{application_id}/archive", response_model=ApplicationResponse)
async def archive_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationResponse:
    try:
        application = await application_service.archive_application(db, user.id, application_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
    return ApplicationResponse.model_validate(application)


@router.post("/{application_id}/unarchive", response_model=ApplicationResponse)
async def unarchive_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationResponse:
    try:
        application = await application_service.unarchive_application(db, user.id, application_id)
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
    return ApplicationResponse.model_validate(application)
