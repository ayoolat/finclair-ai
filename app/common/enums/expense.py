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


class ExpenseVerificationLevel(str, Enum):
    """
    Whether an expense has supporting evidence. Derived from `source`, not stored:
    receipt (OCR scan) and bank_sync (matched bank transaction) are evidence-backed;
    manual entry is self-reported.
    """
    VERIFIED = "verified"
    SELF_REPORTED = "self_reported"


_VERIFIED_SOURCES = {"receipt", "bank_sync"}

# Self-reported expenses at or above this amount get `evidence_suggested=True` on
# the response — a nudge for the client to ask "want to attach proof?", not a
# requirement. Below it, quick cash logging stays frictionless.
LARGE_EXPENSE_EVIDENCE_THRESHOLD = 100_000


def verification_level_for_source(source: str | None) -> ExpenseVerificationLevel:
    if source in _VERIFIED_SOURCES:
        return ExpenseVerificationLevel.VERIFIED
    return ExpenseVerificationLevel.SELF_REPORTED
