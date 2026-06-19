import uuid
from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.mixins.audit import AuditMixin
from app.common.enums.income import IncomeReoccurrence
from app.database.session import Base

if TYPE_CHECKING:
    from app.module.user.schema.user import User
    from app.module.income.schema.income_source import IncomeSource
    from app.module.bank.schema.bank import Bank


class Income(AuditMixin, Base):
    __tablename__ = "incomes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("income_sources.id"), nullable=False)
    bank_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("banks.id"), nullable=True)
    reoccurrence: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="incomes", foreign_keys=[user_id])
    source: Mapped["IncomeSource"] = relationship("IncomeSource", foreign_keys=[source_id])
    bank: Mapped[Optional["Bank"]] = relationship("Bank", foreign_keys=[bank_id])

    @property
    def reoccurrence_enum(self) -> IncomeReoccurrence:
        return IncomeReoccurrence(self.reoccurrence)
