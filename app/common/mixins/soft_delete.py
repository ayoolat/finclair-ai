from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """
    Provides soft-delete semantics via deleted_at timestamp.
    Queries must filter .where(Model.deleted_at.is_(None)) to exclude deleted records.
    """

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
