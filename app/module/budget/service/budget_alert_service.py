"""
Scheduled checks over real Budget/Expense data — separate from the isolated
savings-challenge feature. Two concerns, both wired into core/scheduler.py via
main.py's lifespan:

  - check_no_spend_weekend: congratulates a user who logged zero expenses over
    the weekend that just ended.
  - check_budget_health: warns when a budget (overall or a single category
    allocation) is approaching its limit, and congratulates when a finished
    budget period came in under budget.

Both award badges from the shared catalog (see app/module/challenge) and send
a push notification through the shared PushService.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.common.finance_queries import expense_total
from app.database.session import AsyncSessionLocal
from app.module.budget.schema.budget import Budget
from app.module.budget.schema.budget_allocation import BudgetAllocation
from app.module.budget.schema.budget_alert import BudgetAlert
from app.module.challenge.service.badge_service import BadgeService
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.notification.service.push_service import PushService

logger = logging.getLogger(__name__)

NEAR_LIMIT_THRESHOLD = 0.9


async def check_no_spend_weekend() -> None:
    """Runs daily; only acts on Monday, evaluating the weekend that just ended."""
    today = date.today()
    if today.weekday() != 0:  # Monday
        return

    saturday = today - timedelta(days=2)
    sunday = today - timedelta(days=1)
    start = datetime(saturday.year, saturday.month, saturday.day)
    end = datetime(sunday.year, sunday.month, sunday.day, 23, 59, 59)

    async with AsyncSessionLocal() as db:
        # Bounded to recently-active users rather than scanning every account.
        user_rows = await db.execute(
            select(Expense.user_id)
            .distinct()
            .where(Expense.deleted_at.is_(None), Expense.expense_date >= start - timedelta(days=14))
        )
        user_ids = [row[0] for row in user_rows.all()]
        if not user_ids:
            return

        push = PushService(db)
        badges = BadgeService(db)
        period = saturday.isoformat()

        for user_id in user_ids:
            weekend_total = await expense_total(db, user_id, start, end)
            if weekend_total > 0:
                continue
            awarded = await badges.award(user_id, "no_spend_weekend", period=period)
            if awarded:
                await push.send_to_user(
                    user_id,
                    title="No-spend weekend! 🎉",
                    body="You didn't log a single expense this weekend. Nicely done.",
                    data={"type": "no_spend_weekend"},
                )
        await db.commit()


async def check_budget_health() -> None:
    """Runs daily — warns when nearing a limit, congratulates on a clean finish."""
    today = date.today()
    async with AsyncSessionLocal() as db:
        push = PushService(db)
        badges = BadgeService(db)

        active_rows = await db.execute(
            select(Budget)
            .options(selectinload(Budget.allocations).selectinload(BudgetAllocation.category))
            .where(Budget.start_date <= today, Budget.end_date >= today)
        )
        for budget in active_rows.scalars().all():
            spent = await _budget_spent(db, budget)
            await _maybe_near_limit(db, push, budget, None, "your overall budget", spent, float(budget.amount_allocated))
            for alloc in budget.allocations:
                cat_spent = await _category_spent(db, budget, alloc.category_id)
                await _maybe_near_limit(
                    db, push, budget, alloc.category_id, alloc.category.name, cat_spent, float(alloc.amount_allocated)
                )

        ended_rows = await db.execute(
            select(Budget)
            .options(selectinload(Budget.allocations).selectinload(BudgetAllocation.category))
            .where(Budget.end_date == today - timedelta(days=1))
        )
        for budget in ended_rows.scalars().all():
            spent = await _budget_spent(db, budget)
            if spent <= float(budget.amount_allocated):
                await _maybe_completed(
                    db, push, badges, budget, None, "your budget", period=budget.start_date.strftime("%Y-%m")
                )
            for alloc in budget.allocations:
                cat_spent = await _category_spent(db, budget, alloc.category_id)
                if cat_spent <= float(alloc.amount_allocated):
                    await _maybe_completed(
                        db, push, badges, budget, alloc.category_id, alloc.category.name,
                        period=f"{budget.start_date:%Y-%m}:{alloc.category_id}",
                    )

        await db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _budget_spent(db, budget: Budget) -> float:
    return await expense_total(
        db,
        budget.user_id,
        datetime(budget.start_date.year, budget.start_date.month, budget.start_date.day),
        datetime(budget.end_date.year, budget.end_date.month, budget.end_date.day, 23, 59, 59),
    )


async def _category_spent(db, budget: Budget, category_id) -> float:
    row = await db.execute(
        select(func.sum(Expense.amount))
        .join(expense_categories, expense_categories.c.expense_id == Expense.id)
        .where(
            Expense.user_id == budget.user_id,
            Expense.deleted_at.is_(None),
            Expense.expense_date >= datetime(budget.start_date.year, budget.start_date.month, budget.start_date.day),
            Expense.expense_date <= datetime(budget.end_date.year, budget.end_date.month, budget.end_date.day, 23, 59, 59),
            expense_categories.c.category_id == category_id,
        )
    )
    return float(row.scalar_one() or 0)


async def _alert_exists(db, budget_id, category_id, alert_type: str) -> bool:
    category_clause = BudgetAlert.category_id == category_id if category_id else BudgetAlert.category_id.is_(None)
    row = await db.execute(
        select(BudgetAlert.id).where(
            BudgetAlert.budget_id == budget_id, category_clause, BudgetAlert.alert_type == alert_type
        )
    )
    return row.first() is not None


async def _maybe_near_limit(db, push: PushService, budget: Budget, category_id, label: str, spent: float, allocated: float) -> None:
    if allocated <= 0 or spent / allocated < NEAR_LIMIT_THRESHOLD:
        return
    if await _alert_exists(db, budget.id, category_id, "near_limit"):
        return

    pct = spent / allocated * 100
    await push.send_to_user(
        budget.user_id,
        title="Approaching your budget limit",
        body=f"You've used {pct:.0f}% of {label} this month.",
        data={"type": "budget_near_limit"},
    )
    db.add(BudgetAlert(budget_id=budget.id, category_id=category_id, alert_type="near_limit"))


async def _maybe_completed(db, push: PushService, badges: BadgeService, budget: Budget, category_id, label: str, period: str) -> None:
    if await _alert_exists(db, budget.id, category_id, "completed"):
        return

    badge_key = "category_budget_hero" if category_id else "budget_hero"
    await badges.award(budget.user_id, badge_key, period=period)
    await push.send_to_user(
        budget.user_id,
        title="You stayed within budget! 🎉",
        body=f"You finished the month within {label}.",
        data={"type": "budget_completed"},
    )
    db.add(BudgetAlert(budget_id=budget.id, category_id=category_id, alert_type="completed"))
