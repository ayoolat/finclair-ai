from enum import Enum


class EmailStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
