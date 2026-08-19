"""add email_logs

Revision ID: r9s0t1u2v3w4
Revises: q8r9s0t1u2v3
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r9s0t1u2v3w4"
down_revision: Union[str, None] = "q8r9s0t1u2v3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("from_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("template", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_logs_to_email", "email_logs", ["to_email"])
    op.create_index("ix_email_logs_status", "email_logs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_logs_status", table_name="email_logs")
    op.drop_index("ix_email_logs_to_email", table_name="email_logs")
    op.drop_table("email_logs")
