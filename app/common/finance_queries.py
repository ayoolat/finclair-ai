"""
Shared read queries over expenses/income, used by any feature that needs a
financial summary over a date range (Clara insights, Money Wrapped, etc).
"""

import calendar
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.expense import ExpenseVerificationLevel, verification_level_for_source
from app.common.enums.income import IncomeReoccurrence
from app.module.category.schema.category import Category
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.income.schema.income import Income


async def expense_total(db: AsyncSession, user_id: uuid.UUID, start: datetime, end: datetime) -> float:
    row = await db.execute(
        select(func.sum(Expense.amount)).where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
            Expense.expense_date >= start,
            Expense.expense_date <= end,
        )
    )
    return float(row.scalar_one() or 0)


async def expense_total_for_category(
    db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID, start: datetime, end: datetime
) -> float:
    row = await db.execute(
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


async def category_total_by_names(
    db: AsyncSession, user_id: uuid.UUID, names: list[str], start: datetime, end: datetime
) -> float:
    row = await db.execute(
        select(func.sum(Expense.amount))
        .join(expense_categories, expense_categories.c.expense_id == Expense.id)
        .join(Category, Category.id == expense_categories.c.category_id)
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
            Expense.expense_date >= start,
            Expense.expense_date <= end,
            func.lower(Category.name).in_([n.lower() for n in names]),
        )
    )
    return float(row.scalar_one() or 0)


async def category_totals(
    db: AsyncSession,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
    limit: Optional[int] = None,
) -> list[tuple[str, Optional[str], float]]:
    query = (
        select(Category.name, Category.icon, func.sum(Expense.amount).label("total"))
        .join(expense_categories, expense_categories.c.category_id == Category.id)
        .join(Expense, Expense.id == expense_categories.c.expense_id)
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
            Expense.expense_date >= start,
            Expense.expense_date <= end,
        )
        .group_by(Category.name, Category.icon)
        .order_by(func.sum(Expense.amount).desc())
    )
    if limit is not None:
        query = query.limit(limit)
    rows = await db.execute(query)
    return [(row.name, row.icon, float(row.total)) for row in rows.all()]


async def verification_breakdown(
    db: AsyncSession, user_id: uuid.UUID, start: datetime, end: datetime
) -> tuple[float, float]:
    """Returns (verified_amount, self_reported_amount) for expenses in the range."""
    rows = await db.execute(
        select(Expense.source, func.sum(Expense.amount).label("total"))
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
            Expense.expense_date >= start,
            Expense.expense_date <= end,
        )
        .group_by(Expense.source)
    )
    verified = 0.0
    self_reported = 0.0
    for source, total in rows.all():
        if verification_level_for_source(source) == ExpenseVerificationLevel.VERIFIED:
            verified += float(total)
        else:
            self_reported += float(total)
    return verified, self_reported


def _occurrence_count(step_days: int, start: date, end: date, inc_start: date, inc_end: Optional[date]) -> int:
    """Counts recurring-payment dates spaced `step_days` apart from inc_start that fall
    within [start, end] ∩ [inc_start, inc_end] — each occurrence is a discrete, full payment."""
    range_start = max(start, inc_start)
    range_end = min(end, inc_end) if inc_end is not None else end
    if range_start > range_end:
        return 0

    offset = (range_start - inc_start).days
    remainder = offset % step_days
    first_offset = offset if remainder == 0 else offset + (step_days - remainder)
    first_occurrence = inc_start + timedelta(days=first_offset)
    if first_occurrence > range_end:
        return 0

    return (range_end - first_occurrence).days // step_days + 1


def _monthly_income_for_range(amt: float, start: date, end: date, inc_start: date, inc_end: Optional[date]) -> float:
    """Counts the full amount once for each monthly anniversary of inc_start that falls
    within [start, end] — a monthly income is a discrete payment, not a continuous accrual,
    so a full-month query returns the exact configured amount per occurrence rather than a
    day-prorated fraction."""
    total = 0.0
    year, month = max((start.year, start.month), (inc_start.year, inc_start.month))
    while (year, month) <= (end.year, end.month):
        days_in_month = calendar.monthrange(year, month)[1]
        occurrence = date(year, month, min(inc_start.day, days_in_month))

        if start <= occurrence <= end and (inc_end is None or occurrence <= inc_end):
            total += amt

        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return total


def current_income_period(inc_start: date, reoccurrence: IncomeReoccurrence, as_of: date) -> tuple[date, date]:
    """Returns the [start, end] window (inclusive) of the recurring-income cycle that
    `as_of` falls into. Cycles reset on fixed calendar boundaries — the 1st of the month
    for MONTHLY, Monday for WEEKLY — not on the income's own start_date; only the very
    first cycle is clipped to start_date since the income didn't exist before then."""
    as_of = max(as_of, inc_start)

    if reoccurrence == IncomeReoccurrence.DAILY:
        return as_of, as_of

    if reoccurrence == IncomeReoccurrence.WEEKLY:
        monday = as_of - timedelta(days=as_of.weekday())
        return max(monday, inc_start), monday + timedelta(days=6)

    if reoccurrence == IncomeReoccurrence.MONTHLY:
        month_start = date(as_of.year, as_of.month, 1)
        days_in_month = calendar.monthrange(as_of.year, as_of.month)[1]
        return max(month_start, inc_start), date(as_of.year, as_of.month, days_in_month)

    # ONE_TIME has no recurring cycle to anchor to.
    return inc_start, inc_start


async def income_for_range(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> float:
    rows = await db.execute(
        select(Income.amount, Income.reoccurrence, Income.start_date, Income.end_date).where(
            Income.user_id == user_id,
            Income.start_date <= end,
        )
    )
    total = 0.0
    for amount, reoccurrence, inc_start, inc_end in rows.all():
        if inc_end is not None and inc_end < start:
            continue
        rec = IncomeReoccurrence(reoccurrence)
        amt = float(amount)
        if rec == IncomeReoccurrence.ONE_TIME:
            if start <= inc_start <= end:
                total += amt
        elif rec == IncomeReoccurrence.DAILY:
            range_start = max(start, inc_start)
            range_end = min(end, inc_end) if inc_end is not None else end
            if range_start <= range_end:
                total += amt * ((range_end - range_start).days + 1)
        elif rec == IncomeReoccurrence.WEEKLY:
            total += amt * _occurrence_count(7, start, end, inc_start, inc_end)
        elif rec == IncomeReoccurrence.MONTHLY:
            total += _monthly_income_for_range(amt, start, end, inc_start, inc_end)
    return total
