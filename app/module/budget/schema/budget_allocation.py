import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.mixins.audit import AuditMixin
from app.database.session import Base

if TYPE_CHECKING:
    from app.module.budget.schema.budget import Budget
    from app.module.category.schema.category import Category


class BudgetAllocation(AuditMixin, Base):
    __tablename__ = "budget_allocations"
    __table_args__ = (
        UniqueConstraint("budget_id", "category_id", name="uq_budget_allocations_budget_category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("budgets.id"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    amount_allocated: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    budget: Mapped["Budget"] = relationship("Budget", back_populates="allocations", foreign_keys=[budget_id])
    category: Mapped["Category"] = relationship("Category", foreign_keys=[category_id])
