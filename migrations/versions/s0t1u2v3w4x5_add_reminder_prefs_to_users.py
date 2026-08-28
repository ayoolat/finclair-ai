"""add daily reminder prefs to users

Revision ID: s0t1u2v3w4x5
Revises: r9s0t1u2v3w4
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "s0t1u2v3w4x5"
down_revision: Union[str, None] = "r9s0t1u2v3w4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("reminder_hour", sa.SmallInteger(), nullable=False, server_default="21"),
    )
    op.add_column(
        "users",
        sa.Column("reminder_minute", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("daily_reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # Budget alerts moved from a single "near_limit" (90%) marker to explicit
    # threshold_80 / threshold_90 / threshold_100 markers — carry existing rows
    # over so a 90%-alerted budget doesn't re-notify after deploy.
    op.execute("UPDATE budget_alerts SET alert_type = 'threshold_90' WHERE alert_type = 'near_limit'")


def downgrade() -> None:
    op.execute("UPDATE budget_alerts SET alert_type = 'near_limit' WHERE alert_type = 'threshold_90'")
    op.execute("DELETE FROM budget_alerts WHERE alert_type IN ('threshold_80', 'threshold_100')")
    op.drop_column("users", "daily_reminders_enabled")
    op.drop_column("users", "reminder_minute")
    op.drop_column("users", "reminder_hour")
