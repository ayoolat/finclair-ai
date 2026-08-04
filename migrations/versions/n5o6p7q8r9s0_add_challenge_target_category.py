"""add target_category_id and current_period_spent to savings_challenges

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, None] = "m4n5o6p7q8r9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("savings_challenges", sa.Column("target_category_id", sa.UUID(), nullable=True))
    op.add_column(
        "savings_challenges", sa.Column("current_period_spent", sa.Numeric(15, 2), nullable=True)
    )
    op.create_foreign_key(
        "fk_savings_challenges_target_category_id_categories",
        "savings_challenges",
        "categories",
        ["target_category_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_savings_challenges_target_category_id_categories",
        "savings_challenges",
        type_="foreignkey",
    )
    op.drop_column("savings_challenges", "current_period_spent")
    op.drop_column("savings_challenges", "target_category_id")
