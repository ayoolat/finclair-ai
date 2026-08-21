"""
Two scheduled daily notifications, wired into core/scheduler.py via main.py's
lifespan, both push + in-app via the shared NotificationService:

  - send_daily_expense_summaries: fires at 9:00 PM WAT, tells each active user
    what they spent that (local) day, plus their highest-spending category.
  - send_daily_ai_tips: fires at 9:00 AM WAT, an observation grounded in the
    user's own transaction data (a notable category shift vs. their usual
    weekly average, or their dominant category this week). Sends nothing if
    there's no real signal in the data, rather than a generic filler tip.

Both are scoped to "active" users (logged an expense in the last 30 days)
rather than every registered account, so a signed-up-but-never-used account
doesn't get nightly "no spend today!" notifications forever.
"""

import asyncio
import logging
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select

from app.common.enums.notification import NotificationType
from app.common.finance_queries import category_totals, expense_total
from app.common.timezone import APP_TZ, local_day_end, local_day_start
from app.database.session import AsyncSessionLocal
from app.module.expense.schema.expense import Expense
from app.module.notification.service.notification_service import NotificationService
from app.module.notification.service.push_service import PushService
from app.module.user.schema.user import User

logger = logging.getLogger(__name__)

_ACTIVE_WINDOW_DAYS = 30
_WEEK_DAYS = 7
_BASELINE_WEEKS = 4
_NOTABLE_CHANGE_PCT = 20
_DOMINANT_CATEGORY_PCT = 40


async def send_daily_expense_summaries() -> None:
    today = datetime.now(APP_TZ).date()
    day_start = local_day_start(today)
    day_end = local_day_end(today)

    async with AsyncSessionLocal() as db:
        push = PushService(db)
        notifications = NotificationService(db, push)

        user_ids = await _active_user_ids(db, day_start)

        for user_id, currency in user_ids:
            symbol = "₦" if currency == "NGN" else currency
            total, top = await asyncio.gather(
                expense_total(db, user_id, day_start, day_end),
                category_totals(db, user_id, day_start, day_end, limit=1),
            )
            if total > 0:
                body = f"You spent {symbol}{total:,.2f} today."
                if top:
                    top_name, _icon, top_amount = top[0]
                    body += f" Your highest spending category was {top_name} {symbol}{top_amount:,.2f}."
                await notifications.notify(
                    user_id,
                    NotificationType.DAILY_EXPENSE_SUMMARY,
                    title="Today's spending",
                    body=body,
                    data={"date": today.isoformat(), "total": str(total)},
                )
            else:
                await notifications.notify(
                    user_id,
                    NotificationType.DAILY_EXPENSE_SUMMARY,
                    title="No spend today 🎉",
                    body="No expenses logged today, nice!",
                    data={"date": today.isoformat(), "total": "0"},
                )


async def send_daily_ai_tips() -> None:
    today = datetime.now(APP_TZ).date()
    day_start = local_day_start(today)

    async with AsyncSessionLocal() as db:
        push = PushService(db)
        notifications = NotificationService(db, push)

        user_ids = await _active_user_ids(db, day_start)

        for user_id, currency in user_ids:
            symbol = "₦" if currency == "NGN" else currency
            observation = await _money_tip_observation(db, user_id, symbol, today)
            if observation is None:
                continue
            title, body = observation
            await notifications.notify(
                user_id,
                NotificationType.DAILY_AI_TIP,
                title=title,
                body=body,
            )


async def _money_tip_observation(
    db, user_id: uuid.UUID, symbol: str, today: date
) -> Optional[tuple[str, str]]:
    """Finds one real observation in the user's own category spending this
    week vs. their usual weekly average over the trailing 4 weeks. Returns
    None if there's nothing notable to say, rather than a generic filler."""
    this_start = local_day_start(today - timedelta(days=_WEEK_DAYS - 1))
    this_end = local_day_end(today)
    baseline_end = this_start - timedelta(seconds=1)
    baseline_start = local_day_start(
        baseline_end.date() - timedelta(days=_WEEK_DAYS * _BASELINE_WEEKS - 1)
    )

    this_week_rows, baseline_rows = await asyncio.gather(
        category_totals(db, user_id, this_start, this_end),
        category_totals(db, user_id, baseline_start, baseline_end),
    )
    if not this_week_rows:
        return None

    this_week_by_cat = {name: amount for name, _icon, amount in this_week_rows}
    baseline_avg_by_cat = {name: amount / _BASELINE_WEEKS for name, _icon, amount in baseline_rows}

    best_name: Optional[str] = None
    best_amount = 0.0
    best_pct_change = 0.0
    for name, this_amount in this_week_by_cat.items():
        avg = baseline_avg_by_cat.get(name, 0.0)
        if avg <= 0:
            continue
        pct_change = (this_amount - avg) / avg * 100
        if abs(pct_change) < _NOTABLE_CHANGE_PCT:
            continue
        if best_name is None or abs(pct_change) > abs(best_pct_change):
            best_name, best_amount, best_pct_change = name, this_amount, pct_change

    if best_name is not None:
        if best_pct_change > 0:
            body = random.choice([
                f"You've spent {symbol}{best_amount:,.0f} on {best_name} this week, {best_pct_change:.0f}% more than your usual weekly average. Want to take a look at what changed?",
                f"{best_name} spending is up {best_pct_change:.0f}% this week compared to your usual average, {symbol}{best_amount:,.0f} so far.",
                f"Your {best_name} spending this week ({symbol}{best_amount:,.0f}) is running {best_pct_change:.0f}% above your usual weekly average.",
            ])
        else:
            body = random.choice([
                f"Your {best_name} spending has dropped {abs(best_pct_change):.0f}% this week compared to your usual average.",
                f"{best_name} spending is down {abs(best_pct_change):.0f}% this week versus your usual average. Nice work.",
                f"You've spent {abs(best_pct_change):.0f}% less on {best_name} this week than usual.",
            ])
        return "💡 Clara noticed something", body

    # No category has enough baseline history for a confident comparison.
    # Fall back to naming the dominant category this week, if there is one.
    week_total = sum(this_week_by_cat.values())
    top_name, top_amount = max(this_week_by_cat.items(), key=lambda kv: kv[1])
    top_share = (top_amount / week_total * 100) if week_total > 0 else 0
    if top_share >= _DOMINANT_CATEGORY_PCT:
        body = random.choice([
            f"{top_name} is your biggest category this week at {symbol}{top_amount:,.0f}.",
            f"Most of this week's spending went to {top_name}, {symbol}{top_amount:,.0f} so far.",
            f"Your top category this week is {top_name} at {symbol}{top_amount:,.0f}.",
        ])
        return "💡 Clara noticed something", body

    return None


async def _active_user_ids(db, as_of_day_start: datetime) -> list[tuple]:
    rows = await db.execute(
        select(Expense.user_id, User.default_currency)
        .join(User, User.id == Expense.user_id)
        .distinct()
        .where(
            Expense.deleted_at.is_(None),
            Expense.expense_date >= as_of_day_start - timedelta(days=_ACTIVE_WINDOW_DAYS),
        )
    )
    return [(row[0], row[1]) for row in rows.all()]
