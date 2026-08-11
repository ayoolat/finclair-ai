import asyncio
import calendar
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.income import IncomeReoccurrence
from app.common.finance_queries import (
    category_totals,
    current_income_period,
    expense_total,
    income_for_range,
    verification_breakdown,
)
from app.common.response import Result
from app.database.session import get_db
from app.module.budget.dto.budget import AllocationResponseDto
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.income.schema.income import Income
from app.module.insight.dto.insight import HomeInsightDto
from app.module.user.schema.user import User


class ClaraService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Home dashboard ────────────────────────────────────────────────────────

    async def home_insight(
        self,
        user_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Result[HomeInsightDto]:
        user_row = await self._db.execute(select(User).where(User.id == user_id))
        user = user_row.scalar_one_or_none()
        if user is None:
            return Result.fail("User not found.", error_code="NOT_FOUND", status_code=404)

        today = date.today()
        if start_date is None and end_date is None:
            start_date, end_date = await self._current_income_cycle(user_id, today)
        else:
            if start_date is None:
                start_date = date(today.year, today.month, 1)
            if end_date is None:
                end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])

        if end_date < start_date:
            return Result.fail("end_date must be on or after start_date.", error_code="INVALID_RANGE", status_code=400)

        dt_start = datetime(start_date.year, start_date.month, start_date.day)
        dt_end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

        total_spent, category_rows, total_income, (this_week, last_week), (verified_amt, self_reported_amt) = await asyncio.gather(
            expense_total(self._db, user_id, dt_start, dt_end),
            category_totals(self._db, user_id, dt_start, dt_end, limit=3),
            income_for_range(self._db, user_id, start_date, end_date),
            self._week_totals(user_id),
            verification_breakdown(self._db, user_id, dt_start, dt_end),
        )
        top_categories = [(name, amount) for name, _icon, amount in category_rows]
        verified_pct = (verified_amt / total_spent * 100) if total_spent > 0 else 0.0
        self_reported_pct = (self_reported_amt / total_spent * 100) if total_spent > 0 else 0.0

        symbol = "₦" if user.default_currency == "NGN" else user.default_currency
        insight = _home_insight_rules(
            username=user.display_name,
            symbol=symbol,
            total_spent=total_spent,
            total_income=total_income,
            top_categories=top_categories,
            this_week=this_week,
            last_week=last_week,
        )
        if total_spent > 0 and self_reported_amt > 0:
            insight = f"{insight} This month's analysis is based on 🟢 {verified_pct:.0f}% verified transactions and 🟡 {self_reported_pct:.0f}% self-reported expenses."

        return Result.ok(HomeInsightDto(
            insight=insight,
            start_date=start_date,
            end_date=end_date,
            total_income=total_income,
            total_expenses=total_spent,
            available_balance=max(0.0, total_income - total_spent),
            verified_pct=verified_pct,
            self_reported_pct=self_reported_pct,
        ))

    async def _current_income_cycle(self, user_id: uuid.UUID, today: date) -> tuple[date, date]:
        """The user's current income cycle window: MONTHLY resets on the 1st of the month,
        WEEKLY resets on Monday — clipped to the income's start_date/end_date so the first
        (and last) cycle don't extend beyond when the income is actually active."""
        calendar_month = (
            date(today.year, today.month, 1),
            date(today.year, today.month, calendar.monthrange(today.year, today.month)[1]),
        )

        result = await self._db.execute(
            select(Income.reoccurrence, Income.start_date, Income.end_date)
            .where(Income.user_id == user_id, Income.start_date <= today)
            .order_by(Income.start_date.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return calendar_month

        reoccurrence, inc_start, inc_end = row
        rec = IncomeReoccurrence(reoccurrence)
        if rec == IncomeReoccurrence.ONE_TIME or (inc_end is not None and inc_end < today):
            return calendar_month

        period_start, period_end = current_income_period(inc_start, rec, today)
        if inc_end is not None:
            period_end = min(period_end, inc_end)
        return period_start, period_end

    # ── Post-expense ──────────────────────────────────────────────────────────

    async def post_expense_insight(self, user_id: uuid.UUID, expense: Expense) -> str:
        today = date.today()
        month_start, month_end = _month_bounds(today.year, today.month)
        week_end = datetime(today.year, today.month, today.day, 23, 59, 59)
        week_start = datetime(today.year, today.month, today.day) - timedelta(days=6)

        prev_year, prev_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        prev_start, prev_end = _month_bounds(prev_year, prev_month)

        primary_cat = expense.categories[0] if expense.categories else None
        week_count = 0
        this_month_cat = 0.0
        last_month_cat = 0.0

        if primary_cat:
            count_row = await self._db.execute(
                select(func.count(Expense.id))
                .join(expense_categories, expense_categories.c.expense_id == Expense.id)
                .where(
                    Expense.user_id == user_id,
                    Expense.deleted_at.is_(None),
                    Expense.expense_date >= week_start,
                    Expense.expense_date <= week_end,
                    expense_categories.c.category_id == primary_cat.id,
                )
            )
            week_count = count_row.scalar_one() or 0
            this_month_cat, last_month_cat = await asyncio.gather(
                self._category_total(user_id, primary_cat.id, month_start, month_end),
                self._category_total(user_id, primary_cat.id, prev_start, prev_end),
            )

        month_total, monthly_income = await asyncio.gather(
            expense_total(self._db, user_id, month_start, month_end),
            self._monthly_income(user_id, today.year, today.month),
        )

        symbol = "₦" if (not expense.currency or expense.currency == "NGN") else expense.currency
        return _post_expense_rules(
            symbol=symbol,
            category_name=primary_cat.name if primary_cat else None,
            week_count=week_count,
            this_month_cat_total=this_month_cat,
            last_month_cat_total=last_month_cat,
            month_total=month_total,
            monthly_income=monthly_income,
        )

    # ── Budget ────────────────────────────────────────────────────────────────

    def budget_insight(
        self,
        allocated: float,
        spent: float,
        pct_used: float,
        remaining: float,
        allocations: list[AllocationResponseDto],
        symbol: str = "₦",
    ) -> str:
        return _budget_insight_rules(allocated, spent, pct_used, remaining, allocations, symbol)

    # ── Private DB helpers ────────────────────────────────────────────────────

    async def _category_total(
        self, user_id: uuid.UUID, category_id: uuid.UUID, start: datetime, end: datetime
    ) -> float:
        row = await self._db.execute(
            select(func.sum(Expense.amount))
            .join(expense_categories, expense_categories.c.expense_id == Expense.id)
            .where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= start,
                Expense.expense_date <= end,
                expense_categories.c.category_id == category_id,
            )
        )
        return float(row.scalar_one() or 0)

    async def _monthly_income(self, user_id: uuid.UUID, year: int, month: int) -> float:
        month_start = date(year, month, 1)
        rows = await self._db.execute(
            select(Income.amount, Income.reoccurrence, Income.start_date, Income.end_date).where(
                Income.user_id == user_id,
                Income.start_date <= date(year, month, 28),
            )
        )
        multipliers = {
            IncomeReoccurrence.DAILY: 30,
            IncomeReoccurrence.WEEKLY: 4,
            IncomeReoccurrence.MONTHLY: 1,
        }
        total = 0.0
        for amount, reoccurrence, start, end in rows.all():
            rec = IncomeReoccurrence(reoccurrence)
            if rec == IncomeReoccurrence.ONE_TIME:
                if start >= month_start and (end is None or end <= date(year, month, 28)):
                    total += float(amount)
            else:
                if end is None or end >= month_start:
                    total += float(amount) * multipliers.get(rec, 1)
        return total

    async def _week_totals(self, user_id: uuid.UUID) -> tuple[float, float]:
        today = date.today()
        this_end = datetime(today.year, today.month, today.day, 23, 59, 59)
        this_start = datetime(today.year, today.month, today.day) - timedelta(days=6)
        last_end = this_start - timedelta(seconds=1)
        last_start = datetime(last_end.year, last_end.month, last_end.day) - timedelta(days=6)

        this_week, last_week = await asyncio.gather(
            expense_total(self._db, user_id, this_start, this_end),
            expense_total(self._db, user_id, last_start, last_end),
        )
        return this_week, last_week


# ── Dependency ────────────────────────────────────────────────────────────────

def get_clara_service(db: AsyncSession = Depends(get_db)) -> ClaraService:
    return ClaraService(db)


# ── Rule engines ──────────────────────────────────────────────────────────────

def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{({1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th'))}"


def _home_insight_rules(
    username: str,
    symbol: str,
    total_spent: float,
    total_income: float,
    top_categories: list[tuple[str, float]],
    this_week: float,
    last_week: float,
) -> str:
    if total_spent == 0:
        return random.choice([
            f"No spending recorded yet this month, {username}. Once you log your first expense, I'll start building your picture.",
            f"Nothing logged yet this month, {username}. Add your first expense and I'll get to work.",
            f"Your slate is clean this month, {username}. Log an expense and I'll start making sense of it.",
        ])

    pct = (total_spent / total_income * 100) if total_income > 0 else None
    top_name = top_categories[0][0] if top_categories else None
    top_amount = top_categories[0][1] if top_categories else None
    week_change: Optional[float] = ((this_week - last_week) / last_week * 100) if last_week > 0 else None

    if pct is not None and pct > 100:
        lead = random.choice([
            f"You've spent {symbol}{total_spent:,.0f} this month, {username} — that's {pct:.0f}% of your income.",
            f"This month's spending hit {symbol}{total_spent:,.0f}, {username} — {pct:.0f}% of your income.",
            f"{pct:.0f}% of your income spent this month, {username} — that's {symbol}{total_spent:,.0f} in total.",
        ])
    elif pct is not None and pct >= 80:
        lead = random.choice([
            f"You've used {pct:.0f}% of your monthly income already, {username} — {symbol}{total_spent:,.0f} of {symbol}{total_income:,.0f} gone.",
            f"Getting close, {username} — {symbol}{total_spent:,.0f} spent puts you at {pct:.0f}% of your income.",
            f"{symbol}{total_spent:,.0f} down, {username}. That's {pct:.0f}% of your monthly income.",
        ])
    elif pct is not None and pct >= 50:
        lead = random.choice([
            f"Halfway through your income this month, {username} — {symbol}{total_spent:,.0f} spent so far.",
            f"You're past the halfway mark, {username} — {symbol}{total_spent:,.0f} of your income spent.",
            f"{symbol}{total_spent:,.0f} spent so far this month, {username} — just past the halfway point.",
        ])
    elif pct is not None:
        lead = random.choice([
            f"Looking good, {username} — you've only spent {pct:.0f}% of your income ({symbol}{total_spent:,.0f}) so far this month.",
            f"You're tracking well, {username} — {pct:.0f}% of income spent ({symbol}{total_spent:,.0f}) with room to breathe.",
            f"Nice pace, {username} — only {symbol}{total_spent:,.0f} out the door, which is just {pct:.0f}% of your income.",
        ])
    else:
        lead = random.choice([
            f"You've spent {symbol}{total_spent:,.0f} so far this month, {username}.",
            f"This month's spending sits at {symbol}{total_spent:,.0f} so far, {username}.",
            f"{symbol}{total_spent:,.0f} logged this month, {username}.",
        ])

    parts = [lead]

    if week_change is not None and abs(week_change) >= 10:
        if week_change > 0:
            parts.append(random.choice([
                f"Your spending this week is up {week_change:.0f}% compared to last week.",
                f"This week's spending is running {week_change:.0f}% higher than last week.",
                f"You've spent {week_change:.0f}% more this week than last week.",
            ]))
        else:
            parts.append(random.choice([
                f"Your spending this week is down {abs(week_change):.0f}% compared to last week.",
                f"Spending dropped {abs(week_change):.0f}% this week compared to last.",
                f"This week you spent {abs(week_change):.0f}% less than last week.",
            ]))
    elif top_name and top_amount:
        top_pct = (top_amount / total_spent * 100) if total_spent > 0 else 0
        if top_pct >= 40:
            parts.append(random.choice([
                f"{top_name} is taking up the most at {symbol}{top_amount:,.0f}.",
                f"Most of that went to {top_name} — {symbol}{top_amount:,.0f}.",
                f"{top_name} is your biggest spend this month at {symbol}{top_amount:,.0f}.",
            ]))
        else:
            parts.append(random.choice([
                f"Your top category is {top_name} at {symbol}{top_amount:,.0f}.",
                f"{top_name} leads your spending at {symbol}{top_amount:,.0f}.",
                f"You've spent the most on {top_name} — {symbol}{top_amount:,.0f} so far.",
            ]))

    if pct is not None and pct > 100:
        parts.append(random.choice([
            "Worth reviewing where you can trim back.",
            "Might be time to look at where the money's going.",
            "A quick review could help you find where to pull back.",
        ]))
    elif pct is not None and pct < 40 and week_change is not None and week_change <= -10:
        parts.append(random.choice([
            "You're on a great streak — keep it going.",
            "That's a solid pattern — keep it up.",
            "Nice discipline this month — stay the course.",
        ]))

    return " ".join(parts)


def _post_expense_rules(
    symbol: str,
    category_name: Optional[str],
    week_count: int,
    this_month_cat_total: float,
    last_month_cat_total: float,
    month_total: float,
    monthly_income: float,
) -> str:
    lead: Optional[str] = None
    context: Optional[str] = None

    if category_name and week_count >= 3:
        lead = random.choice([
            f"That's your {_ordinal(week_count)} {category_name} purchase this week.",
            f"This is your {_ordinal(week_count)} {category_name} spend this week.",
            f"{category_name} again — {_ordinal(week_count)} time this week.",
        ])
    elif category_name and last_month_cat_total > 0:
        cat_change = (this_month_cat_total - last_month_cat_total) / last_month_cat_total * 100
        if cat_change >= 20:
            lead = random.choice([
                f"Your {category_name} spending is up {cat_change:.0f}% compared to last month.",
                f"{category_name} is running {cat_change:.0f}% higher than last month.",
                f"You're spending {cat_change:.0f}% more on {category_name} this month.",
            ])
        elif cat_change <= -20:
            lead = random.choice([
                f"Your {category_name} spending is down {abs(cat_change):.0f}% from last month.",
                f"You're spending {abs(cat_change):.0f}% less on {category_name} than last month.",
                f"{category_name} costs are {abs(cat_change):.0f}% lower than last month.",
            ])

    if monthly_income > 0:
        pct = month_total / monthly_income * 100
        if pct > 100:
            context = random.choice([
                "Your total spending this month has now gone over your income.",
                "This puts your total spending over your monthly income.",
                "You've now exceeded your monthly income in spending.",
            ])
        elif pct >= 80:
            context = random.choice([
                f"You've now used {pct:.0f}% of your monthly income.",
                f"That puts you at {pct:.0f}% of your income for the month.",
                f"You're at {pct:.0f}% of your monthly income — getting close.",
            ])
        elif pct < 50:
            context = random.choice([
                "You're still comfortably within your monthly income.",
                "This purchase keeps you well within budget.",
                "You're still well within your monthly income.",
            ])

    if lead and context:
        return f"{lead} {context}"
    if lead:
        return lead
    if context:
        return context
    return random.choice([
        "Expense logged. Keep adding and I'll start spotting patterns.",
        "Got it. Log more expenses and I'll help you find patterns.",
    ])


def _budget_insight_rules(
    allocated: float,
    spent: float,
    pct_used: float,
    remaining: float,
    allocations: list[AllocationResponseDto],
    symbol: str = "₦",
) -> str:
    if spent == 0:
        return random.choice([
            "Budget's all set. Start logging expenses and I'll track how you're doing.",
            "Nothing spent yet. Log your first expense and I'll keep score.",
            "Budget locked in. Add your first expense and I'll start watching the numbers.",
        ])

    over_budget_allocs = [a for a in allocations if a.spent > a.amount_allocated]
    highest_spend_alloc = max(allocations, key=lambda a: a.spent) if allocations else None
    highest_pct_alloc = max(allocations, key=lambda a: a.pct_used) if allocations else None

    if pct_used > 100:
        lead = random.choice([
            f"You've gone over budget — {symbol}{spent:,.0f} spent against {symbol}{allocated:,.0f} allocated.",
            f"Budget exceeded — {symbol}{spent:,.0f} out of {symbol}{allocated:,.0f} gone, and then some.",
            f"You're {pct_used - 100:.0f}% over your budget this month.",
        ])
    elif pct_used >= 90:
        lead = random.choice([
            f"You're at {pct_used:.0f}% of your budget — just {symbol}{remaining:,.0f} left.",
            f"Almost at your limit — {symbol}{remaining:,.0f} remaining from your {symbol}{allocated:,.0f} budget.",
            f"{pct_used:.0f}% of your budget is gone with {symbol}{remaining:,.0f} to spare.",
        ])
    elif pct_used >= 75:
        lead = random.choice([
            f"You're at {pct_used:.0f}% of your budget with {symbol}{remaining:,.0f} remaining.",
            f"Three quarters of your budget is used — {symbol}{remaining:,.0f} left to work with.",
            f"{symbol}{spent:,.0f} spent so far, leaving {symbol}{remaining:,.0f} in your budget.",
        ])
    elif pct_used >= 50:
        lead = random.choice([
            f"Halfway through your budget — {symbol}{spent:,.0f} of {symbol}{allocated:,.0f} used.",
            f"You've used {pct_used:.0f}% of your budget, with {symbol}{remaining:,.0f} still available.",
            f"{symbol}{spent:,.0f} spent against a {symbol}{allocated:,.0f} budget — right at the midpoint.",
        ])
    else:
        lead = random.choice([
            f"Looking good — only {pct_used:.0f}% of your budget used so far.",
            f"You've spent {symbol}{spent:,.0f} of your {symbol}{allocated:,.0f} budget. Plenty of room left.",
            f"Only {pct_used:.0f}% of your budget is gone — {symbol}{remaining:,.0f} still available.",
        ])

    context: Optional[str] = None

    if pct_used > 100 and over_budget_allocs:
        worst = max(over_budget_allocs, key=lambda a: a.spent - a.amount_allocated)
        overage = worst.spent - worst.amount_allocated
        context = random.choice([
            f"{worst.category_name} is your biggest overspend at {symbol}{overage:,.0f} over its allocation.",
            f"{worst.category_name} alone has gone {symbol}{overage:,.0f} over its limit.",
            f"Most of the damage is in {worst.category_name}, which is {symbol}{overage:,.0f} over.",
        ])
    elif pct_used >= 75 and highest_spend_alloc:
        context = random.choice([
            f"Cutting back on {highest_spend_alloc.category_name} this week could help you stay within budget.",
            f"Reducing {highest_spend_alloc.category_name} spending would give you the most breathing room.",
            f"{highest_spend_alloc.category_name} is your biggest spend — easing up there would help.",
        ])
    elif pct_used >= 50 and highest_pct_alloc and highest_pct_alloc.pct_used >= 80:
        context = random.choice([
            f"Your {highest_pct_alloc.category_name} allocation is close to its limit at {highest_pct_alloc.pct_used:.0f}% used.",
            f"Watch your {highest_pct_alloc.category_name} spending — it's at {highest_pct_alloc.pct_used:.0f}% of its allocation.",
            f"{highest_pct_alloc.category_name} is approaching its limit with {highest_pct_alloc.pct_used:.0f}% used.",
        ])
    elif pct_used < 50:
        if over_budget_allocs:
            context = random.choice([
                f"Though {over_budget_allocs[0].category_name} has already gone over its category allocation.",
                f"Note that {over_budget_allocs[0].category_name} has exceeded its individual allocation.",
            ])
        else:
            context = random.choice([
                "Keep it up and you'll finish the month in the green.",
                "You're on track for a solid month — keep going.",
                "Stay consistent and you'll end the month comfortably within budget.",
            ])

    if context:
        return f"{lead} {context}"
    return lead


# ── Shared helper ─────────────────────────────────────────────────────────────

def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    last_day = calendar.monthrange(year, month)[1]
    return (
        datetime(year, month, 1, 0, 0, 0),
        datetime(year, month, last_day, 23, 59, 59),
    )
