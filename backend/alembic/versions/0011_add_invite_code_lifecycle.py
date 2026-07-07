"""add expires_at/revoked_at to invite_codes

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invite_codes", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invite_codes", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("invite_codes", "revoked_at")
    op.drop_column("invite_codes", "expires_at")
