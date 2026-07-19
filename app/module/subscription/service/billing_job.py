import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.subscription import SubscriptionStatus
from app.common.payment.factory import get_payment_provider
from app.database.session import AsyncSessionLocal
from app.module.subscription.schema.subscription import (
    Subscription,
    SubscriptionPlan,
    SubscriptionTransaction,
)

logger = logging.getLogger(__name__)

_PAST_DUE_GRACE = timedelta(days=3)


async def process_subscription_billing() -> None:
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Subscription))
        subscriptions = list(result.scalars().all())

        for subscription in subscriptions:
            try:
                await _process_one(session, subscription, now)
            except Exception as exc:
                logger.error("Subscription billing failed for %s: %s", subscription.id, exc)
                await session.rollback()

    logger.info("Subscription billing  ✓  processed %d subscriptions", len(subscriptions))


async def _process_one(session: AsyncSession, subscription: Subscription, now: datetime) -> None:
    if (
        subscription.status == SubscriptionStatus.TRIALING.value
        and subscription.trial_end
        and subscription.trial_end <= now
    ):
        await _charge_and_update(session, subscription, now, reason="trial_conversion")

    elif (
        subscription.status == SubscriptionStatus.ACTIVE.value
        and not subscription.cancel_at_period_end
        and subscription.current_period_end
        and subscription.current_period_end <= now
    ):
        await _charge_and_update(session, subscription, now, reason="renewal")

    elif (
        subscription.status == SubscriptionStatus.ACTIVE.value
        and subscription.cancel_at_period_end
        and subscription.current_period_end
        and subscription.current_period_end <= now
    ):
        subscription.status = SubscriptionStatus.CANCELED.value
        await session.commit()

    elif subscription.status == SubscriptionStatus.PAST_DUE.value:
        if subscription.past_due_since and now - subscription.past_due_since >= _PAST_DUE_GRACE:
            subscription.status = SubscriptionStatus.EXPIRED.value
            await session.commit()
        else:
            await _charge_and_update(session, subscription, now, reason="past_due_retry")


async def _charge_and_update(
    session: AsyncSession, subscription: Subscription, now: datetime, *, reason: str
) -> None:
    result = await session.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.code == subscription.plan_code)
    )
    plan = result.scalar_one()

    if not subscription.paystack_authorization_code or not subscription.paystack_email:
        logger.warning(
            "Subscription %s missing Paystack authorization details; marking past_due", subscription.id
        )
        subscription.status = SubscriptionStatus.PAST_DUE.value
        subscription.past_due_since = subscription.past_due_since or now
        await session.commit()
        return

    reference = f"sub_{subscription.id}_{int(now.timestamp())}"
    charge_status = None
    gateway_response = None
    provider = get_payment_provider()
    try:
        data = await provider.charge_authorization(
            authorization_code=subscription.paystack_authorization_code,
            email=subscription.paystack_email,
            amount=plan.amount,
            reference=reference,
        )
        charge_status = data.get("status")
        gateway_response = data.get("gateway_response")
    except httpx.HTTPError as exc:
        logger.warning("Payment provider charge_authorization failed for subscription %s: %s", subscription.id, exc)

    succeeded = charge_status == "success"

    session.add(
        SubscriptionTransaction(
            subscription_id=subscription.id,
            paystack_reference=reference,
            amount=plan.amount,
            currency=plan.currency,
            status="success" if succeeded else "failed",
            reason=reason,
            gateway_response=gateway_response,
            paid_at=now if succeeded else None,
        )
    )

    if succeeded:
        subscription.status = SubscriptionStatus.ACTIVE.value
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=plan.interval_days)
        subscription.past_due_since = None
    else:
        subscription.status = SubscriptionStatus.PAST_DUE.value
        subscription.past_due_since = subscription.past_due_since or now

    await session.commit()
