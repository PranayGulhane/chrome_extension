from typing import Annotated

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import SerializationConflictError, get_db
from core.dependencies import CurrentUser
from gmail.service.gmail_service import GmailApiError, GmailNotConnectedError
from mailbox.schemas import (
    FollowupDraftResponse,
    SendFollowupRequest,
    SentMailPageRequest,
    SentMailPageResponse,
    SentMailRow,
)
from mailbox.service import mailbox_service
from mailbox.service.mailbox_service import FollowupDraftingError, MailboxRowNotFoundError

router = APIRouter(prefix="/mailbox", tags=["mailbox"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

_CONFLICT_DETAIL = "This mailbox row was updated by another request at the same time — please retry."


@router.post("/sent", response_model=SentMailPageResponse)
async def get_sent_mail_page(payload: SentMailPageRequest, user: CurrentUser, db: DbSession) -> SentMailPageResponse:
    try:
        return await mailbox_service.get_sent_mail_page(
            db,
            user.id,
            page_size=payload.page_size,
            page_token=payload.page_token,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except GmailNotConnectedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GmailApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.post("/{gmail_sent_message_id}/followup/draft", response_model=FollowupDraftResponse)
async def draft_followup(gmail_sent_message_id: uuid.UUID, user: CurrentUser, db: DbSession) -> FollowupDraftResponse:
    try:
        return await mailbox_service.draft_followup(db, user.id, gmail_sent_message_id)
    except MailboxRowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox row not found") from exc
    except FollowupDraftingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.post("/{gmail_sent_message_id}/followup/send", response_model=SentMailRow)
async def send_followup(
    gmail_sent_message_id: uuid.UUID, payload: SendFollowupRequest, user: CurrentUser, db: DbSession
) -> SentMailRow:
    try:
        return await mailbox_service.send_followup(
            db, user.id, gmail_sent_message_id, payload.subject, payload.body
        )
    except MailboxRowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox row not found") from exc
    except FollowupDraftingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except GmailNotConnectedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GmailApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.post("/{gmail_sent_message_id}/archive", response_model=SentMailRow)
async def archive_mail_row(gmail_sent_message_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SentMailRow:
    try:
        return await mailbox_service.set_archived(db, user.id, gmail_sent_message_id, True)
    except MailboxRowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox row not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc


@router.post("/{gmail_sent_message_id}/unarchive", response_model=SentMailRow)
async def unarchive_mail_row(gmail_sent_message_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SentMailRow:
    try:
        return await mailbox_service.set_archived(db, user.id, gmail_sent_message_id, False)
    except MailboxRowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox row not found") from exc
    except SerializationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT_DETAIL) from exc
