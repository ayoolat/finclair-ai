import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends
from sqlalchemy import Date, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.core.config import settings
from app.database.session import get_db
from app.module.challenge.schema.badge import Badge
from app.module.challenge.service.badge_service import BadgeService, get_badge_service
from app.module.expense.dto.expense import ExpenseStreakDayDto, ExpenseStreakResponseDto
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_streak import ExpenseStreak
from app.module.notification.service.push_service import PushService, get_push_service

# Consecutive days with at least one logged expense -> badge key. Mirrors the
# 5-day milestone in the streak card design, then scales like the weekly
# challenge streaks (STREAK_BADGE_WEEKS in challenge_entry_service.py) but
# tuned for daily logging cadence.
EXPENSE_STREAK_BADGE_DAYS = {
    3: "expense_streak_3_days",
    5: "expense_streak_5_days",
    7: "expense_streak_7_days",
    14: "expense_streak_14_days",
    30: "expense_streak_30_days",
    60: "expense_streak_60_days",
    100: "expense_streak_100_days",
}

_WEEKDAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


@dataclass
class StreakUpdate:
    current_streak: int
    longest_streak: int
    newly_awarded_badge: Optional[Badge]


class ExpenseStreakService:
    def __init__(self, db: AsyncSession, badges: BadgeService, push: PushService) -> None:
        self._db = db
        self._badges = badges
        self._push = push

    async def record_activity(self, user_id: uuid.UUID) -> StreakUpdate:
        """
        Called after an expense is successfully created. Does not commit —
        the caller owns the transaction, same contract as BadgeService.award.
        """
        streak = await self._db.scalar(select(ExpenseStreak).where(ExpenseStreak.user_id == user_id))
        if streak is None:
            streak = ExpenseStreak(user_id=user_id)
            self._db.add(streak)
            await self._db.flush()

        today = date.today()
        if streak.last_logged_date == today:
            # Already logged today — a 2nd/3rd expense the same day shouldn't
            # re-advance the streak or re-check badges.
            return StreakUpdate(streak.current_streak, streak.longest_streak, None)

        if streak.last_logged_date is not None and (today - streak.last_logged_date).days == 1:
            streak.current_streak += 1
        else:
            streak.current_streak = 1
        streak.longest_streak = max(streak.longest_streak, streak.current_streak)
        streak.last_logged_date = today

        newly_awarded_badge = None
        badge_key = EXPENSE_STREAK_BADGE_DAYS.get(streak.current_streak)
        if badge_key:
            newly_awarded_badge = await self._badges.award(user_id, badge_key)

        return StreakUpdate(streak.current_streak, streak.longest_streak, newly_awarded_badge)

    async def get_streak(self, user_id: uuid.UUID) -> Result[ExpenseStreakResponseDto]:
        streak = await self._db.scalar(select(ExpenseStreak).where(ExpenseStreak.user_id == user_id))
        today = date.today()

        # No background job resets a lapsed streak, so the stored value can be
        # stale — recompute what's actually still alive for display.
        if streak is None or streak.last_logged_date is None:
            effective_streak = 0
            longest_streak = streak.longest_streak if streak else 0
            last_logged_date = None
        elif (today - streak.last_logged_date).days <= 1:
            effective_streak = streak.current_streak
            longest_streak = streak.longest_streak
            last_logged_date = streak.last_logged_date
        else:
            effective_streak = 0
            longest_streak = streak.longest_streak
            last_logged_date = streak.last_logged_date

        window_start = today - timedelta(days=6)
        rows = await self._db.execute(
            select(cast(Expense.expense_date, Date)).where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= window_start,
                Expense.expense_date < today + timedelta(days=1),
            ).distinct()
        )
        logged_dates = {row[0] for row in rows.all()}

        days = [
            ExpenseStreakDayDto(
                date=d,
                day_label=_WEEKDAY_LABELS[d.weekday()],
                logged=d in logged_dates,
                is_today=d == today,
            )
            for d in (window_start + timedelta(days=i) for i in range(7))
        ]

        return Result.ok(
            ExpenseStreakResponseDto(
                current_streak=effective_streak,
                longest_streak=longest_streak,
                last_logged_date=last_logged_date,
                logged_today=today in logged_dates,
                days=days,
            )
        )

    async def simulate_streak(self, user_id: uuid.UUID, days: int) -> Result[ExpenseStreakResponseDto]:
        if not settings.debug:
            return Result.fail("Not found.", status_code=404)
        if days < 1:
            return Result.fail("days must be at least 1.", status_code=422)

        streak = await self._db.scalar(select(ExpenseStreak).where(ExpenseStreak.user_id == user_id))
        if streak is None:
            streak = ExpenseStreak(user_id=user_id)
            self._db.add(streak)
            await self._db.flush()

        streak.current_streak = days
        streak.longest_streak = max(streak.longest_streak, days)
        streak.last_logged_date = date.today()

        newly_awarded_badge = None
        badge_key = EXPENSE_STREAK_BADGE_DAYS.get(days)
        if badge_key:
            newly_awarded_badge = await self._badges.award(user_id, badge_key)

        await self._db.commit()

        if newly_awarded_badge:
            await self._push.send_to_user(
                user_id,
                title=f"🔥 {days}-day streak!",
                body=f"You've logged expenses {days} days in a row. New badge: {newly_awarded_badge.name}.",
                data={"type": "expense_streak_badge", "current_streak": str(days)},
            )

        return await self.get_streak(user_id)


def get_expense_streak_service(
    db: AsyncSession = Depends(get_db),
    badges: BadgeService = Depends(get_badge_service),
    push: PushService = Depends(get_push_service),
) -> ExpenseStreakService:
    return ExpenseStreakService(db, badges, push)
