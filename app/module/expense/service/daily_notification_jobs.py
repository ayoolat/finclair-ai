"""
Scheduled expense notifications, wired into core/scheduler.py via main.py's
lifespan, all push + in-app via the shared NotificationService:

  - send_midday_spending_checks: fires at 12:00 PM WAT. Tells each active user
    what they've spent so far that (local) day, so they can course-correct
    before the day ends. Silent for users with nothing logged yet at midday.

  - dispatch_evening_spending_checks: runs every 15 minutes and sends each
    active user their evening spending check when their personalized reminder
    time (default 9:00 PM, User.reminder_hour/minute) falls due. This is framed
    as a *reminder to finish logging*, not a closed-out daily summary: an
    expense entered at 10:30 PM still belongs to today, and Clara reconciles
    any total that grew after the check (see ClaraService.home_insight).

  - send_daily_ai_tips: fires at 9:00 AM WAT, an observation grounded in the
    user's own transaction data (a notable category shift vs. their usual
    weekly average, or their dominant category this week). Sends nothing if
    there's no real signal in the data, rather than a generic filler tip.

There is deliberately no midnight notification — users who keep late hours
shouldn't be pushed at 12 AM just because the financial day rolled over.

All jobs are scoped to "active" users (logged an expense in the last 30 days)
rather than every registered account, so a signed-up-but-never-used account
doesn't get nightly notifications forever.
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
from app.module.notification.schema.notification import Notification
from app.module.notification.service.notification_service import NotificationService
from app.module.notification.service.push_service import PushService
from app.module.user.schema.user import User

logger = logging.getLogger(__name__)

_ACTIVE_WINDOW_DAYS = 30
_EVENING_DISPATCH_WINDOW_MINUTES = 15
_WEEK_DAYS = 7
_BASELINE_WEEKS = 4
_NOTABLE_CHANGE_PCT = 20
_DOMINANT_CATEGORY_PCT = 40


def _symbol_for(currency: Optional[str]) -> str:
    return "₦" if (not currency or currency == "NGN") else currency


# ── Midday spending check (12:00 PM, global) ──────────────────────────────────


async def send_midday_spending_checks() -> None:
    today = datetime.now(APP_TZ).date()
    day_start = local_day_start(today)
    day_end = local_day_end(today)

    async with AsyncSessionLocal() as db:
        push = PushService(db)
        notifications = NotificationService(db, push)

        for user in await _active_users(db, day_start):
            total = await expense_total(db, user.id, day_start, day_end)
            if total <= 0:
                continue
            symbol = _symbol_for(user.default_currency)
            await notifications.notify(
                user.id,
                NotificationType.MIDDAY_SPENDING_CHECK,
                title="Midday spending check",
                body=f"You've spent {symbol}{total:,.2f} so far today.",
                data={"date": today.isoformat(), "total": str(total), "kind": "midday_check"},
            )


# ── Evening spending check (personalized time, dispatched every 15 min) ───────


async def dispatch_evening_spending_checks() -> None:
    now = datetime.now(APP_TZ)
    today = now.date()
    day_start = local_day_start(today)
    day_end = local_day_end(today)
    now_minute_of_day = now.hour * 60 + now.minute

    async with AsyncSessionLocal() as db:
        push = PushService(db)
        notifications = NotificationService(db, push)

        candidates = [
            user
            for user in await _active_users(db, day_start)
            if user.daily_reminders_enabled and _reminder_due(user, now_minute_of_day)
        ]
        if not candidates:
            return

        already_sent = await _users_already_checked_today(db, [u.id for u in candidates], day_start)

        for user in candidates:
            if user.id in already_sent:
                continue
            symbol = _symbol_for(user.default_currency)
            total = await expense_total(db, user.id, day_start, day_end)
            if total > 0:
                body = (
                    f"You've logged {symbol}{total:,.2f} in expenses today. "
                    "Still have expenses to add? Add them before the day ends."
                )
            else:
                body = (
                    "No expenses logged yet today. Add any before midnight so your "
                    "numbers stay accurate."
                )
            await notifications.notify(
                user.id,
                NotificationType.DAILY_EXPENSE_SUMMARY,
                title="Evening spending check",
                body=body,
                data={"date": today.isoformat(), "total": str(total), "kind": "evening_check"},
            )


def _reminder_due(user, now_minute_of_day: int) -> bool:
    target_minute_of_day = user.reminder_hour * 60 + user.reminder_minute
    delta = (now_minute_of_day - target_minute_of_day) % (24 * 60)
    return 0 <= delta < _EVENING_DISPATCH_WINDOW_MINUTES


async def _users_already_checked_today(
    db, user_ids: list[uuid.UUID], day_start: datetime
) -> set[uuid.UUID]:
    rows = await db.execute(
        select(Notification.user_id)
        .distinct()
        .where(
            Notification.user_id.in_(user_ids),
            Notification.type == NotificationType.DAILY_EXPENSE_SUMMARY.value,
            Notification.created_at >= day_start,
        )
    )
    return {row[0] for row in rows.all()}


# ── Daily AI money tip (9:00 AM, global) ─────────────────────────────────────


async def send_daily_ai_tips() -> None:
    today = datetime.now(APP_TZ).date()
    day_start = local_day_start(today)

    async with AsyncSessionLocal() as db:
        push = PushService(db)
        notifications = NotificationService(db, push)

        for user in await _active_users(db, day_start):
            symbol = _symbol_for(user.default_currency)
            observation = await _money_tip_observation(db, user.id, symbol, today)
            if observation is None:
                continue
            title, body = observation
            await notifications.notify(
                user.id,
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


async def _active_users(db, as_of_day_start: datetime) -> list:
    """Users who logged an expense in the trailing 30 days, as detached column
    rows (`.id`, `.default_currency`, `.reminder_hour`, `.reminder_minute`,
    `.daily_reminders_enabled`) — not ORM instances, so a `notify()` commit
    mid-loop doesn't expire them and trigger a lazy reload."""
    rows = await db.execute(
        select(
            User.id,
            User.default_currency,
            User.reminder_hour,
            User.reminder_minute,
            User.daily_reminders_enabled,
        )
        .join(Expense, Expense.user_id == User.id)
        .where(
            Expense.deleted_at.is_(None),
            Expense.expense_date >= as_of_day_start - timedelta(days=_ACTIVE_WINDOW_DAYS),
        )
        .distinct()
    )
    return list(rows.all())
