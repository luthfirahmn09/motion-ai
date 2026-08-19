"""add aspect_ratio to jobs

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("aspect_ratio", sa.String(), nullable=True, server_default="9:16"),
    )


def downgrade() -> None:
    op.drop_column("jobs", "aspect_ratio")
