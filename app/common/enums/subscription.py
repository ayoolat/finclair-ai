from enum import Enum


class PlanCode(str, Enum):
    GO_UNLIMITED_MONTHLY = "go_unlimited_monthly"
    GO_UNLIMITED_YEARLY = "go_unlimited_yearly"


class SubscriptionStatus(str, Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"
