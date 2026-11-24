import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_usage.models import AgentUsageLog
from agent_usage.schemas import AgentUsageInfo
from agents.followup_drafter.agent import draft_followup as run_followup_drafter_agent
from agents.followup_drafter.schemas import FollowupDraftContext
from applications.models import Application
from core.database import with_serialization_retry
from gmail.models import GmailCredential
from gmail.service.gmail_service import (
    GmailApiError,  # noqa: F401 - re-exported for router error mapping, same convention as other service modules
    GmailNotConnectedError,
    get_message_metadata,
    get_thread_reply_status,
    get_valid_access_token,
    list_sent_messages_page,
    send_reply,
)
from mailbox.models import GmailSentMessage, MailFollowup
from mailbox.schemas import FollowupDraftResponse, MailboxSummary, SentMailPageResponse, SentMailRow

logger = logging.getLogger(__name__)


class MailboxRowNotFoundError(Exception):
    pass


class FollowupDraftingError(Exception):
    pass


async def _get_owned_row(db: AsyncSession, user_id: uuid.UUID, gmail_sent_message_id: uuid.UUID) -> GmailSentMessage:
    row = await db.scalar(
        select(GmailSentMessage).where(
            GmailSentMessage.id == gmail_sent_message_id, GmailSentMessage.user_id == user_id
        )
    )
    if row is None:
        raise MailboxRowNotFoundError(str(gmail_sent_message_id))
    return row


async def _get_gmail_address(db: AsyncSession, user_id: uuid.UUID) -> str:
    credential = await db.scalar(select(GmailCredential).where(GmailCredential.user_id == user_id))
    if credential is None:
        raise GmailNotConnectedError("Gmail is not connected for this account.")
    return credential.gmail_address


async def _find_matching_application_id(db: AsyncSession, user_id: uuid.UUID, gmail_message_id: str) -> uuid.UUID | None:
    return await db.scalar(
        select(Application.id).where(Application.user_id == user_id, Application.gmail_message_id == gmail_message_id)
    )


async def _insert_sent_message(
    db: AsyncSession,
    user_id: uuid.UUID,
    gmail_message_id: str,
    metadata: dict,
    application_id: uuid.UUID | None,
) -> GmailSentMessage:
    row = GmailSentMessage(
        user_id=user_id,
        gmail_message_id=gmail_message_id,
        gmail_thread_id=metadata["thread_id"],
        subject=metadata["subject"],
        recipient=metadata["recipient"],
        sent_at=metadata["sent_at"],
        application_id=application_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _mark_reply_detected(db: AsyncSession, user_id: uuid.UUID, gmail_sent_message_id: uuid.UUID) -> GmailSentMessage:
    row = await _get_owned_row(db, user_id, gmail_sent_message_id)
    row.reply_detected = True
    row.synced_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def _last_followup_map(db: AsyncSession, row_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    if not row_ids:
        return {}
    result = await db.execute(
        select(MailFollowup.gmail_sent_message_id, sa_func.max(MailFollowup.sent_at))
        .where(MailFollowup.gmail_sent_message_id.in_(row_ids))
        .group_by(MailFollowup.gmail_sent_message_id)
    )
    return dict(result.all())


async def _build_rows(db: AsyncSession, sent_rows: list[GmailSentMessage]) -> list[SentMailRow]:
    application_ids = [r.application_id for r in sent_rows if r.application_id is not None]
    applications_by_id: dict[uuid.UUID, Application] = {}
    if application_ids:
        result = await db.scalars(select(Application).where(Application.id.in_(application_ids)))
        applications_by_id = {a.id: a for a in result.all()}

    last_followups = await _last_followup_map(db, [r.id for r in sent_rows])

    rows: list[SentMailRow] = []
    for r in sent_rows:
        application = applications_by_id.get(r.application_id) if r.application_id else None
        rows.append(
            SentMailRow(
                id=r.id,
                source="platform" if application is not None else "external",
                poster_name=application.poster_name if application else None,
                company=application.company if application else None,
                application_id=r.application_id,
                recipient=r.recipient,
                subject=r.subject,
                sent_at=r.sent_at,
                last_followup_at=last_followups.get(r.id),
                reply_status="replied" if r.reply_detected else "awaiting",
                is_archived=r.is_archived,
            )
        )
    return rows


async def _compute_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
    date_from: date | None,
    date_to: date | None,
    result_size_estimate: int | None,
) -> MailboxSummary:
    """Aggregates over gmail_sent_messages rows already cached for this user matching the active
    date filter — i.e. what's been paged through so far, not the whole mailbox (see
    mailbox/schemas.py::MailboxSummary's docstring)."""
    conditions = [GmailSentMessage.user_id == user_id]
    if date_from is not None:
        conditions.append(GmailSentMessage.sent_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to is not None:
        end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        conditions.append(GmailSentMessage.sent_at < end)

    cached_rows = list((await db.scalars(select(GmailSentMessage).where(*conditions))).all())

    loaded_count = len(cached_rows)
    sent_via_platform = sum(1 for r in cached_rows if r.application_id is not None)
    replies_detected = sum(1 for r in cached_rows if r.reply_detected)
    awaiting_response = sum(1 for r in cached_rows if not r.reply_detected and not r.is_archived)

    row_ids = [r.id for r in cached_rows]
    followups_sent = 0
    if row_ids:
        followups_sent = (
            await db.scalar(
                select(sa_func.count())
                .select_from(MailFollowup)
                .where(MailFollowup.gmail_sent_message_id.in_(row_ids))
            )
            or 0
        )

    platform_rows = [r for r in cached_rows if r.application_id is not None]
    platform_replies = sum(1 for r in platform_rows if r.reply_detected)

    return MailboxSummary(
        result_size_estimate=result_size_estimate,
        loaded_count=loaded_count,
        sent_via_platform=sent_via_platform,
        followups_sent=followups_sent,
        replies_detected=replies_detected,
        response_rate=(replies_detected / loaded_count) if loaded_count else None,
        response_rate_platform=(platform_replies / len(platform_rows)) if platform_rows else None,
        awaiting_response=awaiting_response,
        # Not computed in v1: would need the replying message's own Date header (not just whether
        # one exists), which get_thread_reply_status doesn't currently surface. Left null rather
        # than adding a second per-thread fetch loop just for this one figure — documented gap, see
        # docs/PROGRESS.md's Feature 13 log.
        avg_days_to_reply=None,
    )


async def get_sent_mail_page(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    page_size: int,
    page_token: str | None,
    date_from: date | None,
    date_to: date | None,
) -> SentMailPageResponse:
    access_token = await get_valid_access_token(db, user_id)
    own_gmail_address = await _get_gmail_address(db, user_id)

    # list_sent_messages_page can no longer filter by date server-side (see its docstring — the
    # gmail.metadata scope rejects Gmail's q= search entirely), so a page here is unfiltered
    # Sent mail. Filtered out below, once each row's sent_at is known.
    ids, next_page_token, result_size_estimate = await list_sent_messages_page(
        access_token, page_size=page_size, page_token=page_token
    )

    existing_by_id: dict[str, GmailSentMessage] = {}
    if ids:
        result = await db.scalars(
            select(GmailSentMessage).where(GmailSentMessage.user_id == user_id, GmailSentMessage.gmail_message_id.in_(ids))
        )
        existing_by_id = {row.gmail_message_id: row for row in result.all()}

    page_rows: list[GmailSentMessage] = []
    for message_id in ids:
        row = existing_by_id.get(message_id)
        if row is None:
            metadata = await get_message_metadata(access_token, message_id)
            application_id = await _find_matching_application_id(db, user_id, message_id)
            row = await with_serialization_retry(
                db, _insert_sent_message, db, user_id, message_id, metadata, application_id
            )
        if date_from is not None and (row.sent_at is None or row.sent_at.date() < date_from):
            continue
        if date_to is not None and (row.sent_at is None or row.sent_at.date() > date_to):
            continue
        if not row.reply_detected:
            reply_detected, _ = await get_thread_reply_status(access_token, row.gmail_thread_id, own_gmail_address)
            if reply_detected:
                row = await with_serialization_retry(db, _mark_reply_detected, db, user_id, row.id)
        page_rows.append(row)

    rows = await _build_rows(db, page_rows)
    summary = await _compute_summary(db, user_id, date_from, date_to, result_size_estimate)
    return SentMailPageResponse(rows=rows, next_page_token=next_page_token, summary=summary)


async def _log_followup_draft_usage(db: AsyncSession, user_id: uuid.UUID, usage: AgentUsageInfo) -> None:
    db.add(
        AgentUsageLog(
            user_id=user_id,
            agent_name="followup_drafter",
            model_used=usage.model_used,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=usage.latency_ms,
        )
    )
    await db.commit()


async def draft_followup(db: AsyncSession, user_id: uuid.UUID, gmail_sent_message_id: uuid.UUID) -> FollowupDraftResponse:
    """Stateless on purpose — unlike applications.create_draft, nothing is persisted here. A
    message can get multiple follow-ups over time, so there's no single "current draft" column to
    write into; only send_followup() persists anything (a mail_followups row, after review)."""
    row = await _get_owned_row(db, user_id, gmail_sent_message_id)

    follow_up_count = (
        await db.scalar(
            select(sa_func.count()).select_from(MailFollowup).where(MailFollowup.gmail_sent_message_id == row.id)
        )
        or 0
    )
    days_since_sent = (datetime.now(timezone.utc) - row.sent_at).days if row.sent_at else 0

    application = None
    if row.application_id is not None:
        application = await db.scalar(select(Application).where(Application.id == row.application_id))

    if application is not None:
        original_body = application.final_email_sent or (
            application.drafted_email.get("body") if application.drafted_email else None
        )
        context = FollowupDraftContext(
            original_subject=row.subject,
            original_body=original_body,
            job_title=application.job_title,
            company=application.company,
            days_since_sent=days_since_sent,
            follow_up_number=follow_up_count + 1,
            grounding="full",
        )
    else:
        context = FollowupDraftContext(
            original_subject=row.subject,
            original_body=None,
            job_title=None,
            company=None,
            days_since_sent=days_since_sent,
            follow_up_number=follow_up_count + 1,
            grounding="subject_only",
        )

    try:
        draft, usage = await run_followup_drafter_agent(context)
    except Exception as exc:
        logger.exception("Follow-Up Drafter agent failed for mailbox row %s (user %s)", gmail_sent_message_id, user_id)
        raise FollowupDraftingError("Follow-Up Drafter agent failed to generate a draft.") from exc

    await with_serialization_retry(db, _log_followup_draft_usage, db, user_id, usage)

    return FollowupDraftResponse(subject=draft.subject, body=draft.body, grounding=context.grounding)


async def _persist_followup(
    db: AsyncSession,
    user_id: uuid.UUID,
    gmail_sent_message_id: uuid.UUID,
    follow_up_number: int,
    subject: str,
    body: str,
    gmail_message_id: str,
) -> SentMailRow:
    row = await _get_owned_row(db, user_id, gmail_sent_message_id)
    db.add(
        MailFollowup(
            gmail_sent_message_id=row.id,
            follow_up_number=follow_up_number,
            drafted_subject=subject,
            drafted_body=body,
            gmail_message_id=gmail_message_id,
        )
    )
    row.synced_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    rows = await _build_rows(db, [row])
    return rows[0]


async def send_followup(
    db: AsyncSession, user_id: uuid.UUID, gmail_sent_message_id: uuid.UUID, subject: str, body: str
) -> SentMailRow:
    row = await _get_owned_row(db, user_id, gmail_sent_message_id)
    if not row.recipient:
        raise FollowupDraftingError("No recipient on file for this message.")

    access_token = await get_valid_access_token(db, user_id)
    own_gmail_address = await _get_gmail_address(db, user_id)

    # Reply into whatever's most recent on the thread (a prior follow-up, or the recipient's own
    # reply) rather than always the original send — that's the correct RFC In-Reply-To target.
    _, latest_message_id_header = await get_thread_reply_status(access_token, row.gmail_thread_id, own_gmail_address)
    if latest_message_id_header is None:
        raise FollowupDraftingError("Could not find a Message-ID to reply to on this thread.")

    to_address = parseaddr(row.recipient)[1] or row.recipient
    gmail_message_id, _ = await send_reply(
        db,
        user_id,
        to=to_address,
        subject=subject,
        body_text=body,
        thread_id=row.gmail_thread_id,
        in_reply_to_message_id=latest_message_id_header,
    )

    follow_up_count = (
        await db.scalar(
            select(sa_func.count()).select_from(MailFollowup).where(MailFollowup.gmail_sent_message_id == row.id)
        )
        or 0
    )
    return await with_serialization_retry(
        db, _persist_followup, db, user_id, row.id, follow_up_count + 1, subject, body, gmail_message_id
    )


async def _set_archived(db: AsyncSession, user_id: uuid.UUID, gmail_sent_message_id: uuid.UUID, archived: bool) -> SentMailRow:
    row = await _get_owned_row(db, user_id, gmail_sent_message_id)
    row.is_archived = archived
    await db.commit()
    await db.refresh(row)
    rows = await _build_rows(db, [row])
    return rows[0]


async def set_archived(db: AsyncSession, user_id: uuid.UUID, gmail_sent_message_id: uuid.UUID, archived: bool) -> SentMailRow:
    return await with_serialization_retry(db, _set_archived, db, user_id, gmail_sent_message_id, archived)
