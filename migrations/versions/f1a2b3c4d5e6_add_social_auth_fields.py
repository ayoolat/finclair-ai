"""add social auth fields to users

Revision ID: f1a2b3c4d5e6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('users', 'hashed_passcode', nullable=True)
    op.add_column('users', sa.Column('auth_provider', sa.String(20), nullable=False, server_default='email'))
    op.add_column('users', sa.Column('firebase_uid', sa.String(128), nullable=True))
    op.create_unique_constraint('uq_users_firebase_uid', 'users', ['firebase_uid'])


def downgrade() -> None:
    op.drop_constraint('uq_users_firebase_uid', 'users', type_='unique')
    op.drop_column('users', 'firebase_uid')
    op.drop_column('users', 'auth_provider')
    op.alter_column('users', 'hashed_passcode', nullable=False)
