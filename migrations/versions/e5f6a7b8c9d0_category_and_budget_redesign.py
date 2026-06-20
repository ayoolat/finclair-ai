"""category and budget redesign

Revision ID: e5f6a7b8c9d0
Revises: b2c3d4e5f6a7
Create Date: 2026-06-20 00:00:00.000000

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_CATEGORIES = [
    ("Food & Dining", "Groceries, restaurants, and takeout"),
    ("Transport", "Fuel, public transit, ride-hailing"),
    ("Housing", "Rent, mortgage, utilities"),
    ("Health", "Medical, pharmacy, fitness"),
    ("Shopping", "Clothing, electronics, and general retail"),
    ("Entertainment", "Movies, games, subscriptions"),
    ("Education", "Courses, books, and tuition"),
    ("Utilities", "Electricity, water, internet, phone"),
    ("Savings", "Savings transfers and investments"),
    ("Others", "Uncategorised expenses"),
]


def upgrade() -> None:
    # ── categories: add user_id, icon; drop old global unique; add new constraints ──
    op.drop_constraint("categories_name_key", "categories", type_="unique")

    op.add_column("categories", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column("categories", sa.Column("icon", sa.String(length=100), nullable=True))

    op.create_index(
        "uq_categories_name_system",
        "categories",
        ["name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_unique_constraint("uq_categories_name_user", "categories", ["name", "user_id"])

    # ── budgets: drop name; add unique per-user-month ──
    op.drop_column("budgets", "name")
    op.create_unique_constraint("uq_budgets_user_month", "budgets", ["user_id", "start_date"])

    # ── seed default categories (skip if already present) ──
    conn = op.get_bind()
    for name, desc in DEFAULT_CATEGORIES:
        conn.execute(
            sa.text(
                "INSERT INTO categories (id, user_id, name, description, icon) "
                "VALUES (:id, NULL, :name, :desc, NULL) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": str(uuid.uuid4()), "name": name, "desc": desc},
        )


def downgrade() -> None:
    op.drop_constraint("uq_budgets_user_month", "budgets", type_="unique")
    op.add_column("budgets", sa.Column("name", sa.String(length=100), nullable=False, server_default="Budget"))
    op.alter_column("budgets", "name", server_default=None)

    op.drop_constraint("uq_categories_name_user", "categories", type_="unique")
    op.drop_index("uq_categories_name_system", table_name="categories")
    op.drop_column("categories", "icon")
    op.drop_column("categories", "user_id")

    op.create_unique_constraint("categories_name_key", "categories", ["name"])
