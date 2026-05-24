import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.common.mixins.audit import AuditMixin
from app.common.enums.expense import ExpenseType, ExpenseDirection, ExpenseStatus

if TYPE_CHECKING:
    from app.module.user.schema.user import User
    from app.module.category.schema.category import Category
    from app.module.expense.schema.expense_item import ExpenseItem


class Expense(AuditMixin, Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    expense_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="expenses",
        foreign_keys=[user_id],
    )
    categories: Mapped[list["Category"]] = relationship(
        "Category",
        secondary="expense_categories",
        back_populates="expenses",
    )
    items: Mapped[list["ExpenseItem"]] = relationship(
        "ExpenseItem",
        back_populates="expense",
        cascade="all, delete-orphan",
    )

    @property
    def type_enum(self) -> ExpenseType:
        return ExpenseType(self.type)

    @property
    def direction_enum(self) -> ExpenseDirection:
        return ExpenseDirection(self.direction)

    @property
    def status_enum(self) -> ExpenseStatus:
        return ExpenseStatus(self.status)
