import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums.challenge import ChallengeStatus, ChallengeType
from app.database.session import Base

if TYPE_CHECKING:
    from app.module.category.schema.category import Category
    from app.module.challenge.schema.challenge_entry import ChallengeEntry
    from app.module.user.schema.user import User


class SavingsChallenge(Base):
    """
    A personal challenge — one user, one row; no group/participant concept.
    Covers three types (see ChallengeType), each giving the generic columns
    below a different meaning:

    - friday_savings: weekly_target/overall_target/total_saved are money;
      current_streak/longest_streak/last_entry_week track consecutive Fridays
      with a logged entry (ChallengeEntry rows).
    - no_spend: only current_streak/longest_streak/last_entry_week are used,
      tracking consecutive weeks with zero spend (auto-advanced by a
      scheduled job, no entries). weekly_target/overall_target/total_saved
      stay null/0; open-ended, no completion.
    - budget_category: target_category_id + overall_target (the spend cap)
      + current_period_spent (running spend, auto-updated) are used over a
      single start_date..end_date period; total_saved/weekly_target/streak
      fields stay null/0.
    """

    __tablename__ = "savings_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False, default=ChallengeType.FRIDAY_SAVINGS)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    weekly_target: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    overall_target: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    total_saved: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=Decimal(0))
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ISO "{year}-W{week}" of the last logged entry — used to detect consecutive
    # vs. skipped weeks without being sensitive to which day of the week it is.
    last_entry_week: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    target_category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    current_period_spent: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ChallengeStatus.ACTIVE)
    # When the challenge reached a terminal state (completed / failed /
    # cancelled); null while ACTIVE. Lets a monthly metric like the Finclar
    # Score attribute the outcome to the month it actually happened in.
    concluded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    category: Mapped[Optional["Category"]] = relationship("Category", foreign_keys=[target_category_id])
    entries: Mapped[list["ChallengeEntry"]] = relationship(
        "ChallengeEntry", back_populates="challenge", cascade="all, delete-orphan"
    )
