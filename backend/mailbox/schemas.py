import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

PAGE_SIZE_CHOICES = (10, 20, 50, 100)


class SentMailPageRequest(BaseModel):
    page_size: Literal[10, 20, 50, 100] = 20
    page_token: str | None = None
    # Optional filter, not a required precondition — narrows the Gmail search query when present.
    date_from: date | None = None
    date_to: date | None = None


class SentMailRow(BaseModel):
    id: uuid.UUID
    source: Literal["platform", "external"]
    # Only populated for source="platform", pulled from the linked application.
    poster_name: str | None = None
    company: str | None = None
    application_id: uuid.UUID | None = None
    recipient: str | None = None
    subject: str | None = None
    sent_at: datetime | None = None
    last_followup_at: datetime | None = None
    reply_status: Literal["awaiting", "replied"]
    is_archived: bool


class MailboxSummary(BaseModel):
    """Computed over gmail_sent_messages rows the user has actually paged through so far (matching
    the active date filter, if any) — deliberately NOT a whole-mailbox aggregate, since walking
    every page up front to get an exact total would defeat the point of paginating. result_size_estimate
    is Gmail's own approximate count for the active query, shown as a headline "~N sent" figure
    precisely because the rest of this summary is only ever partial."""

    result_size_estimate: int | None
    loaded_count: int
    sent_via_platform: int
    followups_sent: int
    replies_detected: int
    response_rate: float | None
    response_rate_platform: float | None
    awaiting_response: int
    avg_days_to_reply: float | None


class SentMailPageResponse(BaseModel):
    rows: list[SentMailRow]
    next_page_token: str | None
    summary: MailboxSummary


class FollowupDraftResponse(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    # "full" = grounded in the original email's own stored body + job context (Platform rows only).
    # "subject_only" = the backend never read that email's body (gmail.metadata scope can't return
    # one for an External row) — grounded only in the Subject header, deliberately shorter/generic.
    grounding: Literal["full", "subject_only"]


class SendFollowupRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
