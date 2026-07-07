import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class GmailCredential(Base):
    """One row per user — a user has at most one connected Gmail account at a time (unique
    user_id; reconnecting upserts this same row rather than creating a second one). Tokens are
    AES-256-GCM encrypted at rest via core/crypto.py, never returned to the client in plaintext."""

    __tablename__ = "gmail_credentials"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    gmail_address: Mapped[str] = mapped_column(String(320), nullable=False)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    token_expiry: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GmailOAuthState(Base):
    """Short-lived row bridging the authenticated 'start' request to the unauthenticated Google
    redirect callback (state is the only thing the callback request carries that ties back to a
    user). Deleted once consumed by a successful callback; an abandoned/expired row is otherwise
    just left in place — no cron cleanup, checked for a freshness window at consume-time instead
    (see gmail/service/gmail_service.py). Deliberate simplification for a dev-scale flow."""

    __tablename__ = "gmail_oauth_states"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
