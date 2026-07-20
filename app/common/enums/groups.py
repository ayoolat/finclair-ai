from enum import Enum


class GroupMemberStatus(str, Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    LEFT = "left"
    REMOVED = "removed"


class RedistributionChoice(str, Enum):
    SELF = "self"
    SPLIT = "split"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    SYSTEM = "system"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"  # reserved for future AI
