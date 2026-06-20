import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.common.mixins.audit import AuditMixin

if TYPE_CHECKING:
    from app.module.expense.schema.expense import Expense
    from app.module.expense.schema.expense_item import ExpenseItem


class Category(AuditMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        # System categories: unique name globally (user_id IS NULL)
        Index("uq_categories_name_system", "name", unique=True, postgresql_where="user_id IS NULL"),
        # User categories: unique name per user
        UniqueConstraint("name", "user_id", name="uq_categories_name_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    expenses: Mapped[list["Expense"]] = relationship(
        "Expense",
        secondary="expense_categories",
        back_populates="categories",
    )
    expense_items: Mapped[list["ExpenseItem"]] = relationship(
        "ExpenseItem",
        back_populates="category",
    )
