import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


# ── Request DTOs ──────────────────────────────────────────────────────────────

class CreateBudgetDto(BaseModel):
    amount_allocated: Decimal

    @field_validator("amount_allocated")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


class UpdateBudgetDto(BaseModel):
    amount_allocated: Optional[Decimal] = None

    @field_validator("amount_allocated")
    @classmethod
    def amount_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


class UpsertAllocationDto(BaseModel):
    category_id: uuid.UUID
    amount_allocated: Decimal

    @field_validator("amount_allocated")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


# ── Response DTOs ─────────────────────────────────────────────────────────────

class AllocationResponseDto(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    category_icon: Optional[str]
    amount_allocated: float
    spent: float
    remaining: float
    pct_used: float


class BudgetResponseDto(BaseModel):
    id: uuid.UUID
    amount_allocated: float
    spent: float
    remaining: float
    pct_used: float
    start_date: date
    end_date: date
    allocations: list[AllocationResponseDto]
    clara_insight: str = ""
