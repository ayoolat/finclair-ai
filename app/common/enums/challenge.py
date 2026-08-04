from enum import Enum


class ChallengeType(str, Enum):
    FRIDAY_SAVINGS = "friday_savings"
    NO_SPEND = "no_spend"
    BUDGET_CATEGORY = "budget_category"


class ChallengeStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    # A budget_category challenge whose period ended over its spend cap —
    # distinct from CANCELLED since the user didn't end it themselves.
    FAILED = "failed"


class EntryVerificationLevel(str, Enum):
    """
    Whether a challenge entry has supporting evidence — a bank receipt or bank
    alert screenshot — or is just a self-reported amount. Mirrors the same
    concept used for expenses (see ExpenseVerificationLevel) but kept separate
    since this feature is deliberately isolated from the expense module.
    """
    SELF_REPORTED = "self_reported"
    EVIDENCE_BACKED = "evidence_backed"
