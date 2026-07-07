"""add access_expires_at/admin_notes to users

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # NULL = unlimited access — existing users are deliberately grandfathered, not retroactively
    # locked out. Only new signups (auth_service.register_user) get the 30-day default going forward.
    op.add_column("users", sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("admin_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "admin_notes")
    op.drop_column("users", "access_expires_at")
