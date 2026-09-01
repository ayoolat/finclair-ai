import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.module.user.schema.user import User


class FinclarScoreSnapshot(Base):
    """
    One month's Finclar Score for a user. Written lazily: the score for a month
    is computed on read and upserted here, so history builds up as the user
    checks in. Past months are frozen once written (their inputs can no longer
    change); the current month is always recomputed and overwritten.
    """

    __tablename__ = "finclar_score_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "period_start", name="uq_finclar_scores_user_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    budget_adherence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    savings_consistency: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    tracking_consistency: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    goal_achievement: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
