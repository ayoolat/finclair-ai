"""
Shared read queries over expenses/income, used by any feature that needs a
financial summary over a date range (Clara insights, Money Wrapped, etc).
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
            total += amt * (total_days / 30)
    return total
