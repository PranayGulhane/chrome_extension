import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class LanguageProficiencyEnum(str, enum.Enum):
    NATIVE = "native"
    FLUENT = "fluent"
    PROFESSIONAL = "professional"
    INTERMEDIATE = "intermediate"
    BASIC = "basic"


def _enum_column(enum_cls: type[enum.Enum], name: str, length: int = 32):
    # values_callable is mandatory: without it SQLAlchemy persists the Python enum *name*
    # (e.g. "NATIVE") instead of its *value* ("native"), which breaks any raw-SQL consumer
    # and is inconsistent with migration server_defaults. Bit us once already in auth.models.
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        Index(
            "ix_user_profiles_one_default_per_user",
            "user_id",
            unique=True,
            postgresql_where="is_default = true",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    professional_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Personal info fields (name, contact, location, links, etc.) as a single JSONB blob — matches
    # the PRD's DB schema diagram exactly; validated on the way in/out via profiles/schemas.py.
    personal_info: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    skills: Mapped[list["ProfileSkill"]] = relationship(cascade="all, delete-orphan", order_by="ProfileSkill.display_order")
    experiences: Mapped[list["ProfileExperience"]] = relationship(
        cascade="all, delete-orphan", order_by="ProfileExperience.display_order"
    )
    projects: Mapped[list["ProfileProject"]] = relationship(
        cascade="all, delete-orphan", order_by="ProfileProject.display_order"
    )
    education: Mapped[list["ProfileEducation"]] = relationship(
        cascade="all, delete-orphan", order_by="ProfileEducation.display_order"
    )
    certifications: Mapped[list["ProfileCertification"]] = relationship(
        cascade="all, delete-orphan", order_by="ProfileCertification.display_order"
    )
    achievements: Mapped[list["ProfileAchievement"]] = relationship(
        cascade="all, delete-orphan", order_by="ProfileAchievement.display_order"
    )
    languages: Mapped[list["ProfileLanguage"]] = relationship(
        cascade="all, delete-orphan", order_by="ProfileLanguage.display_order"
    )


class ProfileSkill(Base):
    __tablename__ = "profile_skills"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProfileExperience(Base):
    __tablename__ = "profile_experiences"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currently_working_here: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    responsibilities: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    projects: Mapped[list["ExperienceProject"]] = relationship(
        cascade="all, delete-orphan", order_by="ExperienceProject.display_order"
    )


class ExperienceProject(Base):
    __tablename__ = "experience_projects"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experience_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profile_experiences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProfileProject(Base):
    __tablename__ = "profile_projects"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    demo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProfileEducation(Base):
    __tablename__ = "profile_education"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    degree: Mapped[str] = mapped_column(String(255), nullable=False)
    field_of_study: Mapped[str | None] = mapped_column(String(255), nullable=True)
    minor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    institution_name: Mapped[str] = mapped_column(String(255), nullable=False)
    university_board: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpa: Mapped[str | None] = mapped_column(String(50), nullable=True)
    honors: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProfileCertification(Base):
    __tablename__ = "profile_certifications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    certification_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuing_organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    credential_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProfileAchievement(Base):
    __tablename__ = "profile_achievements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    achievement_title: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_achieved: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProfileLanguage(Base):
    __tablename__ = "profile_languages"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(100), nullable=False)
    proficiency: Mapped[LanguageProficiencyEnum] = mapped_column(
        _enum_column(LanguageProficiencyEnum, "language_proficiency_enum"), nullable=False
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ResumeUpload(Base):
    __tablename__ = "resume_uploads"
    __table_args__ = (
        Index(
            "ix_resume_uploads_one_active_per_profile",
            "profile_id",
            unique=True,
            postgresql_where="is_active = true",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # R2 object key, e.g. resumes/{user_id}/{profile_id}/{upload_id}.pdf — never returned to the client.
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
