from enum import Enum


class DevicePlatform(str, Enum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class NotificationType(str, Enum):
    BUDGET_NEAR_LIMIT = "budget_near_limit"
    FRIEND_INVITE = "friend_invite"
    GROUP_INVITE = "group_invite"
    GROUP_ACTIVITY = "group_activity"
    BANK_SYNC_COMPLETED = "bank_sync_completed"
    SUBSCRIPTION_ACTIVATED = "subscription_activated"
    # Reused for the 9 PM (or personalized) evening spending check — a reminder to
    # log any outstanding expenses before the day ends, not a closed-out summary.
    DAILY_EXPENSE_SUMMARY = "daily_expense_summary"
    MIDDAY_SPENDING_CHECK = "midday_spending_check"
    DAILY_AI_TIP = "daily_ai_tip"
    LARGE_TRANSACTION = "large_transaction"
    UNUSUAL_SPENDING = "unusual_spending"
    BUDGET_LIMIT_REACHED = "budget_limit_reached"
