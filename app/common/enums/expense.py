from enum import Enum


class ExpenseType(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class ExpenseDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ExpenseStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
