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
