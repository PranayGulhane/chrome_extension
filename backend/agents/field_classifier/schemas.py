from typing import Literal

from pydantic import BaseModel, Field

# Keep this Literal in sync with ProfileFieldKey in
# frontend/extension/src/content/formFiller.ts — it's the fixed vocabulary the classifier is
# allowed to answer with. Using a Literal (not a bare `str`) means Groq's strict json_schema mode
# rejects any key outside this list at the API level, so a hallucinated key can't reach the
# extension at all rather than needing to be filtered out after the fact.
ProfileFieldKey = Literal[
    "first_name",
    "last_name",
    "full_name",
    "email",
    "phone_number",
    "current_city",
    "state_province",
    "country",
    "linkedin_url",
    "github_url",
    "portfolio_website",
    "personal_website",
    "work_authorization",
    "willing_to_relocate",
    "nationality",
    "current_employer",
    "current_job_title",
]


class UnmatchedField(BaseModel):
    """One form field the heuristic pass (content/formFiller.ts's autocomplete-attribute and
    label-synonym matching) couldn't confidently classify — everything here is generic page
    structure (a question's caption, its input type, its option labels), never the candidate's own
    data."""

    index: int
    text: str
    field_type: str
    options: list[str] = Field(default_factory=list)


class FieldClassifierContext(BaseModel):
    fields: list[UnmatchedField]


class FieldMatch(BaseModel):
    index: int
    key: ProfileFieldKey | None = None


class FieldClassifierOutput(BaseModel):
    matches: list[FieldMatch] = Field(default_factory=list)
