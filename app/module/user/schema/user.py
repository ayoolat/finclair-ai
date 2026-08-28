import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, SmallInteger, String
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
    from app.module.subscription.schema.subscription import Subscription


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
    profile_icon: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # What the user wants to be called (set during onboarding) — distinct from the
    # unique login handle in `username`, which can be an unnatural thing to be
    # addressed by (e.g. "chinonso_test") in conversational surfaces like Clara.
    preferred_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Personalized daily expense-review reminder. The financial day is always
    # 00:00–23:59 Africa/Lagos; this only moves *when* the nudge is sent, never
    # the day boundary. The app maps its named presets (Morning / Afternoon /
    # Evening / Late Night / Custom) to a concrete hour+minute and sends that.
    reminder_hour: Mapped[int] = mapped_column(SmallInteger, default=21, nullable=False)
    reminder_minute: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    daily_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def display_name(self) -> str:
        return self.preferred_name or self.username

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
    subscription: Mapped["Subscription | None"] = relationship(
        "Subscription",
        back_populates="user",
        foreign_keys="Subscription.user_id",
        cascade="all, delete-orphan",
        uselist=False,
    )
