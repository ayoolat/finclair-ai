import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.common.mixins.audit import AuditMixin

if TYPE_CHECKING:
    from app.module.user.schema.user import User


class Budget(AuditMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("amount_allocated >= 0", name="ck_budgets_allocated_non_negative"),
        CheckConstraint("spent >= 0", name="ck_budgets_spent_non_negative"),
        CheckConstraint("end_date >= start_date", name="ck_budgets_end_after_start"),
    )

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
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_allocated: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    spent: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    remaining: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    user: Mapped["User"] = relationship(
        "User",
        back_populates="budgets",
        foreign_keys=[user_id],
    )
