import uuid
from typing import Optional

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class Badge(Base):
    """Static catalog of earnable badges — seeded at startup, see core/startup.py."""

    __tablename__ = "badges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    icon_name: Mapped[str] = mapped_column(String(100), nullable=True)
    # What this badge is awarded for: "friday_savings", "streak", "no_spend_weekend",
    # "budget" — null = general. Not an FK; some badges (budget/no-spend) come from
    # the budget module's alert checks, not from a SavingsChallenge at all.
    category: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
