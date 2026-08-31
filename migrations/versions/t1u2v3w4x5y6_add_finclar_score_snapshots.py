"""add finclar score snapshots

Revision ID: t1u2v3w4x5y6
Revises: s0t1u2v3w4x5
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "t1u2v3w4x5y6"
down_revision: Union[str, None] = "s0t1u2v3w4x5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finclar_score_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("budget_adherence", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("savings_consistency", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("tracking_consistency", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("goal_achievement", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "period_start", name="uq_finclar_scores_user_period"),
    )
    op.create_index(
        "ix_finclar_score_snapshots_user_period",
        "finclar_score_snapshots",
        ["user_id", "period_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_finclar_score_snapshots_user_period", table_name="finclar_score_snapshots")
    op.drop_table("finclar_score_snapshots")
