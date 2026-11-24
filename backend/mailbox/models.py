import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class GmailSentMessage(Base):
    """One cached row per Sent-mailbox message the user has paged through in the Manage Gmail
    view (Feature 13) — populated lazily as pages are fetched, never a full-mailbox upfront sync.
    application_id is set at sync time by matching gmail_message_id against
    applications.gmail_message_id; null means "External" (not sent through this platform, or sent
    before that column existed). Only header-level data ever lands here (gmail.metadata scope) —
    never a message body."""

    __tablename__ = "gmail_sent_messages"
    __table_args__ = (UniqueConstraint("user_id", "gmail_message_id", name="uq_gmail_sent_messages_user_message"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recipient: Mapped[str | None] = mapped_column(String(320), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    # Re-checked (via gmail.metadata thread inspection) only while still False, on every sync that
    # touches this row — bounds Gmail API quota use on repeat visits to an already-replied thread.
    reply_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # This feature's own archive, orthogonal to applications.is_archived (Feature 10) — stops
    # follow-up suggestions on this row without touching the application tracker record.
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MailFollowup(Base):
    """History of follow-ups actually sent for a gmail_sent_messages row (never the in-progress
    draft — draft_followup() is stateless and doesn't write here; only a real send does)."""

    __tablename__ = "mail_followups"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gmail_sent_message_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("gmail_sent_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    follow_up_number: Mapped[int] = mapped_column(Integer, nullable=False)
    drafted_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    drafted_body: Mapped[str] = mapped_column(Text, nullable=False)
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
