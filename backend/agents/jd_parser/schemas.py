from pydantic import BaseModel, Field


class JDParserOutput(BaseModel):
    """Structured job data extracted from a single LinkedIn post's text."""

    is_hiring: bool = False
    job_title: str | None = None
    company: str | None = None
    email: str | None = None
    skills: list[str] = Field(default_factory=list)
    seniority: str | None = None
    location: str | None = None
