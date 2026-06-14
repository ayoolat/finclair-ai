import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.common.mixins.audit import AuditMixin
from app.common.enums.user import AuthProvider

if TYPE_CHECKING:
    from app.module.income.schema.income import Income
    from app.module.bank.schema.bank import Bank
    from app.module.expense.schema.expense import Expense
    from app.module.budget.schema.budget import Budget
    from app.module.user.schema.user_goal import UserGoal


class User(AuditMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    hashed_passcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    auth_provider: Mapped[str] = mapped_column(String(20), nullable=False, default=AuthProvider.EMAIL)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    goals: Mapped[list["UserGoal"]] = relationship(
        "UserGoal",
        cascade="all, delete-orphan",
        foreign_keys="UserGoal.user_id",
    )
    incomes: Mapped[list["Income"]] = relationship(
        "Income", back_populates="user", foreign_keys="Income.user_id", cascade="all, delete-orphan"
    )
    banks: Mapped[list["Bank"]] = relationship(
        "Bank", back_populates="user", foreign_keys="Bank.user_id", cascade="all, delete-orphan"
    )
    expenses: Mapped[list["Expense"]] = relationship(
        "Expense", back_populates="user", foreign_keys="Expense.user_id", cascade="all, delete-orphan"
    )
    budgets: Mapped[list["Budget"]] = relationship(
        "Budget", back_populates="user", foreign_keys="Budget.user_id", cascade="all, delete-orphan"
    )
