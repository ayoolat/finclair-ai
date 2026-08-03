import uuid
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.challenge import ChallengeStatus
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.challenge.dto.challenge import (
    ChallengeFilterDto,
    ChallengeResponseDto,
    CreateChallengeDto,
    UpdateChallengeDto,
)
from app.module.challenge.schema.challenge import SavingsChallenge
from app.module.challenge.service.badge_service import BadgeService, get_badge_service


class ChallengeService:
    def __init__(self, db: AsyncSession, badges: BadgeService) -> None:
        self._db = db
        self._badges = badges

    async def create_challenge(
        self, user_id: uuid.UUID, dto: CreateChallengeDto
    ) -> Result[ChallengeResponseDto]:
        existing = await self._db.scalar(
            select(SavingsChallenge).where(
                SavingsChallenge.user_id == user_id,
                SavingsChallenge.status == ChallengeStatus.ACTIVE,
            )
        )
        if existing is not None:
            return Result.fail(
                "You already have an active savings challenge.",
                error_code="ACTIVE_CHALLENGE_EXISTS",
                status_code=409,
            )

        challenge = SavingsChallenge(
            user_id=user_id,
            name=dto.name,
            weekly_target=dto.weekly_target,
            overall_target=dto.overall_target,
            end_date=dto.end_date,
        )
        self._db.add(challenge)
        await self._db.flush()

        await self._badges.award(user_id, "first_challenge")

        await self._db.commit()
        await self._db.refresh(challenge)
        return Result.ok(ChallengeResponseDto.model_validate(challenge), status_code=201)

    async def list_challenges(
        self, user_id: uuid.UUID, filters: ChallengeFilterDto
    ) -> Result[PaginatedResponse[ChallengeResponseDto]]:
        base = select(SavingsChallenge).where(SavingsChallenge.user_id == user_id)
        if filters.status:
            base = base.where(SavingsChallenge.status == filters.status)

        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = await self._db.execute(
            base.order_by(SavingsChallenge.created_at.desc())
            .offset(filters.offset)
            .limit(filters.page_size)
        )
        dtos = [ChallengeResponseDto.model_validate(c) for c in rows.scalars().all()]
        return Result.ok(
            PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total)
        )

    async def get_challenge(
        self, user_id: uuid.UUID, challenge_id: uuid.UUID
    ) -> Result[ChallengeResponseDto]:
        challenge = await self._load(user_id, challenge_id)
        if challenge is None:
            return Result.fail("Challenge not found.", error_code="NOT_FOUND", status_code=404)
        return Result.ok(ChallengeResponseDto.model_validate(challenge))

    async def update_challenge(
        self, user_id: uuid.UUID, challenge_id: uuid.UUID, dto: UpdateChallengeDto
    ) -> Result[ChallengeResponseDto]:
        challenge = await self._load(user_id, challenge_id)
        if challenge is None:
            return Result.fail("Challenge not found.", error_code="NOT_FOUND", status_code=404)

        if dto.name is not None:
            challenge.name = dto.name
        if dto.weekly_target is not None:
            challenge.weekly_target = dto.weekly_target
        if dto.overall_target is not None:
            challenge.overall_target = dto.overall_target
        if dto.end_date is not None:
            challenge.end_date = dto.end_date

        await self._db.commit()
        await self._db.refresh(challenge)
        return Result.ok(ChallengeResponseDto.model_validate(challenge))

    async def cancel_challenge(self, user_id: uuid.UUID, challenge_id: uuid.UUID) -> Result[None]:
        challenge = await self._load(user_id, challenge_id)
        if challenge is None:
            return Result.fail("Challenge not found.", error_code="NOT_FOUND", status_code=404)
        if challenge.status != ChallengeStatus.ACTIVE:
            return Result.fail("Only an active challenge can be cancelled.", status_code=400)

        challenge.status = ChallengeStatus.CANCELLED
        await self._db.commit()
        return Result.ok(None)

    async def _load(self, user_id: uuid.UUID, challenge_id: uuid.UUID) -> Optional[SavingsChallenge]:
        return await self._db.scalar(
            select(SavingsChallenge).where(
                SavingsChallenge.id == challenge_id, SavingsChallenge.user_id == user_id
            )
        )


def get_challenge_service(
    db: AsyncSession = Depends(get_db), badges: BadgeService = Depends(get_badge_service)
) -> ChallengeService:
    return ChallengeService(db, badges)
