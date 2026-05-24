import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class UserGoal(Base):
    __tablename__ = "user_goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True, nullable=False
    )
    # Stored as UserGoalType enum value string
    goal: Mapped[str] = mapped_column(String(50), primary_key=True, nullable=False)
