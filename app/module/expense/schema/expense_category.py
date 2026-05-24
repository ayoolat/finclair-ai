from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID

from app.database.session import Base

expense_categories = Table(
    "expense_categories",
    Base.metadata,
    Column(
        "expense_id",
        UUID(as_uuid=True),
        ForeignKey("expenses.id"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "category_id",
        UUID(as_uuid=True),
        ForeignKey("categories.id"),
        primary_key=True,
        nullable=False,
    ),
)
