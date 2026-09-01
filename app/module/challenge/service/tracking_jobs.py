"""
Scheduled auto-tracking for the no_spend and budget_category challenge types —
both are driven entirely by real Expense data, mirroring the badge jobs in
app/module/budget/service/budget_alert_service.py, but updating a real
SavingsChallenge row (streak / current_period_spent / status) instead of just
awarding a one-off badge. Wired into core/scheduler.py via main.py's lifespan.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.common.enums.challenge import ChallengeStatus, ChallengeType
from app.common.finance_queries import expense_total, expense_total_for_category
from app.database.session import AsyncSessionLocal
from app.module.challenge.schema.challenge import SavingsChallenge
from app.module.challenge.service._helpers import iso_week_key, weeks_between
from app.module.challenge.service.badge_service import BadgeService
from app.module.notification.service.push_service import PushService

logger = logging.getLogger(__name__)

# Consecutive no-spend weeks -> badge key. Same milestones as Friday Savings'
# STREAK_BADGE_WEEKS in challenge_entry_service.py, distinct keys since it's a
# separate challenge type.
NO_SPEND_STREAK_BADGE_WEEKS = {
    4: "no_spend_streak_4_weeks",
    12: "no_spend_streak_12_weeks",
    26: "no_spend_streak_26_weeks",
    52: "no_spend_streak_52_weeks",
}


async def check_no_spend_challenges() -> None:
    """Runs daily; only acts on Monday, evaluating the week that just ended."""
    today = date.today()
    if today.weekday() != 0:  # Monday
        return

    week_start = today - timedelta(days=7)
    week_end = today - timedelta(days=1)
    start = datetime(week_start.year, week_start.month, week_start.day)
    end = datetime(week_end.year, week_end.month, week_end.day, 23, 59, 59)
    current_week = iso_week_key(week_start)

    async with AsyncSessionLocal() as db:
        push = PushService(db)
        badges = BadgeService(db)

        rows = await db.execute(
            select(SavingsChallenge).where(
                SavingsChallenge.type == ChallengeType.NO_SPEND,
                SavingsChallenge.status == ChallengeStatus.ACTIVE,
            )
        )
        for challenge in rows.scalars().all():
            if challenge.last_entry_week == current_week:
                continue  # already processed this week

            spent = await expense_total(db, challenge.user_id, start, end)
            if spent > 0:
                challenge.current_streak = 0
                challenge.last_entry_week = current_week
                continue

            if challenge.last_entry_week is None:
                challenge.current_streak = 1
            else:
                gap = weeks_between(challenge.last_entry_week, current_week)
                challenge.current_streak = challenge.current_streak + 1 if gap == 1 else 1
            challenge.longest_streak = max(challenge.longest_streak, challenge.current_streak)
            challenge.last_entry_week = current_week

            badge_key = NO_SPEND_STREAK_BADGE_WEEKS.get(challenge.current_streak)
            if badge_key:
                awarded = await badges.award(challenge.user_id, badge_key, challenge_id=challenge.id)
                if awarded:
                    await push.send_to_user(
                        challenge.user_id,
                        title=f"🔥 {challenge.current_streak}-week no-spend streak!",
                        body=(
                            f"You've kept up '{challenge.name}' for {challenge.current_streak} weeks "
                            f"straight. New badge: {awarded.name}."
                        ),
                        data={"type": "streak_badge", "challenge_id": str(challenge.id)},
                    )

        await db.commit()


async def check_budget_category_challenges() -> None:
    """Runs daily. Updates running spend and finalizes challenges past their end_date."""
    today = date.today()

    async with AsyncSessionLocal() as db:
        push = PushService(db)
        badges = BadgeService(db)

        rows = await db.execute(
            select(SavingsChallenge).where(
                SavingsChallenge.type == ChallengeType.BUDGET_CATEGORY,
                SavingsChallenge.status == ChallengeStatus.ACTIVE,
            )
        )
        for challenge in rows.scalars().all():
            period_start = challenge.start_date
            period_end = min(today, challenge.end_date)
            if period_end < period_start:
                continue

            spent = await expense_total_for_category(
                db,
                challenge.user_id,
                challenge.target_category_id,
                datetime(period_start.year, period_start.month, period_start.day),
                datetime(period_end.year, period_end.month, period_end.day, 23, 59, 59),
            )
            challenge.current_period_spent = Decimal(str(spent))

            if challenge.end_date >= today:
                continue  # period still open, just updated running spend

            if spent <= float(challenge.overall_target):
                challenge.status = ChallengeStatus.COMPLETED
                challenge.concluded_at = func.now()
                awarded = await badges.award(
                    challenge.user_id, "budget_category_goal_reached", challenge_id=challenge.id
                )
                if awarded:
                    await push.send_to_user(
                        challenge.user_id,
                        title="Challenge complete! 🎉",
                        body=f"You stayed under budget for '{challenge.name}'.",
                        data={"type": "challenge_completed", "challenge_id": str(challenge.id)},
                    )
            else:
                challenge.status = ChallengeStatus.FAILED
                challenge.concluded_at = func.now()
                await push.send_to_user(
                    challenge.user_id,
                    title="Challenge missed",
                    body=f"You went over your spend cap for '{challenge.name}'.",
                    data={"type": "challenge_failed", "challenge_id": str(challenge.id)},
                )

        await db.commit()
