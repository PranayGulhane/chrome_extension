from pydantic import BaseModel, Field


class EmailDraftContext(BaseModel):
    """Everything the Email Drafter agent needs, already assembled by application_service — the
    agent itself has no DB access, matching the JD Parser / Resume Parser pattern."""

    poster_name: str
    job_title: str | None
    company: str | None
    seniority: str | None
    location: str | None
    skills: list[str]
    post_snippet: str
    profile_context: str
    resume_context: str | None
    # Feature 7: linkedin_dm outreach reuses this same agent rather than a second one — a plain
    # bool, not an OutreachTypeEnum import, so this module stays decoupled from the applications
    # module's models (no agent has DB/module coupling elsewhere in this codebase either).
    is_dm: bool = False


class EmailDraftOutput(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
