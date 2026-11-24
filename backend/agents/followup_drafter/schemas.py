from typing import Literal

from pydantic import BaseModel, Field


class FollowupDraftContext(BaseModel):
    """Everything the Follow-Up Drafter agent needs, already assembled by mailbox_service — same
    no-DB-access convention as every other agent in this codebase. original_body is only ever
    populated for grounding="full" (a Platform row, whose original email body is on file in this
    platform's own DB) — for grounding="subject_only" (an External row) it's always None, since
    gmail.metadata scope never returns a message body to read in the first place."""

    original_subject: str | None
    original_body: str | None
    job_title: str | None
    company: str | None
    days_since_sent: int
    follow_up_number: int
    grounding: Literal["full", "subject_only"]


class FollowupDraftOutput(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
