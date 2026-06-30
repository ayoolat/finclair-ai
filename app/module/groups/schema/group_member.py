import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.module.user.schema.user import User
    from app.module.groups.schema.group import Group
    from app.module.groups.schema.group_savings_entry import GroupSavingsEntry


class GroupMember(Base):
    __tablename__ = "group_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    target_amount: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    contributed_amount: Mapped[float] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal(0)
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    group: Mapped["Group"] = relationship("Group", back_populates="members")
    savings_entries: Mapped[list["GroupSavingsEntry"]] = relationship(
        "GroupSavingsEntry", back_populates="member"
    )
