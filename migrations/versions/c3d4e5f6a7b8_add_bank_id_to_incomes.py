"""add bank_id to incomes

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'incomes',
        sa.Column('bank_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_incomes_bank_id',
        'incomes', 'banks',
        ['bank_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_incomes_bank_id', 'incomes', type_='foreignkey')
    op.drop_column('incomes', 'bank_id')
