"""
Two scheduled daily notifications, wired into core/scheduler.py via main.py's
lifespan — both push + in-app via the shared NotificationService:

  - send_daily_expense_summaries: fires at 9:00 PM WAT, tells each active user
    what they spent that (local) day, or congratulates a no-spend day.
  - send_daily_ai_tips: fires at 9:00 AM WAT, a random general money tip —
    not personalized to the user's own data.

Both are scoped to "active" users (logged an expense in the last 30 days)
rather than every registered account, so a signed-up-but-never-used account
doesn't get nightly "no spend today!" notifications forever.
"""

import logging
import random
from datetime import datetime, timedelta

from sqlalchemy import select

from app.common.enums.notification import NotificationType
from app.common.finance_queries import expense_total
from app.common.timezone import APP_TZ, local_day_end, local_day_start
from app.database.session import AsyncSessionLocal
from app.module.expense.schema.expense import Expense
from app.module.notification.service.notification_service import NotificationService
from app.module.notification.service.push_service import PushService
from app.module.user.schema.user import User

logger = logging.getLogger(__name__)

_ACTIVE_WINDOW_DAYS = 30

_MONEY_TIPS = [
    "Track every transaction for a week — small purchases add up faster than you'd expect.",
    "Before a big purchase, wait 24 hours. If you still want it tomorrow, it's probably worth it.",
    "Automate your savings — move money the day you get paid, before you can spend it.",
    "Review your subscriptions this month. Cancel anything you haven't used in 60 days.",
    "Set a weekly spending check-in — a 5-minute glance catches problems before they grow.",
    "Pay yourself first: treat savings like a fixed bill, not what's left over.",
    "Round up your purchases and sink the difference into savings — it adds up quietly.",
    "Compare prices before big purchases. A 10-minute search can save real money.",
    "Cook at home twice more this week than usual — food delivery fees add up fast.",
    "Give every naira a job. A budget isn't a restriction, it's a plan for your money.",
    "Build an emergency fund of one month's expenses before chasing bigger investment goals.",
    "Unsubscribe from marketing emails that tempt you into impulse buys.",
    "Track your net worth monthly, not just your spending — it shows the bigger picture.",
    "Negotiate your recurring bills once a year — many providers offer better rates if you ask.",
    "Avoid shopping when you're bored, stressed, or tired — those purchases are rarely planned.",
]


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
            total = await expense_total(db, user_id, day_start, day_end)
            if total > 0:
                await notifications.notify(
                    user_id,
                    NotificationType.DAILY_EXPENSE_SUMMARY,
                    title="Today's spending",
                    body=f"You spent {symbol}{total:,.2f} today.",
                    data={"date": today.isoformat(), "total": str(total)},
                )
            else:
                await notifications.notify(
                    user_id,
                    NotificationType.DAILY_EXPENSE_SUMMARY,
                    title="No spend today 🎉",
                    body="No expenses logged today — nice!",
                    data={"date": today.isoformat(), "total": "0"},
                )


async def send_daily_ai_tips() -> None:
    today = datetime.now(APP_TZ).date()
    day_start = local_day_start(today)

    async with AsyncSessionLocal() as db:
        push = PushService(db)
        notifications = NotificationService(db, push)

        user_ids = await _active_user_ids(db, day_start)

        for user_id, _currency in user_ids:
            await notifications.notify(
                user_id,
                NotificationType.DAILY_AI_TIP,
                title="💡 Money tip of the day",
                body=random.choice(_MONEY_TIPS),
            )


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
