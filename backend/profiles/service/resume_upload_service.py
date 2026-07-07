import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_usage.models import AgentUsageLog
from agent_usage.schemas import AgentUsageInfo
from agents.resume_parser.agent import parse_resume
from agents.resume_parser.pdf_extractor import ResumeTextExtractionError, extract_resume_text
from agents.resume_parser.schemas import ResumeUploadResult
from core.database import with_serialization_retry
from core.storage import upload_pdf
from profiles.models import ResumeUpload, UserProfile
from profiles.schemas import ResumeUploadResponse
from profiles.service.profile_service import ProfileNotFoundError

logger = logging.getLogger(__name__)

MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024


class InvalidResumeFileError(Exception):
    pass


class ResumeParsingError(Exception):
    pass


async def _assert_profile_owned(db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> None:
    exists = await db.scalar(
        select(UserProfile.id).where(UserProfile.id == profile_id, UserProfile.user_id == user_id)
    )
    if exists is None:
        raise ProfileNotFoundError(str(profile_id))


async def _persist_resume_record(
    db: AsyncSession,
    user_id: uuid.UUID,
    profile_id: uuid.UUID,
    upload_id: uuid.UUID,
    file_path: str,
    original_filename: str,
    raw_text: str,
    parsed_at: datetime,
    parsed_usage: AgentUsageInfo,
) -> ResumeUpload:
    """Deactivate the previous active resume (if any) and insert the new one, atomically. Split out
    from upload_and_parse_resume so only this DB-only step is retried on a CockroachDB serialization
    conflict (SQLSTATE 40001) — retrying the whole function would redundantly re-upload to R2 and
    re-run the LLM parse."""
    await db.execute(
        update(ResumeUpload)
        .where(ResumeUpload.profile_id == profile_id, ResumeUpload.is_active.is_(True))
        .values(is_active=False)
    )
    record = ResumeUpload(
        id=upload_id,
        user_id=user_id,
        profile_id=profile_id,
        file_path=file_path,
        original_filename=original_filename,
        is_active=True,
        raw_text=raw_text,
        parsed_at=parsed_at,
    )
    db.add(record)
    db.add(
        AgentUsageLog(
            user_id=user_id,
            agent_name="resume_parser",
            model_used=parsed_usage.model_used,
            input_tokens=parsed_usage.input_tokens,
            output_tokens=parsed_usage.output_tokens,
            latency_ms=parsed_usage.latency_ms,
        )
    )
    await db.commit()
    await db.refresh(record)
    return record


async def upload_and_parse_resume(
    db: AsyncSession,
    user_id: uuid.UUID,
    profile_id: uuid.UUID,
    original_filename: str,
    file_bytes: bytes,
) -> ResumeUploadResult:
    await _assert_profile_owned(db, user_id, profile_id)

    if len(file_bytes) > MAX_RESUME_SIZE_BYTES:
        raise InvalidResumeFileError("Resume file exceeds the 5MB limit.")
    if not file_bytes.startswith(b"%PDF-"):
        raise InvalidResumeFileError("File is not a valid PDF.")

    try:
        resume_text = extract_resume_text(file_bytes)
    except ResumeTextExtractionError as exc:
        raise InvalidResumeFileError(str(exc)) from exc

    try:
        parsed, parsed_usage = await parse_resume(resume_text)
    except Exception as exc:
        logger.exception("Resume Parser agent failed for profile %s", profile_id)
        raise ResumeParsingError("Resume Parser agent failed to process this resume.") from exc

    upload_id = uuid.uuid4()
    file_path = f"resumes/{user_id}/{profile_id}/{upload_id}.pdf"
    await upload_pdf(file_path, file_bytes)

    record = await with_serialization_retry(
        db,
        _persist_resume_record,
        db,
        user_id,
        profile_id,
        upload_id,
        file_path,
        original_filename,
        resume_text,
        datetime.now(timezone.utc),
        parsed_usage,
    )

    return ResumeUploadResult(resume=ResumeUploadResponse.model_validate(record), parsed=parsed)


async def get_active_resume(db: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> ResumeUpload | None:
    await _assert_profile_owned(db, user_id, profile_id)
    return await db.scalar(
        select(ResumeUpload).where(ResumeUpload.profile_id == profile_id, ResumeUpload.is_active.is_(True))
    )
