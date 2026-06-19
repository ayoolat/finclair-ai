"""drop bank_id from incomes

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('fk_incomes_bank_id', 'incomes', type_='foreignkey')
    op.drop_column('incomes', 'bank_id')


def downgrade() -> None:
    op.add_column('incomes', sa.Column('bank_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_incomes_bank_id',
        'incomes', 'banks',
        ['bank_id'], ['id'],
        ondelete='SET NULL',
    )
