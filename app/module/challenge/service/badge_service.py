import uuid
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.response import Result
from app.database.session import get_db
from app.module.challenge.dto.challenge import BadgeResponseDto, UserBadgeResponseDto
from app.module.challenge.schema.badge import Badge
from app.module.challenge.schema.user_badge import UserBadge


class BadgeService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_catalog(self) -> Result[list[BadgeResponseDto]]:
        rows = await self._db.execute(select(Badge).order_by(Badge.category, Badge.name))
        return Result.ok([BadgeResponseDto.model_validate(b) for b in rows.scalars().all()])

    async def list_user_badges(self, user_id: uuid.UUID) -> Result[list[UserBadgeResponseDto]]:
        rows = await self._db.execute(
            select(UserBadge)
            .options(selectinload(UserBadge.badge))
            .where(UserBadge.user_id == user_id)
            .order_by(UserBadge.earned_at.desc())
        )
        return Result.ok([UserBadgeResponseDto.model_validate(ub) for ub in rows.scalars().all()])

    async def award(
        self,
        user_id: uuid.UUID,
        badge_key: str,
        *,
        challenge_id: Optional[uuid.UUID] = None,
        period: Optional[str] = None,
    ) -> Optional[Badge]:
        """
        Idempotently award a badge — no-ops if the user already holds it for
        this period. Returns the Badge only when this call actually granted
        it, so callers know whether to fire a "new badge" push. Does not
        commit; the caller owns the transaction.
        """
        badge = await self._db.scalar(select(Badge).where(Badge.key == badge_key))
        if badge is None:
            return None

        period_clause = (
            UserBadge.earned_period == period if period is not None else UserBadge.earned_period.is_(None)
        )
        existing = await self._db.scalar(
            select(UserBadge).where(
                UserBadge.user_id == user_id,
                UserBadge.badge_id == badge.id,
                period_clause,
            )
        )
        if existing is not None:
            return None

        self._db.add(
            UserBadge(
                user_id=user_id,
                badge_id=badge.id,
                challenge_id=challenge_id,
                earned_period=period,
            )
        )
        return badge


def get_badge_service(db: AsyncSession = Depends(get_db)) -> BadgeService:
    return BadgeService(db)
