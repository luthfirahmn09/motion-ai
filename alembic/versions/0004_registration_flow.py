"""registration flow: plans table, account/subscription status, phone

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_plans_table = sa.table(
    "subscription_plans",
    sa.column("name", sa.String),
    sa.column("days", sa.Integer),
    sa.column("price", sa.Integer),
    sa.column("is_active", sa.Boolean),
)

INITIAL_PLANS = [
    {"name": "14 Hari", "days": 14, "price": 0, "is_active": True},
    {"name": "30 Hari", "days": 30, "price": 0, "is_active": True},
    {"name": "90 Hari", "days": 90, "price": 0, "is_active": True},
    {"name": "180 Hari", "days": 180, "price": 0, "is_active": True},
    {"name": "360 Hari", "days": 360, "price": 0, "is_active": True},
]


def upgrade() -> None:
    # Create subscription_plans table
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), server_default="0"),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )
    op.bulk_insert(_plans_table, INITIAL_PLANS)

    # Add new user columns
    op.add_column("users", sa.Column("account_status", sa.String(), server_default="whitelist", nullable=False))
    op.add_column("users", sa.Column("subscription_status", sa.String(), nullable=True))
    op.add_column("users", sa.Column("phone_number", sa.String(), nullable=True))
    op.add_column("users", sa.Column("selected_plan_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_selected_plan_id",
        "users", "subscription_plans",
        ["selected_plan_id"], ["id"],
    )

    # Migrate data from old columns
    op.execute("UPDATE users SET account_status = 'banned' WHERE is_banned = true")
    op.execute("UPDATE users SET subscription_status = 'active' WHERE is_registered = true")

    # Drop old columns
    op.drop_column("users", "is_banned")
    op.drop_column("users", "is_registered")


def downgrade() -> None:
    op.add_column("users", sa.Column("is_registered", sa.Boolean(), server_default="false"))
    op.add_column("users", sa.Column("is_banned", sa.Boolean(), server_default="false"))
    op.execute("UPDATE users SET is_banned = true WHERE account_status = 'banned'")
    op.execute("UPDATE users SET is_registered = true WHERE subscription_status = 'active'")
    op.drop_constraint("fk_users_selected_plan_id", "users", type_="foreignkey")
    op.drop_column("users", "selected_plan_id")
    op.drop_column("users", "phone_number")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "account_status")
    op.drop_table("subscription_plans")
