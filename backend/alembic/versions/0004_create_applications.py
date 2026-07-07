"""create applications table

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("poster_name", sa.String(length=255), nullable=False),
        sa.Column("poster_profile_url", sa.String(length=1024), nullable=False),
        sa.Column("poster_headline", sa.String(length=500), nullable=True),
        sa.Column("post_url", sa.String(length=1024), nullable=False),
        sa.Column("post_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("post_snippet", sa.String(length=300), nullable=False),
        sa.Column("was_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("skills", sa.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("seniority", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("parsed_email", sa.String(length=320), nullable=True),
        # outreach_type / status are stored as plain varchar (native_enum=False on the ORM side —
        # see applications/models.py's _enum_column, same CockroachDB ALTER-TYPE-avoidance reason
        # as auth.models.User.role and profiles.models.ProfileLanguage.proficiency), not a native
        # Postgres ENUM type.
        sa.Column("outreach_type", sa.String(length=32), nullable=True),
        sa.Column("outreach_note", sa.Text(), nullable=True),
        sa.Column("drafted_email", postgresql.JSONB(), nullable=True),
        sa.Column("final_email_sent", sa.Text(), nullable=True),
        sa.Column(
            "resume_upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resume_uploads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="extracted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_user_id", table_name="applications")
    op.drop_table("applications")
