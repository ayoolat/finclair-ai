import asyncio
import calendar
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import Depends
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.finance_queries import category_totals, expense_total, income_for_range
from app.common.response import Result
from app.database.session import get_db
from app.module.budget.schema.budget import Budget
from app.module.expense.schema.expense import Expense
from app.module.user.schema.user import User
from app.module.wrapped.dto.wrapped import (
    BadgeDto,
    CategoryShareDto,
    IncomeExpenseDto,
    MonthlySavingsDto,
    MoneyPersonalityDto,
    SavingsDto,
    SharePassportDto,
    SpendingBreakdownDto,
    TipDto,
    TopCategoryDto,
    WrappedCoverDto,
    WrappedDto,
)

TOP_CATEGORIES_LIMIT = 6
WEEKEND_DOW = (0, 6)  # Postgres EXTRACT(DOW): 0 = Sunday, 6 = Saturday


class WrappedService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_wrapped(self, user_id: uuid.UUID, year: Optional[int] = None) -> Result[WrappedDto]:
        user_row = await self._db.execute(select(User).where(User.id == user_id))
        user = user_row.scalar_one_or_none()
        if user is None:
            return Result.fail("User not found.", error_code="NOT_FOUND", status_code=404)

        year = year or date.today().year
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        dt_start = datetime(year, 1, 1)
        dt_end = datetime(year, 12, 31, 23, 59, 59)

        symbol = "₦" if user.default_currency == "NGN" else user.default_currency

        total_expenses, category_rows, total_income, weekend_expenses, budget_rows = await asyncio.gather(
            expense_total(self._db, user_id, dt_start, dt_end),
            category_totals(self._db, user_id, dt_start, dt_end, limit=TOP_CATEGORIES_LIMIT),
            income_for_range(self._db, user_id, start_date, end_date),
            self._weekend_expense_total(user_id, dt_start, dt_end),
            self._budgets_for_year(user_id, year),
        )
        monthly_trend = await self._monthly_trend(user_id, year)

        categories = [
            CategoryShareDto(
                name=name,
                icon=icon,
                amount=amount,
                percentage=(amount / total_expenses * 100) if total_expenses > 0 else 0.0,
            )
            for name, icon, amount in category_rows
        ]
        top_category = categories[0] if categories else None
        top_category_share = top_category.percentage if top_category else 0.0
        weekend_share = (weekend_expenses / total_expenses * 100) if total_expenses > 0 else 0.0
        net_balance = total_income - total_expenses
        savings_rate = (net_balance / total_income * 100) if total_income > 0 else 0.0

        months_tracked = len(budget_rows)
        months_on_track = sum(1 for b in budget_rows if float(b.spent) <= float(b.amount_allocated))

        personality = _personality_rules(
            total_expenses=total_expenses,
            savings_rate=savings_rate,
            top_category_name=top_category.name if top_category else None,
            top_category_share=top_category_share,
            weekend_share=weekend_share,
            months_tracked=months_tracked,
            months_on_track=months_on_track,
        )
        tip = _tip_rules(
            symbol=symbol,
            top_category_name=top_category.name if top_category else None,
            top_category_share=top_category_share,
            savings_rate=savings_rate,
            total_expenses=total_expenses,
        )
        badge = _badge_rules(
            username=user.username,
            months_tracked=months_tracked,
            months_on_track=months_on_track,
            savings_rate=savings_rate,
            total_expenses=total_expenses,
        )

        return Result.ok(
            WrappedDto(
                year=year,
                start_date=start_date,
                end_date=end_date,
                symbol=symbol,
                cover=WrappedCoverDto(
                    year=year,
                    username=user.username,
                    headline=f"Your {year} Money Wrapped is here, {user.username}.",
                ),
                income_vs_expense=IncomeExpenseDto(
                    total_income=total_income,
                    total_expenses=total_expenses,
                    net_balance=net_balance,
                    headline=(
                        f"You earned {symbol}{total_income:,.0f} and spent {symbol}{total_expenses:,.0f} in {year}."
                        if total_income > 0 or total_expenses > 0
                        else f"No income or expenses logged for {year} yet."
                    ),
                ),
                spending_breakdown=SpendingBreakdownDto(
                    total_expenses=total_expenses,
                    categories=categories,
                    headline=(
                        f"Your money moved across {len(categories)} categories this year."
                        if categories
                        else "No spending logged yet."
                    ),
                ),
                top_category=(
                    TopCategoryDto(
                        name=top_category.name,
                        icon=top_category.icon,
                        amount=top_category.amount,
                        percentage=top_category_share,
                        headline=f"{top_category.name} took the biggest bite — {top_category_share:.0f}% of your spending.",
                    )
                    if top_category
                    else None
                ),
                savings=SavingsDto(
                    savings_rate=savings_rate,
                    total_saved=max(0.0, net_balance),
                    headline=_savings_headline(savings_rate, symbol, net_balance, total_income, total_expenses),
                    monthly_trend=monthly_trend,
                ),
                personality=personality,
                tip=tip,
                badge=badge,
                share_passport=SharePassportDto(
                    username=user.username,
                    year=year,
                    total_income=total_income,
                    total_expenses=total_expenses,
                    total_saved=max(0.0, net_balance),
                    top_category=top_category.name if top_category else None,
                    personality_name=personality.name,
                    badge_name=badge.name,
                ),
            )
        )

    # ── Private DB helpers ────────────────────────────────────────────────────

    async def _weekend_expense_total(self, user_id: uuid.UUID, start: datetime, end: datetime) -> float:
        row = await self._db.execute(
            select(func.sum(Expense.amount)).where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= start,
                Expense.expense_date <= end,
                extract("dow", Expense.expense_date).in_(WEEKEND_DOW),
            )
        )
        return float(row.scalar_one() or 0)

    async def _budgets_for_year(self, user_id: uuid.UUID, year: int) -> list[Budget]:
        rows = await self._db.execute(
            select(Budget).where(
                Budget.user_id == user_id,
                Budget.start_date >= date(year, 1, 1),
                Budget.start_date <= date(year, 12, 31),
            )
        )
        return list(rows.scalars().all())

    async def _monthly_trend(self, user_id: uuid.UUID, year: int) -> list[MonthlySavingsDto]:
        trend: list[MonthlySavingsDto] = []
        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            month_start = date(year, month, 1)
            month_end = date(year, month, last_day)
            dt_start = datetime(year, month, 1)
            dt_end = datetime(year, month, last_day, 23, 59, 59)
            month_expenses = await expense_total(self._db, user_id, dt_start, dt_end)
            month_income = await income_for_range(self._db, user_id, month_start, month_end)
            trend.append(
                MonthlySavingsDto(
                    month=month,
                    income=month_income,
                    expenses=month_expenses,
                    net_saved=month_income - month_expenses,
                )
            )
        return trend


def get_wrapped_service(db: AsyncSession = Depends(get_db)) -> WrappedService:
    return WrappedService(db)


# ── Rule engines ──────────────────────────────────────────────────────────────

def _savings_headline(savings_rate: float, symbol: str, net_balance: float, total_income: float, total_expenses: float) -> str:
    if total_income == 0 and total_expenses == 0:
        return "Nothing tracked yet this year — log an income and expense to see your savings story."
    if net_balance <= 0:
        return "You spent more than you earned this year — next year's a fresh start."
    if savings_rate >= 30:
        return f"Your savings game is fire! You kept {savings_rate:.0f}% of your income — {symbol}{net_balance:,.0f} saved."
    if savings_rate >= 10:
        return f"Solid work — you saved {savings_rate:.0f}% of your income, {symbol}{net_balance:,.0f} in total."
    return f"You saved {symbol}{net_balance:,.0f} this year — {savings_rate:.0f}% of your income. Room to grow next year."


def _personality_rules(
    total_expenses: float,
    savings_rate: float,
    top_category_name: Optional[str],
    top_category_share: float,
    weekend_share: float,
    months_tracked: int,
    months_on_track: int,
) -> MoneyPersonalityDto:
    if total_expenses == 0:
        return MoneyPersonalityDto(
            key="fresh_start",
            name="The Fresh Start",
            description="You haven't logged any spending yet this year. Once you do, I'll get to know your money habits.",
        )

    if savings_rate <= -10:
        return MoneyPersonalityDto(
            key="big_spender",
            name="The Big Spender",
            description="You spent more than you brought in this year. Living for the moment has its price — let's rein it in next year.",
        )

    if top_category_name and top_category_share >= 40:
        return MoneyPersonalityDto(
            key="category_enthusiast",
            name=f"The {top_category_name} Enthusiast",
            description=f"{top_category_name} took up {top_category_share:.0f}% of your spending this year — clearly a priority for you.",
        )

    if weekend_share >= 60:
        return MoneyPersonalityDto(
            key="weekend_spender",
            name="The Weekend Spender",
            description="Most of your money goes out on weekends. Weekdays are for saving, weekends are for living.",
        )

    if savings_rate >= 30:
        return MoneyPersonalityDto(
            key="steady_saver",
            name="The Steady Saver",
            description="You consistently kept a big chunk of your income unspent this year. Disciplined and future-focused.",
        )

    if months_tracked > 0 and months_on_track / months_tracked >= 0.75:
        return MoneyPersonalityDto(
            key="pragmatic_planner",
            name="The Pragmatic Planner",
            description="You stuck to your budget in most months this year — thoughtful, deliberate, and in control.",
        )

    return MoneyPersonalityDto(
        key="balanced_budgeter",
        name="The Balanced Budgeter",
        description="Your spending is spread evenly across the things you care about — no single habit dominates your year.",
    )


def _tip_rules(
    symbol: str,
    top_category_name: Optional[str],
    top_category_share: float,
    savings_rate: float,
    total_expenses: float,
) -> TipDto:
    if total_expenses == 0:
        return TipDto(
            title="Start logging your spending",
            body="Once you log a few expenses, I'll be able to spot patterns and suggest ways to save.",
        )

    if savings_rate < 0:
        return TipDto(
            title="Bring spending back under income",
            body="You spent more than you earned this year. Try setting a monthly budget so you can see the gap before it grows.",
        )

    if top_category_name and top_category_share >= 40:
        return TipDto(
            title=f"Set a budget for {top_category_name}",
            body=f"{top_category_name} took the biggest bite out of your money this year. Setting a monthly cap could free up cash for your other goals.",
        )

    if savings_rate < 15:
        return TipDto(
            title="Build a small savings cushion",
            body=f"You saved {savings_rate:.0f}% of your income this year. Try setting aside a fixed amount right after payday — even {symbol}5,000 a month adds up.",
        )

    return TipDto(
        title="Put your savings to work",
        body="You're saving well — consider setting a financial goal so that extra cash has a purpose.",
    )


def _badge_rules(
    username: str,
    months_tracked: int,
    months_on_track: int,
    savings_rate: float,
    total_expenses: float,
) -> BadgeDto:
    if total_expenses == 0:
        return BadgeDto(
            key="getting_started",
            name="Getting Started",
            headline=f"Welcome, {username}!",
            description="Log your first expense to start earning badges.",
            months_on_track=0,
            months_tracked=0,
        )

    on_track_ratio = (months_on_track / months_tracked) if months_tracked > 0 else 0.0

    if on_track_ratio >= 0.9 and months_tracked >= 6:
        return BadgeDto(
            key="money_champion",
            name="Money Champion",
            headline=f"Keep it up, champ {username}!",
            description=f"You stayed within budget in {months_on_track} of {months_tracked} months this year. That's elite discipline.",
            months_on_track=months_on_track,
            months_tracked=months_tracked,
        )

    if savings_rate >= 20:
        return BadgeDto(
            key="consistent_saver",
            name="Consistent Saver",
            headline=f"Well done, {username}!",
            description=f"You kept {savings_rate:.0f}% of your income this year. That consistency is what builds real wealth.",
            months_on_track=months_on_track,
            months_tracked=months_tracked,
        )

    return BadgeDto(
        key="year_tracked",
        name="Year Tracked",
        headline=f"Thanks for a great year, {username}!",
        description="You showed up and tracked your money this year — that's the foundation everything else is built on.",
        months_on_track=months_on_track,
        months_tracked=months_tracked,
    )
