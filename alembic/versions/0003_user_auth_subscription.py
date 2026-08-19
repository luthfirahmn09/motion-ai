"""add user auth and subscription fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_registered", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("subscription_expires_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("features", sa.String(), server_default="motion_control", nullable=True))
    op.add_column("users", sa.Column("user_api_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "user_api_key")
    op.drop_column("users", "features")
    op.drop_column("users", "subscription_expires_at")
    op.drop_column("users", "is_registered")
