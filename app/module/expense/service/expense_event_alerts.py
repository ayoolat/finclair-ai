import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.common.enums.notification import NotificationType
from app.common.timezone import APP_TZ, local_day_end, local_day_start
from app.core.config import settings
from app.module.budget.service.budget_alert_service import evaluate_budget_thresholds
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.notification.schema.notification import Notification
from app.module.notification.service.notification_service import NotificationService

logger = logging.getLogger(__name__)

_LARGE_TXN_LOOKBACK_DAYS = 30
_UNUSUAL_BASELINE_DAYS = 28
_UNUSUAL_MIN_BASELINE_TXNS = 3


def _symbol_for(currency: str | None) -> str:
    return "₦" if (not currency or currency == "NGN") else currency


async def run_expense_alerts(
    db,
    notifications: NotificationService,
    user_id: uuid.UUID,
    expense: Expense,
) -> None:
    """Best-effort — logs and swallows any failure so expense creation is never
    blocked by an alert."""
    try:
        primary_category = expense.categories[0] if expense.categories else None
        symbol = _symbol_for(expense.currency)

        if primary_category is not None:
            await _maybe_large_transaction(db, notifications, user_id, expense, primary_category, symbol)
            await _maybe_unusual_spending(db, notifications, user_id, primary_category, symbol)

        category_ids = [c.id for c in expense.categories]
        await evaluate_budget_thresholds(db, notifications, user_id, category_ids or None)
    except Exception as exc:
        logger.error("Expense alerts failed for user %s expense %s: %s", user_id, expense.id, exc)


async def _already_alerted_today(
    db, user_id: uuid.UUID, ntype: NotificationType, category_id: uuid.UUID
) -> bool:
    today = datetime.now(APP_TZ).date()
    row = await db.execute(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.type == ntype.value,
            Notification.created_at >= local_day_start(today),
            Notification.data["category_id"].astext == str(category_id),
        )
    )
    return row.first() is not None


async def _maybe_large_transaction(
    db, notifications: NotificationService, user_id: uuid.UUID, expense: Expense, category, symbol: str
) -> None:
    now = datetime.now(APP_TZ)
    lookback_start = now - timedelta(days=_LARGE_TXN_LOOKBACK_DAYS)

    row = await db.execute(
        select(func.count(Expense.id), func.avg(Expense.amount))
        .join(expense_categories, expense_categories.c.expense_id == Expense.id)
        .where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
            Expense.id != expense.id,
            expense_categories.c.category_id == category.id,
            Expense.expense_date >= lookback_start,
        )
    )
    prior_count, prior_avg = row.one()
    if prior_count < settings.large_txn_min_history or not prior_avg:
        return

    amount = float(expense.amount)
    if amount < float(prior_avg) * settings.large_txn_multiplier:
        return

    if await _already_alerted_today(db, user_id, NotificationType.LARGE_TRANSACTION, category.id):
        return

    await notifications.notify(
        user_id,
        NotificationType.LARGE_TRANSACTION,
        title="Larger than usual",
        body=(
            f"You just spent {symbol}{amount:,.2f}. That's higher than your usual "
            f"{category.name} spending."
        ),
        data={
            "expense_id": str(expense.id),
            "category_id": str(category.id),
            "amount": str(amount),
        },
    )


async def _maybe_unusual_spending(
    db, notifications: NotificationService, user_id: uuid.UUID, category, symbol: str
) -> None:
    today = datetime.now(APP_TZ).date()
    today_start = local_day_start(today)
    today_end = local_day_end(today)
    baseline_start = local_day_start(today - timedelta(days=_UNUSUAL_BASELINE_DAYS))
    baseline_end = today_start - timedelta(seconds=1)

    today_row, baseline_row = (
        await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .join(expense_categories, expense_categories.c.expense_id == Expense.id)
            .where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                expense_categories.c.category_id == category.id,
                Expense.expense_date >= today_start,
                Expense.expense_date <= today_end,
            )
        ),
        await db.execute(
            select(func.count(Expense.id), func.coalesce(func.sum(Expense.amount), 0))
            .join(expense_categories, expense_categories.c.expense_id == Expense.id)
            .where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                expense_categories.c.category_id == category.id,
                Expense.expense_date >= baseline_start,
                Expense.expense_date <= baseline_end,
            )
        ),
    )
    today_total = float(today_row.scalar_one())
    baseline_count, baseline_sum = baseline_row.one()
    if baseline_count < _UNUSUAL_MIN_BASELINE_TXNS or not baseline_sum:
        return

    daily_avg = float(baseline_sum) / _UNUSUAL_BASELINE_DAYS
    if daily_avg <= 0 or today_total < daily_avg * settings.unusual_daily_multiplier:
        return

    if await _already_alerted_today(db, user_id, NotificationType.UNUSUAL_SPENDING, category.id):
        return

    await notifications.notify(
        user_id,
        NotificationType.UNUSUAL_SPENDING,
        title="This is unusual for you 👀",
        body=f"You've spent {symbol}{today_total:,.2f} on {category.name} today.",
        data={
            "category_id": str(category.id),
            "today_total": str(today_total),
        },
    )
