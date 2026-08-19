"""add subscription_transactions table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("transaction_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("prev_status", sa.String(), nullable=True),
        sa.Column("new_status", sa.String(), nullable=False),
        sa.Column("prev_expires_at", sa.DateTime(), nullable=True),
        sa.Column("new_expires_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sub_tx_user_id", "subscription_transactions", ["user_id"])
    op.create_index("ix_sub_tx_created_at", "subscription_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sub_tx_created_at", "subscription_transactions")
    op.drop_index("ix_sub_tx_user_id", "subscription_transactions")
    op.drop_table("subscription_transactions")
