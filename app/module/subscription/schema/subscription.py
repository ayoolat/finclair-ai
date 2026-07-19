import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.common.mixins.audit import AuditMixin

if TYPE_CHECKING:
    from app.module.user.schema.user import User


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    compare_at_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="NGN")
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Subscription(AuditMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    plan_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("subscription_plans.code"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    compare_at_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="NGN")

    paystack_customer_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    paystack_authorization_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    paystack_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    trial_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    past_due_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(
        "User", back_populates="subscription", foreign_keys=[user_id]
    )


class SubscriptionTransaction(Base):
    __tablename__ = "subscription_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False
    )
    paystack_reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="NGN")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    gateway_response: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
