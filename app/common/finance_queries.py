"""
Shared read queries over expenses/income, used by any feature that needs a
financial summary over a date range (Clara insights, Money Wrapped, etc).
"""

import calendar
import uuid
from datetime import date, datetime
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


def _monthly_income_for_range(amt: float, start: date, end: date, inc_start: date, inc_end: Optional[date]) -> float:
    """Prorate a MONTHLY income amount against [start, end] using each calendar
    month's actual day count, so a full-calendar-month query returns the exact
    configured amount instead of drifting with month length (28-31 days)."""
    total = 0.0
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        days_in_month = calendar.monthrange(year, month)[1]
        month_start = date(year, month, 1)
        month_end = date(year, month, days_in_month)

        period_start = max(month_start, start, inc_start)
        period_end = min(month_end, end, inc_end) if inc_end is not None else min(month_end, end)

        if period_start <= period_end:
            overlap_days = (period_end - period_start).days + 1
            total += amt * (overlap_days / days_in_month)

        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return total


async def income_for_range(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> float:
    rows = await db.execute(
        select(Income.amount, Income.reoccurrence, Income.start_date, Income.end_date).where(
            Income.user_id == user_id,
            Income.start_date <= end,
        )
    )
    total_days = (end - start).days + 1
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
            total += amt * total_days
        elif rec == IncomeReoccurrence.WEEKLY:
            total += amt * (total_days / 7)
        elif rec == IncomeReoccurrence.MONTHLY:
            total += _monthly_income_for_range(amt, start, end, inc_start, inc_end)
    return total
