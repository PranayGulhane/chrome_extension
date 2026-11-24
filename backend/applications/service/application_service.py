import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_usage.models import AgentUsageLog
from agent_usage.schemas import AgentUsageInfo
from agents.email_drafter.agent import draft_email
from agents.email_drafter.schemas import EmailDraftContext, EmailDraftOutput
from agents.jd_parser.agent import parse_job_post
from agents.jd_parser.schemas import JDParserOutput
from agents.relevance_scorer.agent import score_post
from agents.relevance_scorer.schemas import RelevanceScorerContext, RelevanceScorerOutput
from applications.models import Application, ApplicationStatusEnum, OutreachTypeEnum
from applications.schemas import POST_SNIPPET_LENGTH, DraftedEmailPayload, PostExtractionRequest
from core.database import with_serialization_retry
from core.storage import download_pdf
from gmail.service.gmail_service import send_message
from profiles.schemas import ProfileResponse
from profiles.service.resume_upload_service import get_active_resume
from profiles.service.profile_service import get_default_profile_id, get_profile

logger = logging.getLogger(__name__)

_PROFILE_CONTEXT_MAX_LENGTH = 3000
_RESUME_CONTEXT_MAX_LENGTH = 3000
_MAX_EXPERIENCES_IN_CONTEXT = 4
_MAX_PROJECTS_IN_CONTEXT = 2


class ApplicationNotFoundError(Exception):
    pass


class JDParsingError(Exception):
    pass


class EmailDraftingError(Exception):
    pass


class NoDraftError(Exception):
    pass


class NoRecipientError(Exception):
    pass


class NoResumeError(Exception):
    pass


class WrongOutreachTypeError(Exception):
    pass


class NotYetSentError(Exception):
    pass


class NotDiscardableError(Exception):
    pass


async def _get_owned(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    application = await db.scalar(
        select(Application).where(Application.id == application_id, Application.user_id == user_id)
    )
    if application is None:
        raise ApplicationNotFoundError(str(application_id))
    return application


async def _persist_application(
    db: AsyncSession,
    user_id: uuid.UUID,
    request: PostExtractionRequest,
    parsed: JDParserOutput,
    parsed_usage: AgentUsageInfo,
    score: RelevanceScorerOutput | None,
    score_usage: AgentUsageInfo | None,
) -> Application:
    # Split out from create_from_extraction so only this DB-only step is retried on a CockroachDB
    # serialization conflict (SQLSTATE 40001) — retrying the whole function would redundantly
    # re-run the LLM parse (same reasoning as resume_upload_service._persist_resume_record).
    application = Application(
        user_id=user_id,
        poster_name=request.poster_name,
        poster_profile_url=request.poster_profile_url,
        poster_headline=request.poster_headline,
        post_url=request.post_url,
        post_timestamp=request.post_timestamp,
        post_snippet=request.post_content[:POST_SNIPPET_LENGTH],
        was_truncated=request.was_truncated,
        company=parsed.company,
        job_title=parsed.job_title,
        skills=parsed.skills,
        seniority=parsed.seniority,
        location=parsed.location,
        parsed_email=parsed.email,
        # Feature 7: an application already "is" email outreach once the JD Parser found an
        # address — the no-email wizard (outreach_type set explicitly via update_application)
        # only ever applies to the remaining 3 branches.
        outreach_type=OutreachTypeEnum.EMAIL if parsed.email else None,
        # Feature 9 (A4) — both stay null if the user had no profile yet or scoring failed
        # (create_from_extraction treats it as best-effort, never a blocker).
        relevance_score=score.score if score else None,
        relevance_reasoning=score.reasoning if score else None,
    )
    db.add(application)
    db.add(
        AgentUsageLog(
            user_id=user_id,
            agent_name="jd_parser",
            model_used=parsed_usage.model_used,
            input_tokens=parsed_usage.input_tokens,
            output_tokens=parsed_usage.output_tokens,
            latency_ms=parsed_usage.latency_ms,
        )
    )
    if score_usage is not None:
        db.add(
            AgentUsageLog(
                user_id=user_id,
                agent_name="relevance_scorer",
                model_used=score_usage.model_used,
                input_tokens=score_usage.input_tokens,
                output_tokens=score_usage.output_tokens,
                latency_ms=score_usage.latency_ms,
            )
        )
    await db.commit()
    await db.refresh(application)
    return application


async def create_from_extraction(
    db: AsyncSession, user_id: uuid.UUID, request: PostExtractionRequest
) -> tuple[Application, JDParserOutput]:
    try:
        parsed, parsed_usage = await parse_job_post(request.post_content)
    except Exception as exc:
        logger.exception("JD Parser agent failed for a post extraction (user %s)", user_id)
        raise JDParsingError("JD Parser agent failed to process this post.") from exc

    score, score_usage = await _try_score_relevance(db, user_id, parsed)

    application = await with_serialization_retry(
        db, _persist_application, db, user_id, request, parsed, parsed_usage, score, score_usage
    )
    return application, parsed


async def _try_score_relevance(
    db: AsyncSession, user_id: uuid.UUID, parsed: JDParserOutput
) -> tuple[RelevanceScorerOutput | None, AgentUsageInfo | None]:
    """Feature 9 (A4): best-effort relevance scoring against the user's default profile. Returns
    (None, None) if the user has no profile yet, or if the scoring call itself fails — this is a
    supplementary signal, never a reason to fail the whole extraction."""
    profile_id = await get_default_profile_id(db, user_id)
    if profile_id is None:
        return None, None

    try:
        profile = await get_profile(db, user_id, profile_id)
        context = RelevanceScorerContext(
            job_title=parsed.job_title,
            company=parsed.company,
            seniority=parsed.seniority,
            location=parsed.location,
            skills=parsed.skills,
            profile_context=_build_profile_context(profile),
        )
        return await score_post(context)
    except Exception:
        logger.warning("Relevance Scorer agent failed for a post extraction (user %s)", user_id, exc_info=True)
        return None, None


async def update_application(
    db: AsyncSession,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    *,
    email: str | None,
    post_url: str | None,
    drafted_email: DraftedEmailPayload | None,
    outreach_type: OutreachTypeEnum | None,
    outreach_note: str | None,
) -> Application:
    """Partial update. post_url exists to let the user paste in the post's real permalink — the
    auto-captured value is a best-effort fallback (the search-results page URL, since no reliable
    per-post permalink was found in that page's markup during live testing) rather than a
    guaranteed deep link. drafted_email lets the user's manual edits to a generated draft
    (create_draft below) persist the same way parsed_email/post_url do. outreach_type/
    outreach_note power Feature 7's 4-way no-email wizard — saving an email always implies
    outreach_type=email (whether it came from the wizard's email branch or the older plain
    manual-entry form), while an explicit outreach_type in the request covers the other 3
    branches (linkedin_dm/apply_via_link/reach_out_other)."""
    application = await _get_owned(db, user_id, application_id)
    if email is not None:
        application.parsed_email = email
        application.outreach_type = OutreachTypeEnum.EMAIL
    if post_url is not None:
        application.post_url = post_url
    if drafted_email is not None:
        application.drafted_email = drafted_email.model_dump()
    if outreach_type is not None:
        application.outreach_type = outreach_type
    if outreach_note is not None:
        application.outreach_note = outreach_note
    await db.commit()
    await db.refresh(application)
    return application


async def list_applications(db: AsyncSession, user_id: uuid.UUID) -> list[Application]:
    result = await db.scalars(
        select(Application).where(Application.user_id == user_id).order_by(Application.created_at.desc())
    )
    return list(result.all())


async def get_application(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    return await _get_owned(db, user_id, application_id)


def _build_profile_context(profile: ProfileResponse) -> str:
    """Plain-text summary of a saved profile for the Email Drafter agent's prompt — the agent has
    no DB access, so this is assembled here from the already-eager-loaded profile relationships
    (profile_service.get_profile loads all of them). Truncated defensively: an unusually large
    profile could otherwise blow past the drafting model's prompt-token budget, same class of risk
    as Feature 3's resume-parsing max_tokens tuning."""
    personal_info = profile.personal_info
    name = " ".join(filter(None, [personal_info.first_name, personal_info.last_name]))

    lines = [f"Target role: {profile.target_job_title}"]
    if name:
        lines.append(f"Candidate name: {name}")
    if personal_info.professional_headline:
        lines.append(f"Headline: {personal_info.professional_headline}")
    if profile.professional_summary:
        lines.append(f"Summary: {profile.professional_summary}")

    if profile.skills:
        by_category: dict[str, list[str]] = {}
        for skill in profile.skills:
            by_category.setdefault(skill.category, []).append(skill.skill_name)
        skills_text = "; ".join(f"{category}: {', '.join(names)}" for category, names in by_category.items())
        lines.append(f"Skills: {skills_text}")

    for experience in profile.experiences[:_MAX_EXPERIENCES_IN_CONTEXT]:
        span = "Present" if experience.currently_working_here else (experience.end_date or "unknown end")
        header = f"Experience: {experience.job_title} at {experience.company_name} ({experience.start_date or '?'}-{span})"
        if experience.responsibilities:
            header += " — " + "; ".join(experience.responsibilities)
        lines.append(header)

    for project in profile.projects[:_MAX_PROJECTS_IN_CONTEXT]:
        project_line = f"Project: {project.project_name}"
        if project.details:
            project_line += " — " + "; ".join(project.details)
        lines.append(project_line)

    return "\n".join(lines)[:_PROFILE_CONTEXT_MAX_LENGTH]


async def create_draft(
    db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID, profile_id: uuid.UUID
) -> Application:
    application = await _get_owned(db, user_id, application_id)
    profile = await get_profile(db, user_id, profile_id)  # raises ProfileNotFoundError if not owned
    resume = await get_active_resume(db, user_id, profile_id)

    context = EmailDraftContext(
        poster_name=application.poster_name,
        job_title=application.job_title,
        company=application.company,
        seniority=application.seniority,
        location=application.location,
        skills=application.skills,
        post_snippet=application.post_snippet,
        profile_context=_build_profile_context(profile),
        resume_context=resume.raw_text[:_RESUME_CONTEXT_MAX_LENGTH] if resume else None,
        # linkedin_dm outreach still runs through this same agent/endpoint — is_dm is a plain
        # bool (not the OutreachTypeEnum itself) so agents/email_drafter stays decoupled from the
        # applications module's models, matching every other agent's "no DB/module coupling" shape.
        is_dm=application.outreach_type == OutreachTypeEnum.LINKEDIN_DM,
    )

    try:
        draft, usage = await draft_email(context)
    except Exception as exc:
        logger.exception("Email Drafter agent failed for application %s (user %s)", application_id, user_id)
        raise EmailDraftingError("Email Drafter agent failed to generate a draft.") from exc

    return await with_serialization_retry(
        db, _persist_draft, db, user_id, application_id, profile_id, draft, usage
    )


async def _persist_draft(
    db: AsyncSession,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    profile_id: uuid.UUID,
    draft: EmailDraftOutput,
    usage: AgentUsageInfo,
) -> Application:
    # Same "DB-only step gets the retry, LLM call doesn't" split as _persist_application /
    # resume_upload_service._persist_resume_record — re-fetches fresh state on each attempt.
    application = await _get_owned(db, user_id, application_id)
    application.profile_id = profile_id
    application.drafted_email = {"subject": draft.subject, "body": draft.body}
    if application.status == ApplicationStatusEnum.EXTRACTED:
        application.status = ApplicationStatusEnum.DRAFT_READY

    db.add(
        AgentUsageLog(
            user_id=user_id,
            agent_name="email_drafter",
            model_used=usage.model_used,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=usage.latency_ms,
        )
    )
    await db.commit()
    await db.refresh(application)
    return application


def _sanitize_filename_part(text: str) -> str:
    # Collapse whitespace to underscores, strip anything that isn't safe across filesystems/email
    # clients (keep alnum, underscore, hyphen) — used to build the resume attachment filename.
    return re.sub(r"[^A-Za-z0-9_-]", "", re.sub(r"\s+", "_", text.strip()))


_ALREADY_SENT_STATUSES = (ApplicationStatusEnum.SENT, ApplicationStatusEnum.REPLIED)


async def check_duplicate_contact(
    db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> tuple[Application, str] | None:
    """Feature 11 — advisory only, never blocks the extract/draft/send flow. Called right after
    extraction (not at send time) so the user can decide whether to bother drafting at all.
    Matches on poster_profile_url (always present) or parsed_email (case-insensitive, only when
    set) against any other application for this user that was actually sent — catches both "already
    reached out to this exact person" (even with no/a different email) and "already used this
    email" (even from a different poster, e.g. a shared HR inbox). poster_profile_url is preferred
    as the reported matched_via when both match, since it's the stronger identity signal."""
    application = await _get_owned(db, user_id, application_id)
    conditions = [Application.poster_profile_url == application.poster_profile_url]
    if application.parsed_email:
        conditions.append(func.lower(Application.parsed_email) == application.parsed_email.lower())
    existing = await db.scalar(
        select(Application)
        .where(
            Application.user_id == user_id,
            Application.id != application_id,
            or_(*conditions),
            Application.status.in_(_ALREADY_SENT_STATUSES),
        )
        .order_by(Application.sent_at.desc())
        .limit(1)
    )
    if existing is None:
        return None
    matched_via = "poster_profile_url" if existing.poster_profile_url == application.poster_profile_url else "email"
    return existing, matched_via


async def delete_application(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> None:
    """Feature 11 — lets the user discard a just-extracted application when the duplicate-contact
    warning shows and they decide not to pursue it, so a redundant row isn't left behind alongside
    the contact already on record. Deliberately narrow: only reachable while still status=extracted
    (nothing drafted or sent yet) — G5's "every application is auto-saved regardless of send
    action" commitment still holds once real work (a draft, a send) exists for the record."""
    application = await _get_owned(db, user_id, application_id)
    if application.status != ApplicationStatusEnum.EXTRACTED:
        raise NotDiscardableError(str(application_id))
    await db.delete(application)
    await db.commit()


async def send_application_email(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    """PRD §09 step 3: fetches the active resume PDF for the application's selected profile,
    builds the multipart email, sends via the user's connected Gmail account. Raises NoDraftError/
    NoRecipientError/NoResumeError for the PRD's explicit pre-send checks, and whatever
    gmail_service raises (GmailNotConnectedError/GmailApiError) for the actual send step."""
    application = await _get_owned(db, user_id, application_id)
    if not application.drafted_email:
        raise NoDraftError("This application doesn't have a drafted email yet.")
    if not application.parsed_email:
        raise NoRecipientError("No recipient email is set for this application yet.")
    if not application.profile_id:
        raise NoDraftError("No profile was selected when this draft was created.")

    resume = await get_active_resume(db, user_id, application.profile_id)
    if resume is None:
        raise NoResumeError("No resume is uploaded for the selected profile — upload one before sending.")

    profile = await get_profile(db, user_id, application.profile_id)
    personal_info = profile.personal_info
    name_parts = [personal_info.first_name, personal_info.last_name, profile.target_job_title]
    filename = "_".join(_sanitize_filename_part(part) for part in name_parts if part) + "_Resume.pdf"

    attachment_bytes = await download_pdf(resume.file_path)
    gmail_message_id, gmail_thread_id = await send_message(
        db,
        user_id,
        to=application.parsed_email,
        subject=application.drafted_email["subject"],
        body_text=application.drafted_email["body"],
        attachment_bytes=attachment_bytes,
        attachment_filename=filename,
    )
    logger.info("Sent application %s via Gmail (message id %s)", application_id, gmail_message_id)

    return await with_serialization_retry(
        db, _persist_sent, db, user_id, application_id, resume.id, gmail_message_id, gmail_thread_id
    )


async def _persist_sent(
    db: AsyncSession,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    resume_upload_id: uuid.UUID,
    gmail_message_id: str,
    gmail_thread_id: str,
) -> Application:
    # Same "DB-only step gets the retry, the external call doesn't" split as _persist_draft —
    # re-fetches fresh state on each attempt rather than resending the email on a serialization
    # conflict (the Gmail send already happened by the time this runs).
    application = await _get_owned(db, user_id, application_id)
    application.final_email_sent = application.drafted_email["body"] if application.drafted_email else None
    application.resume_upload_id = resume_upload_id
    application.sent_at = datetime.now(timezone.utc)
    application.status = ApplicationStatusEnum.SENT
    # Feature 13 (Gmail Follow-Up Manager) matches gmail_sent_messages rows back to this
    # application via gmail_message_id — previously fetched from the Gmail API and logged, then
    # discarded, on every send.
    application.gmail_message_id = gmail_message_id
    application.gmail_thread_id = gmail_thread_id
    await db.commit()
    await db.refresh(application)
    return application


async def mark_sent_manually(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    """For the 3 non-email outreach types (linkedin_dm/apply_via_link/reach_out_other), there's no
    backend-programmatic send to confirm — DM copy-paste, an external application link, and a
    manual contact are all outside this app's reach. This is the user's own confirmation that they
    followed through. The email path must use send_application_email instead (it's the one outreach
    type this app can actually send on the user's behalf), enforced below."""
    application = await _get_owned(db, user_id, application_id)
    if application.outreach_type is None or application.outreach_type == OutreachTypeEnum.EMAIL:
        raise WrongOutreachTypeError(
            "Pick an outreach type (LinkedIn DM, application link, or another contact) before "
            "marking this as sent — an email outreach type must be sent via Gmail instead."
        )
    return await with_serialization_retry(db, _mark_sent, db, user_id, application_id)


async def _mark_sent(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    application = await _get_owned(db, user_id, application_id)
    application.sent_at = datetime.now(timezone.utc)
    application.status = ApplicationStatusEnum.SENT
    await db.commit()
    await db.refresh(application)
    return application


async def mark_replied(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    """PRD §10: status -> replied is always a manual transition, for every outreach type —
    there's no way to detect a reply automatically without broader Gmail scopes than gmail.send."""
    application = await _get_owned(db, user_id, application_id)
    if application.status != ApplicationStatusEnum.SENT:
        raise NotYetSentError("This application hasn't been marked sent yet.")
    return await with_serialization_retry(db, _mark_replied, db, user_id, application_id)


async def _mark_replied(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    application = await _get_owned(db, user_id, application_id)
    application.status = ApplicationStatusEnum.REPLIED
    await db.commit()
    await db.refresh(application)
    return application


async def archive_application(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    """Feature 10 — orthogonal to status (can archive at any lifecycle stage), so no state-machine
    precondition to check here, unlike mark_sent_manually/mark_replied."""
    return await with_serialization_retry(db, _set_archived, db, user_id, application_id, True)


async def unarchive_application(db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    return await with_serialization_retry(db, _set_archived, db, user_id, application_id, False)


async def _set_archived(
    db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID, archived: bool
) -> Application:
    application = await _get_owned(db, user_id, application_id)
    application.is_archived = archived
    await db.commit()
    await db.refresh(application)
    return application
