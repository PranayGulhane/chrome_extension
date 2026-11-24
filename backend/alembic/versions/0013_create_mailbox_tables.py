"""create mailbox tables (gmail_sent_messages, mail_followups) and application gmail id columns

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Set at send time going forward (application_service._persist_sent) from the Gmail API's
    # response, which gmail_service.send_message already fetches but previously discarded. Null for
    # anything not sent via this platform's Send flow, or sent before this column existed.
    op.add_column("applications", sa.Column("gmail_message_id", sa.String(length=255), nullable=True))
    op.add_column("applications", sa.Column("gmail_thread_id", sa.String(length=255), nullable=True))
    op.create_index("ix_applications_gmail_message_id", "applications", ["gmail_message_id"])

    op.create_table(
        "gmail_sent_messages",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("recipient", sa.String(length=320), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        # Matched at sync time via gmail_message_id == applications.gmail_message_id. Null =
        # "External" (not sent through this platform, or sent before gmail_message_id existed).
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reply_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Feature 13's own archive, orthogonal to applications.is_archived (Feature 10) — stops
        # follow-up suggestions on this row without touching the application tracker record.
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_gmail_sent_messages_user_id", "gmail_sent_messages", ["user_id"])
    op.create_unique_constraint(
        "uq_gmail_sent_messages_user_message", "gmail_sent_messages", ["user_id", "gmail_message_id"]
    )

    op.create_table(
        "mail_followups",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "gmail_sent_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_sent_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("follow_up_number", sa.Integer(), nullable=False),
        sa.Column("drafted_subject", sa.String(length=255), nullable=False),
        sa.Column("drafted_body", sa.Text(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mail_followups_gmail_sent_message_id", "mail_followups", ["gmail_sent_message_id"])


def downgrade() -> None:
    op.drop_index("ix_mail_followups_gmail_sent_message_id", table_name="mail_followups")
    op.drop_table("mail_followups")

    op.drop_constraint("uq_gmail_sent_messages_user_message", "gmail_sent_messages", type_="unique")
    op.drop_index("ix_gmail_sent_messages_user_id", table_name="gmail_sent_messages")
    op.drop_table("gmail_sent_messages")

    op.drop_index("ix_applications_gmail_message_id", table_name="applications")
    op.drop_column("applications", "gmail_thread_id")
    op.drop_column("applications", "gmail_message_id")
