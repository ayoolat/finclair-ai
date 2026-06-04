"""add financial_goals table and banks.mono_account_id

Revision ID: a1b2c3d4e5f6
Revises: e35b4348f70c
Create Date: 2026-06-04 00:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e35b4348f70c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'financial_goals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=400), nullable=False),
        sa.Column('icon_name', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )

    goals_table = sa.table(
        'financial_goals',
        sa.column('id', sa.UUID),
        sa.column('key', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('icon_name', sa.String),
    )
    op.bulk_insert(goals_table, [
        {
            'id': uuid.uuid4(),
            'key': 'smart_money_saving',
            'name': 'Save more money',
            'description': 'Help me understand my spending and find simple ways to save more every month.',
            'icon_name': 'wallet',
        },
        {
            'id': uuid.uuid4(),
            'key': 'track_my_spending',
            'name': 'Track My Spending',
            'description': 'Help me see where my money goes with quick tracking and easy-to-read summaries.',
            'icon_name': 'bar-chart',
        },
        {
            'id': uuid.uuid4(),
            'key': 'stick_to_a_budget',
            'name': 'Stick to a Budget',
            'description': 'Help me set spending limits and warn me before I overspend.',
            'icon_name': 'pie-chart',
        },
        {
            'id': uuid.uuid4(),
            'key': 'feel_more_in_control',
            'name': 'Feel More In Control',
            'description': 'Help me feel less stressed about money by giving me a clearer picture of my finances.',
            'icon_name': 'briefcase',
        },
    ])

    op.add_column('banks', sa.Column('mono_account_id', sa.String(length=100), nullable=True))
    op.add_column('banks', sa.Column('mono_code', sa.String(length=100), nullable=True))

    op.create_table(
        'paystack_banks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('paystack_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('country', sa.String(length=10), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('bank_type', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paystack_id'),
    )

    op.create_table(
        'files',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('folder', sa.String(length=200), nullable=False),
        sa.Column('file_name', sa.String(length=200), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # source: manual | receipt | bank_sync
    op.add_column('expenses', sa.Column('source', sa.String(length=20), nullable=True))
    op.add_column('expenses', sa.Column('file_id', sa.UUID(), nullable=True))
    op.add_column('expenses', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(None, 'expenses', 'files', ['file_id'], ['id'])

    op.add_column('banks', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('incomes', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_table('paystack_banks')
    op.drop_column('incomes', 'deleted_at')
    op.drop_column('banks', 'deleted_at')
    op.drop_constraint(None, 'expenses', type_='foreignkey')
    op.drop_column('expenses', 'deleted_at')
    op.drop_column('expenses', 'file_id')
    op.drop_column('expenses', 'source')
    op.drop_table('files')
    op.drop_column('banks', 'mono_code')
    op.drop_column('banks', 'mono_account_id')
    op.drop_table('financial_goals')
