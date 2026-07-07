from pydantic import BaseModel, Field


class RelevanceScorerContext(BaseModel):
    """Everything the Relevance Scorer agent (A4) needs, already assembled by
    application_service — the agent itself has no DB access, matching every other agent."""

    job_title: str | None
    company: str | None
    seniority: str | None
    location: str | None
    skills: list[str]
    profile_context: str


class RelevanceScorerOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    reasoning: str = Field(min_length=1)
