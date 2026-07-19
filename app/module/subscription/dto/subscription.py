from datetime import datetime

from pydantic import BaseModel

from app.common.enums.subscription import PlanCode


class PlanDto(BaseModel):
    code: PlanCode
    name: str
    amount: int
    compare_at_amount: int | None = None
    currency: str
    interval_days: int
    trial_days: int
    features: list[str]

    model_config = {"from_attributes": True}


class PlansResponseDto(BaseModel):
    paystack_public_key: str
    plans: list[PlanDto]


class VerifyCheckoutDto(BaseModel):
    reference: str
    plan_code: PlanCode


class SubscriptionDto(BaseModel):
    plan_code: PlanCode | None = None
    status: str
    amount: int | None = None
    currency: str | None = None
    trial_end: datetime | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    canceled_at: datetime | None = None

    model_config = {"from_attributes": True}
