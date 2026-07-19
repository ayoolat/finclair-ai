"""add subscription_plans, subscriptions and subscription_transactions tables

Revision ID: j1k2l3m4n5o6
Revises: i8j9k0l1m2n3
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, None] = "i8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("compare_at_amount", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="NGN"),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("trial_days", sa.Integer(), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_subscription_plans_code"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("plan_code", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("compare_at_amount", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="NGN"),
        sa.Column("paystack_customer_code", sa.String(100), nullable=True),
        sa.Column("paystack_authorization_code", sa.String(100), nullable=True),
        sa.Column("paystack_email", sa.String(255), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_code"], ["subscription_plans.code"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
    )

    op.create_table(
        "subscription_transactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), nullable=False),
        sa.Column("paystack_reference", sa.String(100), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="NGN"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("gateway_response", sa.String(255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("paystack_reference", name="uq_subscription_transactions_reference"),
    )
    op.create_index(
        "ix_subscription_transactions_subscription_id",
        "subscription_transactions",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_transactions_subscription_id", table_name="subscription_transactions")
    op.drop_table("subscription_transactions")
    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
