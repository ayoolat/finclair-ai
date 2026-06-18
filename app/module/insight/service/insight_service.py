import asyncio
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clients.openai_client import get_openai_client
from app.common.enums.income import IncomeReoccurrence
from app.common.response import Result
from app.database.session import get_db
from app.module.category.schema.category import Category
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.income.schema.income import Income
from app.module.user.schema.user import User

_SYSTEM_PROMPT = (
    "You are Clara, a warm and slightly witty AI financial assistant for Finclair — "
    "a personal finance app for Nigerians.\n\n"
    "Your job: write a brief, personal spending insight for the current month.\n\n"
    "Rules:\n"
    "- Address the user by their username\n"
    "- Be warm, conversational, and slightly playful — like a smart friend who knows money\n"
    "- Exactly 2-3 sentences, no more\n"
    "- Lead with the most interesting data point (total spent, % of income, or top category spike)\n"
    "- End with a light observation, gentle nudge, or soft call to action\n"
    "- Use ₦ for naira amounts with comma-separated thousands (e.g. ₦50,000)\n"
    "- Never lecture or moralize\n"
    "- Only reference numbers you are given — never invent figures\n"
)

_MONTHLY_MULTIPLIERS = {
    IncomeReoccurrence.DAILY: 30,
    IncomeReoccurrence.WEEKLY: 4,
    IncomeReoccurrence.MONTHLY: 1,
    IncomeReoccurrence.ONE_TIME: 0,  # handled separately
}


class InsightService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def home_insight(self, user_id: uuid.UUID) -> Result[str]:
        user_row = await self._db.execute(select(User).where(User.id == user_id))
        user = user_row.scalar_one_or_none()
        if user is None:
            return Result.fail("User not found.", error_code="NOT_FOUND", status_code=404)

        today = date.today()
        month_start = datetime(today.year, today.month, 1)
        month_end = datetime(today.year, today.month, today.day, 23, 59, 59)

        total_spent = await self._month_total(user_id, month_start, month_end)
        top_categories = await self._top_categories(user_id, month_start, month_end)
        monthly_income = await self._monthly_income(user_id, today)

        user_prompt = _build_prompt(
            username=user.username,
            month=today.strftime("%B"),
            total_spent=total_spent,
            monthly_income=monthly_income,
            top_categories=top_categories,
            currency=user.default_currency,
        )

        client = get_openai_client()
        try:
            response = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=200,
                    temperature=0.8,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            )
            message = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            return Result.fail(str(exc), error_code="AI_ERROR", status_code=502)

        return Result.ok(message)

    async def _month_total(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> float:
        row = await self._db.execute(
            select(func.sum(Expense.amount)).where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= start,
                Expense.expense_date <= end,
            )
        )
        return float(row.scalar_one() or 0)

    async def _top_categories(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[tuple[str, float]]:
        rows = await self._db.execute(
            select(Category.name, func.sum(Expense.amount).label("total"))
            .join(expense_categories, expense_categories.c.category_id == Category.id)
            .join(Expense, Expense.id == expense_categories.c.expense_id)
            .where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= start,
                Expense.expense_date <= end,
            )
            .group_by(Category.name)
            .order_by(func.sum(Expense.amount).desc())
            .limit(3)
        )
        return [(row.name, float(row.total)) for row in rows.all()]

    async def _monthly_income(self, user_id: uuid.UUID, today: date) -> float:
        month_start = date(today.year, today.month, 1)
        rows = await self._db.execute(
            select(Income.amount, Income.reoccurrence, Income.start_date).where(
                Income.user_id == user_id,
                Income.start_date <= today,
            )
        )
        total = 0.0
        for amount, reoccurrence, start_date in rows.all():
            rec = IncomeReoccurrence(reoccurrence)
            if rec == IncomeReoccurrence.ONE_TIME:
                if start_date >= month_start:
                    total += float(amount)
            else:
                multiplier = _MONTHLY_MULTIPLIERS.get(rec, 1)
                total += float(amount) * multiplier
        return total


def _build_prompt(
    username: str,
    month: str,
    total_spent: float,
    monthly_income: float,
    top_categories: list[tuple[str, float]],
    currency: str,
) -> str:
    symbol = "₦" if currency == "NGN" else currency
    pct: Optional[float] = (total_spent / monthly_income * 100) if monthly_income > 0 else None

    lines = [
        f"User: {username}",
        f"Month: {month}",
        f"Total spent so far: {symbol}{total_spent:,.0f}",
    ]
    if monthly_income > 0:
        lines.append(f"Estimated monthly income: {symbol}{monthly_income:,.0f}")
    if pct is not None:
        lines.append(f"Spending as % of income: {pct:.0f}%")
    if top_categories:
        lines.append("Top spending categories:")
        for name, amount in top_categories:
            cat_pct = (amount / total_spent * 100) if total_spent > 0 else 0
            lines.append(f"  - {name}: {symbol}{amount:,.0f} ({cat_pct:.0f}% of total)")

    lines.append("\nWrite Clara's home screen insight.")
    return "\n".join(lines)


def get_insight_service(db: AsyncSession = Depends(get_db)) -> InsightService:
    return InsightService(db)
