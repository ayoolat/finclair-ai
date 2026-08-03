import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import Depends, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.dto.pagination import PageQueryDto
from app.common.enums.challenge import ChallengeStatus, EntryVerificationLevel
from app.common.ocr.factory import get_ocr_provider
from app.common.response import PaginatedResponse, Result
from app.common.storage.factory import get_storage_provider
from app.core.config import settings
from app.database.session import get_db
from app.module.challenge.dto.challenge import (
    ChallengeEntryResponseDto,
    ChallengeResponseDto,
    RecordEntryDto,
)
from app.module.challenge.schema.challenge import SavingsChallenge
from app.module.challenge.schema.challenge_entry import ChallengeEntry
from app.module.challenge.service._helpers import iso_week_key, receipt_amount_matches, weeks_between
from app.module.challenge.service.badge_service import BadgeService, get_badge_service
from app.module.notification.service.push_service import PushService, get_push_service

# Consecutive Fridays logged in a row -> badge key. Chosen to land roughly at
# 1 month / 1 quarter / 6 months / 1 year of an unbroken weekly habit.
STREAK_BADGE_WEEKS = {
    4: "streak_4_weeks",
    12: "streak_12_weeks",
    26: "streak_26_weeks",
    52: "streak_52_weeks",
}


class ChallengeEntryService:
    def __init__(self, db: AsyncSession, badges: BadgeService, push: PushService) -> None:
        self._db = db
        self._badges = badges
        self._push = push
        self._storage = get_storage_provider()
        self._ocr = get_ocr_provider()

    async def record_entry(
        self,
        user_id: uuid.UUID,
        challenge_id: uuid.UUID,
        dto: RecordEntryDto,
        receipt: Optional[UploadFile] = None,
    ) -> Result[ChallengeEntryResponseDto]:
        challenge = await self._db.scalar(
            select(SavingsChallenge).where(
                SavingsChallenge.id == challenge_id, SavingsChallenge.user_id == user_id
            )
        )
        if challenge is None:
            return Result.fail("Challenge not found.", error_code="NOT_FOUND", status_code=404)
        if challenge.status != ChallengeStatus.ACTIVE:
            return Result.fail("This challenge is no longer active.", status_code=400)

        if dto.amount is None and receipt is None:
            return Result.fail(
                "Enter an amount or upload a bank receipt / bank alert screenshot.",
                error_code="ENTRY_REQUIRED",
                status_code=422,
            )

        current_week = iso_week_key(date.today())
        if challenge.last_entry_week == current_week:
            return Result.fail(
                "You've already logged savings for this week.",
                error_code="ALREADY_LOGGED_THIS_WEEK",
                status_code=409,
            )

        file_url: Optional[str] = None
        verification_level = EntryVerificationLevel.SELF_REPORTED
        final_amount = dto.amount
        if receipt is not None:
            data = await receipt.read()
            content_type = receipt.content_type or "image/jpeg"

            try:
                ocr_result = await self._ocr.parse_receipt(data, content_type)
            except ValueError as exc:
                return Result.fail(str(exc), error_code="INVALID_IMAGE", status_code=400)
            except RuntimeError as exc:
                return Result.fail(
                    f"Could not read the receipt: {exc}", error_code="OCR_FAILED", status_code=502
                )

            if dto.amount is not None and not receipt_amount_matches(dto.amount, ocr_result.total):
                return Result.fail(
                    f"The receipt shows {ocr_result.total}, which doesn't match the "
                    f"{dto.amount} you entered. Please correct the amount or upload the matching receipt.",
                    error_code="RECEIPT_AMOUNT_MISMATCH",
                    status_code=422,
                )
            final_amount = dto.amount if dto.amount is not None else ocr_result.total

            ext = (receipt.filename or "file").rsplit(".", 1)[-1]
            file_name = f"{uuid.uuid4()}.{ext}"
            await self._storage.upload(f"challenges/{challenge_id}/receipts", file_name, data, content_type)
            file_url = self._storage.public_url(f"challenges/{challenge_id}/receipts", file_name)
            verification_level = EntryVerificationLevel.EVIDENCE_BACKED

        if final_amount is not None:
            challenge.total_saved = Decimal(str(challenge.total_saved or 0)) + final_amount

        if challenge.last_entry_week is None:
            challenge.current_streak = 1
        else:
            gap = weeks_between(challenge.last_entry_week, current_week)
            challenge.current_streak = challenge.current_streak + 1 if gap == 1 else 1
        challenge.longest_streak = max(challenge.longest_streak, challenge.current_streak)
        challenge.last_entry_week = current_week

        entry = ChallengeEntry(
            challenge_id=challenge.id,
            user_id=user_id,
            amount=final_amount,
            verification_level=verification_level,
            note=dto.note,
            file_url=file_url,
        )
        self._db.add(entry)

        newly_awarded_badge = None
        streak_badge_key = STREAK_BADGE_WEEKS.get(challenge.current_streak)
        if streak_badge_key:
            newly_awarded_badge = await self._badges.award(
                user_id, streak_badge_key, challenge_id=challenge.id
            )

        just_completed = (
            challenge.status == ChallengeStatus.ACTIVE
            and challenge.overall_target is not None
            and Decimal(str(challenge.total_saved)) >= Decimal(str(challenge.overall_target))
        )
        if just_completed:
            challenge.status = ChallengeStatus.COMPLETED
            await self._badges.award(user_id, "friday_savings_goal_reached", challenge_id=challenge.id)

        await self._db.commit()
        await self._db.refresh(entry)

        if newly_awarded_badge:
            await self._push.send_to_user(
                user_id,
                title=f"🔥 {challenge.current_streak}-week streak!",
                body=(
                    f"You've kept up '{challenge.name}' for {challenge.current_streak} weeks straight. "
                    f"New badge: {newly_awarded_badge.name}."
                ),
                data={"type": "streak_badge", "challenge_id": str(challenge.id)},
            )
        if just_completed:
            await self._push.send_to_user(
                user_id,
                title="Challenge complete! 🎉",
                body=f"You hit your savings goal for '{challenge.name}'.",
                data={"type": "challenge_completed", "challenge_id": str(challenge.id)},
            )

        return Result.ok(ChallengeEntryResponseDto.model_validate(entry), status_code=201)


    async def simulate_streak(
        self, user_id: uuid.UUID, challenge_id: uuid.UUID, weeks: int
    ) -> Result[ChallengeResponseDto]:
        if not settings.debug:
            return Result.fail("Not found.", status_code=404)
        if weeks < 1:
            return Result.fail("weeks must be at least 1.", status_code=422)

        challenge = await self._db.scalar(
            select(SavingsChallenge).where(
                SavingsChallenge.id == challenge_id, SavingsChallenge.user_id == user_id
            )
        )
        if challenge is None:
            return Result.fail("Challenge not found.", error_code="NOT_FOUND", status_code=404)

        challenge.current_streak = weeks
        challenge.longest_streak = max(challenge.longest_streak, weeks)
        challenge.last_entry_week = iso_week_key(date.today())

        newly_awarded_badge = None
        streak_badge_key = STREAK_BADGE_WEEKS.get(weeks)
        if streak_badge_key:
            newly_awarded_badge = await self._badges.award(
                user_id, streak_badge_key, challenge_id=challenge.id
            )

        await self._db.commit()
        await self._db.refresh(challenge)

        if newly_awarded_badge:
            await self._push.send_to_user(
                user_id,
                title=f"🔥 {weeks}-week streak!",
                body=(
                    f"You've kept up '{challenge.name}' for {weeks} weeks straight. "
                    f"New badge: {newly_awarded_badge.name}."
                ),
                data={"type": "streak_badge", "challenge_id": str(challenge.id)},
            )

        return Result.ok(ChallengeResponseDto.model_validate(challenge))

    async def send_test_reminder(self, user_id: uuid.UUID, challenge_id: uuid.UUID) -> Result[None]:
        if not settings.debug:
            return Result.fail("Not found.", status_code=404)

        challenge = await self._db.scalar(
            select(SavingsChallenge).where(
                SavingsChallenge.id == challenge_id, SavingsChallenge.user_id == user_id
            )
        )
        if challenge is None:
            return Result.fail("Challenge not found.", error_code="NOT_FOUND", status_code=404)

        body = (
            f"You're on a {challenge.current_streak}-week streak — log today's savings to keep it alive."
            if challenge.current_streak > 0
            else f"Time to save for '{challenge.name}'. Log today's contribution to start your streak."
        )
        await self._push.send_to_user(
            user_id,
            title="It's Friday! 💰",
            body=body,
            data={"type": "friday_reminder", "challenge_id": str(challenge.id)},
        )
        return Result.ok(None)

    async def list_entries(
        self, user_id: uuid.UUID, challenge_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[ChallengeEntryResponseDto]]:
        owns = await self._db.scalar(
            select(SavingsChallenge.id).where(
                SavingsChallenge.id == challenge_id, SavingsChallenge.user_id == user_id
            )
        )
        if owns is None:
            return Result.fail("Challenge not found.", error_code="NOT_FOUND", status_code=404)

        base = select(ChallengeEntry).where(ChallengeEntry.challenge_id == challenge_id)
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = await self._db.execute(
            base.order_by(ChallengeEntry.recorded_at.desc()).offset(filters.offset).limit(filters.page_size)
        )
        dtos = [ChallengeEntryResponseDto.model_validate(e) for e in rows.scalars().all()]
        return Result.ok(
            PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total)
        )


def get_challenge_entry_service(
    db: AsyncSession = Depends(get_db),
    badges: BadgeService = Depends(get_badge_service),
    push: PushService = Depends(get_push_service),
) -> ChallengeEntryService:
    return ChallengeEntryService(db, badges, push)
