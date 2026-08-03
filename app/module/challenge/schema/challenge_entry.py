import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums.challenge import EntryVerificationLevel
from app.database.session import Base

if TYPE_CHECKING:
    from app.module.challenge.schema.challenge import SavingsChallenge


class ChallengeEntry(Base):
    """
    One weekly submission toward a SavingsChallenge — either a self-reported
    amount, or a bank receipt / bank alert screenshot as evidence (or both).
    """

    __tablename__ = "challenge_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("savings_challenges.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    amount: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    verification_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EntryVerificationLevel.SELF_REPORTED
    )
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    challenge: Mapped["SavingsChallenge"] = relationship("SavingsChallenge", back_populates="entries")
