import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.subscription import SubscriptionStatus
from app.common.payment.factory import get_payment_provider
from app.common.response import Result
from app.database.session import get_db
from app.module.subscription.dto.subscription import (
    PlanDto,
    PlansResponseDto,
    SubscriptionDto,
    VerifyCheckoutDto,
)
from app.module.subscription.schema.subscription import (
    Subscription,
    SubscriptionPlan,
    SubscriptionTransaction,
)

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = {SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE}


class SubscriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_plans(self) -> Result[PlansResponseDto]:
        result = await self._db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.is_active == True)  # noqa: E712
        )
        plans = [PlanDto.model_validate(row) for row in result.scalars().all()]
        provider = get_payment_provider()
        return Result.ok(PlansResponseDto(paystack_public_key=provider.public_key, plans=plans))

    async def get_my_subscription(self, user_id: uuid.UUID) -> Result[SubscriptionDto]:
        subscription = await self._get_subscription(user_id)
        if subscription is None:
            return Result.ok(SubscriptionDto(status="free"))
        return Result.ok(SubscriptionDto.model_validate(subscription))

    async def verify_checkout(
        self, user_id: uuid.UUID, dto: VerifyCheckoutDto
    ) -> Result[SubscriptionDto]:
        plan = await self._get_plan(dto.plan_code.value)
        if plan is None:
            return Result.fail("Unknown plan.", status_code=400)

        subscription = await self._get_subscription(user_id)

        if subscription is not None and subscription.status in {s.value for s in _ACTIVE_STATUSES}:
            existing_tx = await self._db.execute(
                select(SubscriptionTransaction).where(
                    SubscriptionTransaction.paystack_reference == dto.reference
                )
            )
            if existing_tx.scalar_one_or_none() is not None:
                return Result.ok(SubscriptionDto.model_validate(subscription))
            return Result.fail(
                "You already have an active subscription. Cancel it before subscribing again.",
                status_code=409,
            )

        provider = get_payment_provider()
        try:
            data = await provider.verify_transaction(dto.reference)
        except httpx.HTTPError as exc:
            logger.warning("Payment provider verify_transaction failed for %s: %s", dto.reference, exc)
            return Result.fail("Unable to verify payment. Please try again.", status_code=502)

        if data.get("status") != "success":
            return Result.fail("Payment was not successful.", status_code=400)
        if data.get("amount") != plan.amount or data.get("currency") != plan.currency:
            return Result.fail("Payment amount does not match the selected plan.", status_code=400)

        authorization = data.get("authorization") or {}
        customer = data.get("customer") or {}
        now = datetime.now(timezone.utc)
        trial_already_used = subscription is not None and subscription.trial_end is not None

        if trial_already_used:
            status = SubscriptionStatus.ACTIVE
            trial_end = subscription.trial_end if subscription else None
            period_start = now
            period_end = now + timedelta(days=plan.interval_days)
        else:
            status = SubscriptionStatus.TRIALING
            trial_end = now + timedelta(days=plan.trial_days)
            period_start = now
            period_end = trial_end

        if subscription is None:
            subscription = Subscription(user_id=user_id)
            self._db.add(subscription)

        subscription.plan_code = plan.code
        subscription.status = status.value
        subscription.amount = plan.amount
        subscription.compare_at_amount = plan.compare_at_amount
        subscription.currency = plan.currency
        subscription.paystack_customer_code = customer.get("customer_code")
        subscription.paystack_authorization_code = authorization.get("authorization_code")
        subscription.paystack_email = customer.get("email")
        subscription.trial_end = trial_end
        subscription.current_period_start = period_start
        subscription.current_period_end = period_end
        subscription.cancel_at_period_end = False
        subscription.canceled_at = None
        subscription.past_due_since = None

        await self._db.flush()

        self._db.add(
            SubscriptionTransaction(
                subscription_id=subscription.id,
                paystack_reference=dto.reference,
                amount=plan.amount,
                currency=plan.currency,
                status="success",
                reason="checkout",
                gateway_response=data.get("gateway_response"),
                paid_at=now,
            )
        )
        await self._db.commit()
        await self._db.refresh(subscription)
        return Result.ok(SubscriptionDto.model_validate(subscription))

    async def cancel(self, user_id: uuid.UUID) -> Result[SubscriptionDto]:
        subscription = await self._get_subscription(user_id)
        if subscription is None or subscription.status not in {s.value for s in _ACTIVE_STATUSES}:
            return Result.fail("No active subscription to cancel.", status_code=400)

        subscription.cancel_at_period_end = True
        subscription.canceled_at = datetime.now(timezone.utc)
        await self._db.commit()
        await self._db.refresh(subscription)
        return Result.ok(SubscriptionDto.model_validate(subscription))

    async def resume(self, user_id: uuid.UUID) -> Result[SubscriptionDto]:
        subscription = await self._get_subscription(user_id)
        now = datetime.now(timezone.utc)
        if (
            subscription is None
            or not subscription.cancel_at_period_end
            or subscription.current_period_end is None
            or subscription.current_period_end <= now
        ):
            return Result.fail("No pending cancellation to resume.", status_code=400)

        subscription.cancel_at_period_end = False
        subscription.canceled_at = None
        await self._db.commit()
        await self._db.refresh(subscription)
        return Result.ok(SubscriptionDto.model_validate(subscription))

    async def _get_subscription(self, user_id: uuid.UUID) -> Subscription | None:
        result = await self._db.execute(select(Subscription).where(Subscription.user_id == user_id))
        return result.scalar_one_or_none()

    async def _get_plan(self, code: str) -> SubscriptionPlan | None:
        result = await self._db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.code == code, SubscriptionPlan.is_active == True  # noqa: E712
            )
        )
        return result.scalar_one_or_none()


def get_subscription_service(db: AsyncSession = Depends(get_db)) -> SubscriptionService:
    return SubscriptionService(db)
