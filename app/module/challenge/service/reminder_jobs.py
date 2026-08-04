"""Scheduled reminder for active Friday Savings Challenges — wired into main.py's lifespan via schedule_daily."""

from datetime import date

from sqlalchemy import or_, select

from app.common.enums.challenge import ChallengeStatus, ChallengeType
from app.database.session import AsyncSessionLocal
from app.module.challenge.schema.challenge import SavingsChallenge
from app.module.challenge.service._helpers import iso_week_key
from app.module.notification.service.push_service import PushService


async def send_friday_savings_reminders() -> None:
    """Runs daily; only acts on Friday, nudging anyone who hasn't logged this week yet."""
    if date.today().weekday() != 4:  # Friday
        return

    current_week = iso_week_key(date.today())
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(SavingsChallenge).where(
                SavingsChallenge.type == ChallengeType.FRIDAY_SAVINGS,
                SavingsChallenge.status == ChallengeStatus.ACTIVE,
                or_(
                    SavingsChallenge.last_entry_week != current_week,
                    SavingsChallenge.last_entry_week.is_(None),
                ),
            )
        )
        push = PushService(db)
        for challenge in rows.scalars().all():
            body = (
                f"You're on a {challenge.current_streak}-week streak — log today's savings to keep it alive."
                if challenge.current_streak > 0
                else f"Time to save for '{challenge.name}'. Log today's contribution to start your streak."
            )
            await push.send_to_user(
                challenge.user_id,
                title="It's Friday! 💰",
                body=body,
                data={"type": "friday_reminder", "challenge_id": str(challenge.id)},
            )
