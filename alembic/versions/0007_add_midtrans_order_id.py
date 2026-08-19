"""add midtrans_order_id to subscription_transactions

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription_transactions",
        sa.Column("midtrans_order_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_sub_tx_midtrans_order_id",
        "subscription_transactions",
        ["midtrans_order_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_sub_tx_midtrans_order_id", "subscription_transactions")
    op.drop_column("subscription_transactions", "midtrans_order_id")
