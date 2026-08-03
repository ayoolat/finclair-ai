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
    from app.module.challenge.schema.challenge_entry import ChallengeEntry
    from app.module.user.schema.user import User


class SavingsChallenge(Base):
    """
    A personal savings challenge — e.g. "save something every Friday". One user,
    one challenge; no group/participant concept. Streak state lives directly on
    the row since there's exactly one participant (the owner).
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
    start_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ChallengeStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    entries: Mapped[list["ChallengeEntry"]] = relationship(
        "ChallengeEntry", back_populates="challenge", cascade="all, delete-orphan"
    )
