import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.common.mixins.audit import AuditMixin

if TYPE_CHECKING:
    from app.module.expense.schema.expense import Expense
    from app.module.category.schema.category import Category


class ExpenseItem(AuditMixin, Base):
    __tablename__ = "expense_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_expense_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_expense_items_unit_price_non_negative"),
        CheckConstraint("total_price >= 0", name="ck_expense_items_total_price_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    expense_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expenses.id"),
        nullable=False,
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)

    expense: Mapped["Expense"] = relationship(
        "Expense",
        back_populates="items",
        foreign_keys=[expense_id],
    )
    category: Mapped[Optional["Category"]] = relationship(
        "Category",
        back_populates="expense_items",
        foreign_keys=[category_id],
    )
