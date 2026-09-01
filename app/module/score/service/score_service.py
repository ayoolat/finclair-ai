"""
The Finclar Score — a 0-100 financial discipline metric, computed per calendar
month from four weighted components (spec §3.3):

    Budget Adherence     40%  — % of budget categories kept within their limit
    Savings Consistency  30%  — how often, and how evenly, money is set aside
    Tracking Consistency 20%  — days with a logged expense / days elapsed
    Goal Achievement     10%  — savings challenges completed / challenges set

A component with no data to judge (no budget yet, never saved, no challenges)
is dropped and its weight redistributed over the components that do have data,
so a new user isn't scored 0 for features they haven't reached yet.
"""

import calendar
import statistics
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.challenge import ChallengeStatus
from app.common.finance_queries import expense_total_for_category
from app.common.response import Result
from app.database.session import get_db
from app.module.budget.schema.budget import Budget
from app.module.budget.schema.budget_allocation import BudgetAllocation
from app.module.category.schema.category import Category
from app.module.challenge.schema.challenge import SavingsChallenge
from app.module.challenge.schema.challenge_entry import ChallengeEntry
from app.module.challenge.service.badge_service import BadgeService
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.score.dto.score import (
    FinclarScoreDto,
    ScoreComponentDto,
    ScoreHistoryPointDto,
    ScoreTierDto,
)
from app.module.score.schema.finclar_score import FinclarScoreSnapshot
from app.module.user.schema.user import User

# Same two categories Money Wrapped treats as "money set aside" rather than spent.
SAVINGS_CATEGORY_NAMES = ["Savings", "Investment"]

HISTORY_MONTHS = 6

WEIGHT_BUDGET = 40.0
WEIGHT_SAVINGS = 30.0
WEIGHT_TRACKING = 20.0
WEIGHT_GOALS = 10.0

# Of the savings component, how much is "did you save this week at all" vs.
# "were the amounts steady" — frequency is the behaviour we actually want.
SAVINGS_FREQUENCY_SHARE = 0.7

TIERS = [
    ScoreTierDto(key="getting_started", name="Getting Started", description="You are just beginning to build habits.", min_score=0, max_score=24),
    ScoreTierDto(key="finding_footing", name="Finding Your Feet", description="Some habits are forming — keep going.", min_score=25, max_score=49),
    ScoreTierDto(key="on_track", name="On Track", description="You are managing money consistently.", min_score=50, max_score=69),
    ScoreTierDto(key="disciplined", name="Disciplined", description="Strong, steady financial discipline.", min_score=70, max_score=84),
    ScoreTierDto(key="elite", name="Financially Elite", description="Top-tier discipline. Outstanding.", min_score=85, max_score=100),
]

# Score milestones that unlock a badge. Seeded in app/core/startup.py.
SCORE_BADGES = [(50, "score_on_track"), (70, "score_disciplined"), (85, "score_elite")]


def _tier_for(score: float) -> ScoreTierDto:
    for tier in TIERS:
        if score <= tier.max_score:
            return tier
    return TIERS[-1]


def _next_tier(tier: ScoreTierDto) -> Optional[ScoreTierDto]:
    index = TIERS.index(tier)
    return TIERS[index + 1] if index + 1 < len(TIERS) else None


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


class _Component:
    def __init__(self, key: str, name: str, description: str, weight: float) -> None:
        self.key = key
        self.name = name
        self.description = description
        self.weight = weight
        self.score = 0.0
        self.has_data = False
        self.detail = ""

    def set(self, score: float, detail: str) -> None:
        self.score = max(0.0, min(100.0, score))
        self.has_data = True
        self.detail = detail

    def no_data(self, detail: str) -> None:
        self.score = 0.0
        self.has_data = False
        self.detail = detail


class ScoreService:
    def __init__(self, db: AsyncSession, badges: BadgeService) -> None:
        self._db = db
        self._badges = badges

    async def get_score(
        self, user_id: uuid.UUID, year: Optional[int] = None, month: Optional[int] = None
    ) -> Result[FinclarScoreDto]:
        user = await self._db.scalar(select(User).where(User.id == user_id))
        if user is None:
            return Result.fail("User not found.", error_code="NOT_FOUND", status_code=404)

        today = date.today()
        year = year or today.year
        month = month or today.month
        if not 1 <= month <= 12:
            return Result.fail("Month must be between 1 and 12.", error_code="INVALID_MONTH", status_code=400)
        if (year, month) > (today.year, today.month):
            return Result.fail("Cannot score a future month.", error_code="FUTURE_MONTH", status_code=400)

        components, score, has_data = await self._compute(user_id, year, month, today)
        await self._store(user_id, year, month, score, components)

        history = await self._history(user_id, year, month, today)
        previous = next((p.score for p in history if (p.year, p.month) == _shift_month(year, month, -1)), None)

        if has_data:
            await self._award_score_badges(user_id, score)
        await self._db.commit()

        tier = _tier_for(score)
        upcoming = _next_tier(tier)
        period_start, period_end = _month_bounds(year, month)

        return Result.ok(
            FinclarScoreDto(
                year=year,
                month=month,
                label=f"{calendar.month_name[month]} {year}",
                period_start=period_start,
                period_end=period_end,
                score=score,
                previous_score=previous,
                delta=round(score - previous, 1) if previous is not None else None,
                has_data=has_data,
                tier=tier,
                next_tier=upcoming,
                points_to_next_tier=round(upcoming.min_score - score, 1) if upcoming else None,
                components=components,
                tiers=TIERS,
                history=history,
            )
        )

    async def _compute(
        self, user_id: uuid.UUID, year: int, month: int, today: date
    ) -> tuple[list[ScoreComponentDto], float, bool]:
        period_start, period_end = _month_bounds(year, month)
        dt_start = datetime(year, month, 1)
        dt_end = datetime(period_end.year, period_end.month, period_end.day, 23, 59, 59)

        budget = _Component("budget_adherence", "Budget adherence", "Staying within your budget limits.", WEIGHT_BUDGET)
        savings = _Component("savings_consistency", "Savings consistency", "Saving regularly, in steady amounts.", WEIGHT_SAVINGS)
        tracking = _Component("tracking_consistency", "Tracking consistency", "Logging your expenses every day.", WEIGHT_TRACKING)
        goals = _Component("goal_achievement", "Goal achievement", "Finishing the challenges you start.", WEIGHT_GOALS)

        await self._score_budget(budget, user_id, period_start, dt_start, dt_end)
        await self._score_savings(savings, user_id, period_start, period_end, dt_start, dt_end)
        await self._score_tracking(tracking, user_id, period_start, period_end, dt_start, dt_end, today)
        await self._score_goals(goals, user_id, period_start, period_end)

        parts = [budget, savings, tracking, goals]
        scored = [c for c in parts if c.has_data]
        total_weight = sum(c.weight for c in scored)
        score = round(sum(c.weight * c.score for c in scored) / total_weight, 1) if total_weight else 0.0

        dtos = []
        for c in parts:
            effective = (c.weight / total_weight * 100) if (total_weight and c.has_data) else 0.0
            dtos.append(
                ScoreComponentDto(
                    key=c.key,
                    name=c.name,
                    description=c.description,
                    weight=c.weight,
                    score=round(c.score, 1),
                    points=round(effective * c.score / 100, 1),
                    max_points=round(effective, 1),
                    has_data=c.has_data,
                    detail=c.detail,
                )
            )
        return dtos, score, bool(scored)

    async def _score_budget(
        self, component: _Component, user_id: uuid.UUID, period_start: date, dt_start: datetime, dt_end: datetime
    ) -> None:
        budget = await self._db.scalar(
            select(Budget).where(Budget.user_id == user_id, Budget.start_date == period_start)
        )
        if budget is None:
            component.no_data("No budget set for this month.")
            return

        rows = await self._db.execute(
            select(BudgetAllocation.category_id, BudgetAllocation.amount_allocated).where(
                BudgetAllocation.budget_id == budget.id
            )
        )
        allocations = rows.all()

        if not allocations:
            allocated = float(budget.amount_allocated)
            spent = float(budget.spent)
            if allocated <= 0:
                component.no_data("No budget set for this month.")
                return
            ratio = spent / allocated
            score = 100.0 if ratio <= 1 else max(0.0, 100.0 - (ratio - 1) * 200)
            component.set(score, f"{'Within' if ratio <= 1 else 'Over'} your overall budget.")
            return

        spends = [
            await expense_total_for_category(self._db, user_id, cat_id, dt_start, dt_end)
            for cat_id, _ in allocations
        ]
        within = sum(1 for (_, limit), spent in zip(allocations, spends) if spent <= float(limit))
        total = len(allocations)
        component.set(
            within / total * 100,
            f"{within} of {total} budget categories kept within limit.",
        )

    async def _score_savings(
        self,
        component: _Component,
        user_id: uuid.UUID,
        period_start: date,
        period_end: date,
        dt_start: datetime,
        dt_end: datetime,
    ) -> None:
        entry_rows = await self._db.execute(
            select(ChallengeEntry.recorded_at, ChallengeEntry.amount).where(
                ChallengeEntry.user_id == user_id,
                ChallengeEntry.recorded_at >= dt_start,
                ChallengeEntry.recorded_at <= dt_end,
            )
        )
        savings_rows = await self._db.execute(
            select(Expense.expense_date, Expense.amount)
            .join(expense_categories, expense_categories.c.expense_id == Expense.id)
            .join(Category, Category.id == expense_categories.c.category_id)
            .where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= dt_start,
                Expense.expense_date <= dt_end,
                func.lower(Category.name).in_([n.lower() for n in SAVINGS_CATEGORY_NAMES]),
            )
        )

        per_week: dict[int, float] = {}
        for when, amount in list(entry_rows.all()) + list(savings_rows.all()):
            week = ((when.date() if isinstance(when, datetime) else when) - period_start).days // 7
            per_week[week] = per_week.get(week, 0.0) + float(amount or 0)

        total_weeks = ((period_end - period_start).days // 7) + 1

        if not per_week:
            ever_saved = await self._db.scalar(
                select(func.count())
                .select_from(SavingsChallenge)
                .where(SavingsChallenge.user_id == user_id, SavingsChallenge.start_date <= period_end)
            )
            if not ever_saved:
                component.no_data("You haven't started saving in the app yet.")
            else:
                component.set(0.0, f"No savings recorded in any of the {total_weeks} weeks.")
            return

        weeks_saved = len(per_week)
        frequency = weeks_saved / total_weeks

        amounts = [v for v in per_week.values() if v > 0]
        if len(amounts) < 2:
            evenness = 1.0
        else:
            mean = statistics.fmean(amounts)
            spread = (statistics.pstdev(amounts) / mean) if mean > 0 else 1.0
            evenness = max(0.0, 1.0 - spread)

        score = 100 * frequency * (SAVINGS_FREQUENCY_SHARE + (1 - SAVINGS_FREQUENCY_SHARE) * evenness)
        component.set(score, f"Saved in {weeks_saved} of {total_weeks} weeks.")

    async def _score_tracking(
        self,
        component: _Component,
        user_id: uuid.UUID,
        period_start: date,
        period_end: date,
        dt_start: datetime,
        dt_end: datetime,
        today: date,
    ) -> None:
        # A month in progress is judged on days elapsed, not the full month —
        # otherwise the current score would always look worse than it is.
        last_day = min(period_end, today)
        days_elapsed = (last_day - period_start).days + 1

        logged = await self._db.scalar(
            select(func.count(func.distinct(func.date(Expense.expense_date)))).where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= dt_start,
                Expense.expense_date <= dt_end,
            )
        ) or 0

        if logged == 0:
            ever_logged = await self._db.scalar(
                select(func.count())
                .select_from(Expense)
                .where(Expense.user_id == user_id, Expense.deleted_at.is_(None), Expense.expense_date <= dt_end)
            )
            if not ever_logged:
                component.no_data("You haven't logged any expenses yet.")
                return

        component.set(
            min(100.0, logged / days_elapsed * 100),
            f"Logged expenses on {logged} of {days_elapsed} days.",
        )

    async def _score_goals(
        self, component: _Component, user_id: uuid.UUID, period_start: date, period_end: date
    ) -> None:
        rows = await self._db.execute(
            select(SavingsChallenge.status).where(
                SavingsChallenge.user_id == user_id,
                SavingsChallenge.start_date <= period_end,
                or_(SavingsChallenge.end_date.is_(None), SavingsChallenge.end_date >= period_start),
            )
        )
        statuses = [s for (s,) in rows.all()]
        if not statuses:
            component.no_data("No challenges set for this month.")
            return

        # Still-running challenges shouldn't count as failures — only settled ones are judged.
        settled = [s for s in statuses if s != ChallengeStatus.ACTIVE]
        if not settled:
            component.no_data(f"{len(statuses)} challenge(s) still in progress.")
            return

        completed = sum(1 for s in settled if s == ChallengeStatus.COMPLETED)
        component.set(
            completed / len(settled) * 100,
            f"Completed {completed} of {len(settled)} finished challenges.",
        )

    async def _store(
        self,
        user_id: uuid.UUID,
        year: int,
        month: int,
        score: float,
        components: list[ScoreComponentDto],
    ) -> None:
        period_start, _ = _month_bounds(year, month)
        by_key = {c.key: c.score for c in components}
        existing = await self._db.scalar(
            select(FinclarScoreSnapshot).where(
                FinclarScoreSnapshot.user_id == user_id,
                FinclarScoreSnapshot.period_start == period_start,
            )
        )
        target = existing or FinclarScoreSnapshot(user_id=user_id, period_start=period_start)
        target.score = score
        target.budget_adherence = by_key.get("budget_adherence", 0.0)
        target.savings_consistency = by_key.get("savings_consistency", 0.0)
        target.tracking_consistency = by_key.get("tracking_consistency", 0.0)
        target.goal_achievement = by_key.get("goal_achievement", 0.0)
        if existing is None:
            self._db.add(target)
        # Flushed, not committed — so a snapshot written earlier in this request
        # (the current month) is visible to the history query that follows.
        await self._db.flush()

    async def _history(
        self, user_id: uuid.UUID, year: int, month: int, today: date
    ) -> list[ScoreHistoryPointDto]:
        """
        The HISTORY_MONTHS months ending at (year, month). Past months are read
        from stored snapshots — they are only computed once, the first time the
        user looks at a period that includes them.
        """
        months = [_shift_month(year, month, -offset) for offset in range(HISTORY_MONTHS - 1, -1, -1)]
        months = [(y, m) for y, m in months if (y, m) <= (today.year, today.month)]
        starts = [date(y, m, 1) for y, m in months]

        rows = await self._db.execute(
            select(FinclarScoreSnapshot.period_start, FinclarScoreSnapshot.score).where(
                FinclarScoreSnapshot.user_id == user_id,
                FinclarScoreSnapshot.period_start.in_(starts),
            )
        )
        stored = {period: float(value) for period, value in rows.all()}

        points = []
        for (y, m), start in zip(months, starts):
            if start not in stored:
                parts, computed, month_has_data = await self._compute(user_id, y, m, today)
                # A month with nothing to score isn't a zero — it's a gap. Don't
                # store it or plot it, or the trend line starts with fake zeros.
                if not month_has_data:
                    continue
                await self._store(user_id, y, m, computed, parts)
                stored[start] = computed
            points.append(
                ScoreHistoryPointDto(
                    year=y,
                    month=m,
                    label=calendar.month_abbr[m],
                    period_start=start,
                    score=stored[start],
                )
            )
        return points

    async def _award_score_badges(self, user_id: uuid.UUID, score: float) -> None:
        for threshold, key in SCORE_BADGES:
            if score >= threshold:
                await self._badges.award(user_id, key)


def get_score_service(
    db: AsyncSession = Depends(get_db),
) -> ScoreService:
    return ScoreService(db, BadgeService(db))
