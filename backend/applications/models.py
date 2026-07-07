import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class OutreachTypeEnum(str, enum.Enum):
    EMAIL = "email"
    LINKEDIN_DM = "linkedin_dm"
    APPLY_VIA_LINK = "apply_via_link"
    REACH_OUT_OTHER = "reach_out_other"


class ApplicationStatusEnum(str, enum.Enum):
    EXTRACTED = "extracted"
    DRAFT_READY = "draft_ready"
    SENT = "sent"
    REPLIED = "replied"


def _enum_column(enum_cls: type[enum.Enum], name: str, length: int = 32):
    # values_callable is mandatory: without it SQLAlchemy persists the Python enum *name* instead
    # of its *value* — see docs/PROGRESS.md's Phase 1 enum-storage bug note. Same helper shape as
    # profiles/models.py, kept local so this module doesn't depend on another module's private name.
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
    )


class Application(Base):
    """One row per post the user has selected for extraction. Feature 4 only ever writes the
    "extracted" slice of this (poster/post/job fields, status=extracted); profile_id, outreach_*,
    drafted_email, final_email_sent, resume_upload_id and sent_at are populated by later features
    (5-7) on the same row rather than a new table, per docs/PROGRESS.md's Feature 4 log."""

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )

    # Extracted from the LinkedIn post (required per PRD's Post Extraction section).
    poster_name: Mapped[str] = mapped_column(String(255), nullable=False)
    poster_profile_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    poster_headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    post_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    post_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # First POST_SNIPPET_LENGTH (applications/schemas.py) chars of the captured post content — the
    # full text is only ever sent to the JD Parser agent in-request, never persisted (see
    # docs/PROGRESS.md Feature 4 log). post_url is what lets the user revisit the actual post.
    post_snippet: Mapped[str] = mapped_column(String(500), nullable=False)
    was_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Parsed by the JD Parser agent (A1).
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    seniority: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parsed_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # Populated by later features — nullable here on purpose.
    outreach_type: Mapped[OutreachTypeEnum | None] = mapped_column(
        _enum_column(OutreachTypeEnum, "outreach_type_enum"), nullable=True
    )
    outreach_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    drafted_email: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    final_email_sent: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("resume_uploads.id", ondelete="SET NULL"), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Feature 9 (A4, Post Relevance Scorer) — computed best-effort at extraction time against the
    # user's default profile; both stay null if the user has no profile yet or the scoring call
    # itself fails (this is a supplementary signal, never a blocker on extraction succeeding).
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[ApplicationStatusEnum] = mapped_column(
        _enum_column(ApplicationStatusEnum, "application_status_enum"),
        nullable=False,
        default=ApplicationStatusEnum.EXTRACTED,
    )
    # Feature 10 — orthogonal to status (can be archived at any lifecycle stage, e.g. "no longer
    # expecting anything" or "got rejected"), not a new status value.
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
