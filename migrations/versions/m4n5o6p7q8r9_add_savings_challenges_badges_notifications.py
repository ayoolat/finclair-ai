"""add savings challenges, badges, device tokens, budget alerts

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m4n5o6p7q8r9"
down_revision: Union[str, None] = "l3m4n5o6p7q8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── device_tokens ─────────────────────────────────────────────────────────
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(500), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token", name="uq_device_tokens_token"),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])

    # ── savings_challenges ────────────────────────────────────────────────────
    op.create_table(
        "savings_challenges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False, server_default="friday_savings"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("weekly_target", sa.Numeric(15, 2), nullable=True),
        sa.Column("overall_target", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_saved", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_entry_week", sa.String(10), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_savings_challenges_user_id", "savings_challenges", ["user_id"])
    op.create_index("ix_savings_challenges_status", "savings_challenges", ["status"])

    # ── challenge_entries ─────────────────────────────────────────────────────
    op.create_table(
        "challenge_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("challenge_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("verification_level", sa.String(20), nullable=False, server_default="self_reported"),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("file_url", sa.String(1000), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["challenge_id"], ["savings_challenges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_challenge_entries_challenge_id", "challenge_entries", ["challenge_id"])

    # ── badges ────────────────────────────────────────────────────────────────
    op.create_table(
        "badges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("icon_name", sa.String(100), nullable=True),
        sa.Column("category", sa.String(30), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_badges_key"),
    )

    # ── user_badges ───────────────────────────────────────────────────────────
    op.create_table(
        "user_badges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("badge_id", sa.UUID(), nullable=False),
        sa.Column("challenge_id", sa.UUID(), nullable=True),
        sa.Column("earned_period", sa.String(20), nullable=True),
        sa.Column("earned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["badge_id"], ["badges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["challenge_id"], ["savings_challenges.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_user_badges_user_id", "user_badges", ["user_id"])

    # ── budget_alerts ─────────────────────────────────────────────────────────
    op.create_table(
        "budget_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("budget_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_budget_alerts_budget_id", "budget_alerts", ["budget_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_alerts_budget_id", table_name="budget_alerts")
    op.drop_table("budget_alerts")
    op.drop_index("ix_user_badges_user_id", table_name="user_badges")
    op.drop_table("user_badges")
    op.drop_table("badges")
    op.drop_index("ix_challenge_entries_challenge_id", table_name="challenge_entries")
    op.drop_table("challenge_entries")
    op.drop_index("ix_savings_challenges_status", table_name="savings_challenges")
    op.drop_index("ix_savings_challenges_user_id", table_name="savings_challenges")
    op.drop_table("savings_challenges")
    op.drop_index("ix_device_tokens_user_id", table_name="device_tokens")
    op.drop_table("device_tokens")
