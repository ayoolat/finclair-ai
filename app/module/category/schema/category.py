import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.common.mixins.audit import AuditMixin

if TYPE_CHECKING:
    from app.module.expense.schema.expense import Expense
    from app.module.expense.schema.expense_item import ExpenseItem


class Category(AuditMixin, Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)

    expenses: Mapped[list["Expense"]] = relationship(
        "Expense",
        secondary="expense_categories",
        back_populates="categories",
    )
    expense_items: Mapped[list["ExpenseItem"]] = relationship(
        "ExpenseItem",
        back_populates="category",
    )
