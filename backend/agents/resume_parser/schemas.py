import re
from datetime import date

from pydantic import BaseModel, Field

from profiles.schemas import (
    AchievementItem,
    CertificationItem,
    EducationItem,
    ExperienceItem,
    ExperienceProjectItem,
    LanguageItem,
    PersonalInfo,
    ProjectItem,
    ResumeUploadResponse,
    SkillItem,
)

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9,
    "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}


def _parse_partial_date(raw: str | None) -> date | None:
    """Resumes almost never spell out full ISO dates ("Jan 2021", "2019", "03/2020" are the
    norm) — asking Groq's structured-output tool-calling to emit a strict `date` directly fails
    with a 400 (schema validation error) on any of those, which would break parsing for nearly
    every real resume. So the LLM emits dates as free text (see the *_date: str | None fields
    below) and this best-effort parser normalizes them afterward. Anything it can't confidently
    parse is left as None (blank) rather than guessed — the user fills it in on review, same
    policy as the LLM's own "don't hallucinate" instruction."""
    if not raw:
        return None
    text = raw.strip().lower().rstrip(".")
    if text in ("present", "current", "now", "ongoing", "till date", "to date"):
        return None

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    m = re.fullmatch(r"(\d{1,2})[/-](\d{4})", text)
    if m:
        month = int(m.group(1))
        if 1 <= month <= 12:
            return date(int(m.group(2)), month, 1)

    m = re.fullmatch(r"([a-z]+)\.?,?\s+(\d{4})", text)
    if m and m.group(1) in _MONTHS:
        return date(int(m.group(2)), _MONTHS[m.group(1)], 1)

    m = re.fullmatch(r"(\d{4})", text)
    if m:
        return date(int(m.group(1)), 1, 1)

    return None


class _RawExperienceProjectItem(BaseModel):
    project_name: str
    details: list[str] = Field(default_factory=list)


class _RawExperienceItem(BaseModel):
    job_title: str
    company_name: str
    employment_type: str | None = None
    location: str | None = None
    start_date: str | None = Field(default=None, description="As written in the resume, e.g. 'Jan 2021', '2019'.")
    end_date: str | None = Field(
        default=None, description="As written in the resume. Leave empty (and set currently_working_here) if 'Present'/'Current'."
    )
    currently_working_here: bool = False
    responsibilities: list[str] = Field(default_factory=list)
    projects: list[_RawExperienceProjectItem] = Field(default_factory=list)


class _RawEducationItem(BaseModel):
    degree: str
    field_of_study: str | None = None
    minor: str | None = None
    institution_name: str
    university_board: str | None = None
    location: str | None = None
    start_date: str | None = Field(default=None, description="As written in the resume, e.g. '2016'.")
    end_date: str | None = Field(default=None, description="As written in the resume, e.g. '2020'.")
    graduation_year: int | None = None
    gpa: str | None = None
    honors: str | None = None


class _RawCertificationItem(BaseModel):
    certification_name: str
    issuing_organization: str | None = None
    issue_date: str | None = Field(default=None, description="As written in the resume.")
    expiry_date: str | None = Field(default=None, description="As written in the resume.")
    credential_id: str | None = None
    credential_url: str | None = None


class _RawAchievementItem(BaseModel):
    achievement_title: str
    organization: str | None = None
    date_achieved: str | None = Field(default=None, description="As written in the resume.")
    description: list[str] = Field(default_factory=list)


class ResumeParserLLMOutput(BaseModel):
    """The schema actually bound to Groq's structured output. Date fields are raw strings —
    see _parse_partial_date for why. Not returned to callers directly; use parse_resume()'s
    return value (ResumeParserOutput) instead, which has this normalized into real dates."""

    professional_summary: str | None = None
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    skills: list[SkillItem] = Field(default_factory=list)
    experiences: list[_RawExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    education: list[_RawEducationItem] = Field(default_factory=list)
    certifications: list[_RawCertificationItem] = Field(default_factory=list)
    achievements: list[_RawAchievementItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)


class ResumeParserOutput(BaseModel):
    """Partial UserProfile object with normalized dates — reuses profiles.schemas item shapes
    directly so this can be handed straight to the profile editor / PUT /profiles/{id} without a
    translation layer."""

    professional_summary: str | None = None
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    skills: list[SkillItem] = Field(default_factory=list)
    experiences: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    achievements: list[AchievementItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)


def normalize_llm_output(raw: ResumeParserLLMOutput) -> ResumeParserOutput:
    return ResumeParserOutput(
        professional_summary=raw.professional_summary,
        personal_info=raw.personal_info,
        skills=raw.skills,
        experiences=[
            ExperienceItem(
                job_title=e.job_title,
                company_name=e.company_name,
                employment_type=e.employment_type,
                location=e.location,
                start_date=_parse_partial_date(e.start_date),
                end_date=_parse_partial_date(e.end_date),
                currently_working_here=e.currently_working_here,
                responsibilities=e.responsibilities,
                projects=[
                    ExperienceProjectItem(project_name=p.project_name, details=p.details) for p in e.projects
                ],
            )
            for e in raw.experiences
        ],
        projects=raw.projects,
        education=[
            EducationItem(
                degree=e.degree,
                field_of_study=e.field_of_study,
                minor=e.minor,
                institution_name=e.institution_name,
                university_board=e.university_board,
                location=e.location,
                start_date=_parse_partial_date(e.start_date),
                end_date=_parse_partial_date(e.end_date),
                graduation_year=e.graduation_year,
                gpa=e.gpa,
                honors=e.honors,
            )
            for e in raw.education
        ],
        certifications=[
            CertificationItem(
                certification_name=c.certification_name,
                issuing_organization=c.issuing_organization,
                issue_date=_parse_partial_date(c.issue_date),
                expiry_date=_parse_partial_date(c.expiry_date),
                credential_id=c.credential_id,
                credential_url=c.credential_url,
            )
            for c in raw.certifications
        ],
        achievements=[
            AchievementItem(
                achievement_title=a.achievement_title,
                organization=a.organization,
                date_achieved=_parse_partial_date(a.date_achieved),
                description=a.description,
            )
            for a in raw.achievements
        ],
        languages=raw.languages,
    )


class ResumeUploadResult(BaseModel):
    resume: ResumeUploadResponse
    parsed: ResumeParserOutput
