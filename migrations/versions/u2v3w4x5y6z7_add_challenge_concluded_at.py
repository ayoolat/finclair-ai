"""add concluded_at to savings challenges

Revision ID: u2v3w4x5y6z7
Revises: t1u2v3w4x5y6
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u2v3w4x5y6z7"
down_revision: Union[str, None] = "t1u2v3w4x5y6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "savings_challenges",
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill challenges already in a terminal state. There was no dedicated
    # column until now, so updated_at is the best available proxy for when they
    # concluded.
    op.execute(
        """
        UPDATE savings_challenges
        SET concluded_at = updated_at
        WHERE status IN ('completed', 'failed', 'cancelled')
          AND concluded_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("savings_challenges", "concluded_at")
