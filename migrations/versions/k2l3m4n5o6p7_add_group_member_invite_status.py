"""add invite_status to group_members

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k2l3m4n5o6p7"
down_revision: Union[str, None] = "j1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "group_members",
        sa.Column("invite_status", sa.String(20), nullable=False, server_default="pending"),
    )
    # Existing members already had full access before this field existed — treat them as accepted.
    op.execute("UPDATE group_members SET invite_status = 'accepted'")
    op.alter_column("group_members", "invite_status", server_default=None)


def downgrade() -> None:
    op.drop_column("group_members", "invite_status")
