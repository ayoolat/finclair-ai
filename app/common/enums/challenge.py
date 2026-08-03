from enum import Enum


class ChallengeType(str, Enum):
    # Only one kind today — save something every Friday. Kept as an enum (not a
    # hardcoded string) so a future challenge type doesn't require a schema change.
    FRIDAY_SAVINGS = "friday_savings"


class ChallengeStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EntryVerificationLevel(str, Enum):
    """
    Whether a challenge entry has supporting evidence — a bank receipt or bank
    alert screenshot — or is just a self-reported amount. Mirrors the same
    concept used for expenses (see ExpenseVerificationLevel) but kept separate
    since this feature is deliberately isolated from the expense module.
    """
    SELF_REPORTED = "self_reported"
    EVIDENCE_BACKED = "evidence_backed"
