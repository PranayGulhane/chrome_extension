import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from profiles.models import LanguageProficiencyEnum


class PersonalInfo(BaseModel):
    """Free-form personal/contact info, stored as a single JSONB blob (matches the PRD's DB schema
    diagram). Every field is optional so a resume parser (Phase 3) can hand back a partial object
    without hallucinating missing fields."""

    first_name: str | None = None
    last_name: str | None = None
    professional_headline: str | None = None
    email: str | None = None
    phone_number: str | None = None
    current_city: str | None = None
    state_province: str | None = None
    country: str | None = None
    willing_to_relocate: bool | None = None
    preferred_work_locations: list[str] = Field(default_factory=list)
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_website: str | None = None
    personal_website: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    work_authorization: str | None = None


class ExperienceProjectItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    project_name: str
    details: list[str] = Field(default_factory=list)
    display_order: int = 0


class SkillItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    category: str
    skill_name: str
    display_order: int = 0


class ExperienceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    job_title: str
    company_name: str
    employment_type: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    currently_working_here: bool = False
    responsibilities: list[str] = Field(default_factory=list)
    display_order: int = 0
    projects: list[ExperienceProjectItem] = Field(default_factory=list)


class ProjectItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    project_name: str
    details: list[str] = Field(default_factory=list)
    demo_url: str | None = None
    github_url: str | None = None
    display_order: int = 0


class EducationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    degree: str
    field_of_study: str | None = None
    minor: str | None = None
    institution_name: str
    university_board: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    graduation_year: int | None = None
    gpa: str | None = None
    honors: str | None = None
    display_order: int = 0


class CertificationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    certification_name: str
    issuing_organization: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None
    display_order: int = 0


class AchievementItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    achievement_title: str
    organization: str | None = None
    date_achieved: date | None = None
    description: list[str] = Field(default_factory=list)
    display_order: int = 0


class LanguageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    language: str
    proficiency: LanguageProficiencyEnum
    display_order: int = 0


class ProfileWriteRequest(BaseModel):
    """Used for both create (POST) and full-replace update (PUT). Nested collections are always
    replaced wholesale — this is an aggregate resource, not per-item CRUD, matching how a profile
    edit UI (and the resume parser in Phase 3) produces/consumes one whole profile at a time."""

    target_job_title: str = Field(min_length=1, max_length=255)
    is_default: bool = False
    professional_summary: str | None = None
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    skills: list[SkillItem] = Field(default_factory=list)
    experiences: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    achievements: list[AchievementItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)


class CloneProfileRequest(BaseModel):
    target_job_title: str = Field(min_length=1, max_length=255)


class ClassifyFieldsField(BaseModel):
    """One form field the extension's heuristic pass (content/formFiller.ts) couldn't confidently
    match to a profile key by itself — sent to the Field Classifier agent as a last resort. Only
    generic page structure (a question's caption/type/options), never the candidate's own data."""

    index: int
    text: str = Field(min_length=1, max_length=300)
    field_type: str = Field(max_length=30)
    options: list[str] = Field(default_factory=list, max_length=50)


class ClassifyFieldsRequest(BaseModel):
    fields: list[ClassifyFieldsField] = Field(max_length=60)


class ClassifyFieldsMatch(BaseModel):
    index: int
    key: str | None = None


class ClassifyFieldsResponse(BaseModel):
    matches: list[ClassifyFieldsMatch]


class ResumeUploadResponse(BaseModel):
    """Resume file metadata only — file_path and raw_text are never sent to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    original_filename: str
    is_active: bool
    parsed_at: datetime
    created_at: datetime


class ProfileSummaryResponse(BaseModel):
    """Lightweight shape for listing profiles — no nested collections, so it's one query instead
    of eight. Full detail (skills/experience/etc.) is fetched per-profile via GET /profiles/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    target_job_title: str
    is_default: bool
    professional_summary: str | None
    created_at: datetime
    updated_at: datetime


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    target_job_title: str
    is_default: bool
    professional_summary: str | None
    personal_info: PersonalInfo
    skills: list[SkillItem]
    experiences: list[ExperienceItem]
    projects: list[ProjectItem]
    education: list[EducationItem]
    certifications: list[CertificationItem]
    achievements: list[AchievementItem]
    languages: list[LanguageItem]
    created_at: datetime
    updated_at: datetime
