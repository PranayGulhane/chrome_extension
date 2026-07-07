"""widen applications.post_snippet to 500 chars

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("applications", "post_snippet", type_=sa.String(length=500), existing_type=sa.String(length=300))


def downgrade() -> None:
    op.alter_column("applications", "post_snippet", type_=sa.String(length=300), existing_type=sa.String(length=500))
