import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from applications.models import ApplicationStatusEnum, OutreachTypeEnum

POST_SNIPPET_LENGTH = 500


class PostExtractionRequest(BaseModel):
    """What the content script sends after capturing one selected LinkedIn post. post_content is
    the full captured text — sent to the JD Parser agent but only the first
    POST_SNIPPET_LENGTH chars are ever persisted (see applications.models.Application)."""

    poster_name: str = Field(min_length=1, max_length=255)
    poster_profile_url: str = Field(min_length=1, max_length=1024)
    poster_headline: str | None = Field(default=None, max_length=500)
    post_content: str = Field(min_length=1)
    post_url: str = Field(min_length=1, max_length=1024)
    post_timestamp: datetime | None = None
    # Defensive flag only — per the PRD's resolved "see more" question, the content script is not
    # supposed to submit an extraction at all while a post still looks truncated. This exists for
    # the edge case where truncation is detected only after the fact.
    was_truncated: bool = False


class DraftedEmailPayload(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)


class DraftEmailRequest(BaseModel):
    profile_id: uuid.UUID


class ApplicationUpdateRequest(BaseModel):
    """Partial update — all fields optional, only the ones provided are changed.
    outreach_type/outreach_note power Feature 7's 4-way no-email wizard (linkedin_dm/
    apply_via_link/reach_out_other) — setting parsed_email instead always implies outreach_type
    email, handled in application_service.update_application."""

    parsed_email: EmailStr | None = None
    post_url: str | None = Field(default=None, min_length=1, max_length=1024)
    drafted_email: DraftedEmailPayload | None = None
    outreach_type: OutreachTypeEnum | None = None
    outreach_note: str | None = Field(default=None, max_length=2000)


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    profile_id: uuid.UUID | None
    poster_name: str
    poster_profile_url: str
    poster_headline: str | None
    post_url: str
    post_timestamp: datetime | None
    post_snippet: str
    was_truncated: bool
    company: str | None
    job_title: str | None
    skills: list[str]
    seniority: str | None
    location: str | None
    parsed_email: str | None
    outreach_type: OutreachTypeEnum | None
    outreach_note: str | None
    drafted_email: dict | None
    # Not exposed until now — Feature 4/5/6 had no reader that needed either field, but PRD §10
    # explicitly lists "Final Email Sent" and "Resume Attached" as tracker fields, so Feature 7 is
    # what surfaces them.
    final_email_sent: str | None
    resume_upload_id: uuid.UUID | None
    # Feature 9 (A4, Post Relevance Scorer) — both null if the user had no profile at extraction
    # time or the scoring call failed (best-effort, never blocks extraction).
    relevance_score: int | None
    relevance_reasoning: str | None
    is_archived: bool
    status: ApplicationStatusEnum
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PostExtractionResponse(BaseModel):
    """Returned only by POST /applications/extract. is_hiring isn't a DB column — it's a property
    of that one parse, not the saved record (is_hiring=false posts are still saved like any other
    extraction) — so it rides alongside the persisted `application`, not inside it. PATCH just
    returns ApplicationResponse directly since nothing about hiring-ness is recomputed there."""

    application: ApplicationResponse
    is_hiring: bool


class DuplicateCheckResponse(BaseModel):
    """Feature 11 — advisory check the extension calls right after extraction, to warn the user if
    they've already contacted this poster or recipient from a different application. Purely
    informational: nothing in the extract/draft/send flow is ever blocked by this. matched_via
    tells the UI which identity signal matched — poster_profile_url is preferred when both match,
    since "you already contacted this person" is more useful than "you already used this email"."""

    is_duplicate: bool
    matched_via: Literal["email", "poster_profile_url"] | None = None
    existing_application: ApplicationResponse | None = None
