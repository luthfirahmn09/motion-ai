"""initial tables

Revision ID: 0001
Revises:
Create Date: 2026-05-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("jobs_today", sa.Integer(), server_default="0"),
        sa.Column("last_reset", sa.Date(), server_default=sa.func.current_date()),
        sa.Column("is_banned", sa.Boolean(), server_default="false"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("photo_path", sa.String(), nullable=True),
        sa.Column("video_path", sa.String(), nullable=True),
        sa.Column("replicate_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="queued"),
        sa.Column("progress", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("output_path", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), server_default="std"),
        sa.Column("orientation", sa.String(), server_default="video"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("users")
