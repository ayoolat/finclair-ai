import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.module.challenge.schema.badge import Badge
    from app.module.user.schema.user import User


class UserBadge(Base):
    """
    A single award of a badge to a user. `earned_period` is a free-form dedup
    key BadgeService uses to allow a badge to be earned again later without
    duplicating it within the same period — "2026-08" for a monthly budget
    badge, an ISO week/date for a weekly one, or null for a one-time badge
    (e.g. a streak milestone).
    """

    __tablename__ = "user_badges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    badge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("badges.id"), nullable=False
    )
    challenge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("savings_challenges.id"), nullable=True
    )
    earned_period: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    badge: Mapped["Badge"] = relationship("Badge", foreign_keys=[badge_id])
