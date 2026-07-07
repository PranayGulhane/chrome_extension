"""add relevance_score/relevance_reasoning to applications

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("relevance_score", sa.Integer(), nullable=True))
    op.add_column("applications", sa.Column("relevance_reasoning", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "relevance_reasoning")
    op.drop_column("applications", "relevance_score")
