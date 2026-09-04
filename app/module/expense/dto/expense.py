import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, computed_field, field_validator

from app.common.dto.pagination import PageQueryDto
from app.common.response import PaginatedResponse
from app.common.enums.expense import (
    LARGE_EXPENSE_EVIDENCE_THRESHOLD,
    ExpenseStatus,
    ExpenseVerificationLevel,
    verification_level_for_source,
)
from app.core.config import settings


# ── Item DTOs ─────────────────────────────────────────────────────────────────

class ExpenseItemCreateDto(BaseModel):
    name: str
    quantity: int = 1
    unit_price: Decimal
    category_id: Optional[uuid.UUID] = None

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Quantity must be greater than zero.")
        return v

    @field_validator("unit_price")
    @classmethod
    def price_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Unit price must be non-negative.")
        return v


class UpdateExpenseItemDto(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    category_id: Optional[uuid.UUID] = None

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("Quantity must be greater than zero.")
        return v

    @field_validator("unit_price")
    @classmethod
    def price_non_negative(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("Unit price must be non-negative.")
        return v


class ExpenseItemResponseDto(BaseModel):
    id: uuid.UUID
    name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    category_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


# ── Manual expense ────────────────────────────────────────────────────────────

class CreateManualExpenseDto(BaseModel):
    amount: Decimal
    description: Optional[str] = None
    category_ids: list[uuid.UUID] = []
    expense_date: datetime
    currency: Optional[str] = None
    items: list[ExpenseItemCreateDto] = []

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


# ── Update expense ────────────────────────────────────────────────────────────

class UpdateExpenseDto(BaseModel):
    amount: Optional[Decimal] = None
    description: Optional[str] = None
    category_ids: Optional[list[uuid.UUID]] = None
    expense_date: Optional[datetime] = None
    currency: Optional[str] = None
    status: Optional[ExpenseStatus] = None
    items: Optional[list[UpdateExpenseItemDto]] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


# ── Response ──────────────────────────────────────────────────────────────────

class CategorySummaryDto(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class _FileDto(BaseModel):
    folder: str
    file_name: str

    model_config = {"from_attributes": True}


class ExpenseResponseDto(BaseModel):
    id: uuid.UUID
    amount: Decimal
    type: Optional[str]
    direction: Optional[str]
    status: Optional[str]
    currency: Optional[str]
    description: Optional[str]
    expense_date: datetime
    source: Optional[str]
    file: Optional[_FileDto] = None
    categories: list[CategorySummaryDto]
    items: list[ExpenseItemResponseDto]
    clara_insight: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def receipt_url(self) -> Optional[str]:
        if self.file is None:
            return None
        return f"{settings.spaces_cdn_url}/{self.file.folder}/{self.file.file_name}"

    @computed_field  # type: ignore[misc]
    @property
    def verification_level(self) -> ExpenseVerificationLevel:
        return verification_level_for_source(self.source)

    @computed_field  # type: ignore[misc]
    @property
    def evidence_suggested(self) -> bool:
        """True for large self-reported expenses — a nudge to attach proof, not a requirement."""
        return (
            self.verification_level == ExpenseVerificationLevel.SELF_REPORTED
            and self.amount >= LARGE_EXPENSE_EVIDENCE_THRESHOLD
        )

    model_config = {"from_attributes": True}


# ── Summary / analytics ───────────────────────────────────────────────────────

class CategoryExpenseSummaryDto(BaseModel):
    name: str
    amount: float
    transaction_count: int
    pct_of_total: float


class ExpenseListResponseDto(PaginatedResponse[ExpenseResponseDto]):
    total_expenses: Decimal
    category_breakdown: list[CategoryExpenseSummaryDto]


class MonthlyTrendPointDto(BaseModel):
    month: str   # "Jan", "Feb", …
    year: int
    total: Optional[float]  # None for future months with no data


class IncomeExpenseTrendPointDto(BaseModel):
    month: str
    year: int
    income: float
    expense: float


class ExpenseSummaryDto(BaseModel):
    month_label: str               # "April 2024"
    total_expense: float
    mom_change_pct: Optional[float]   # None when no prior month data
    mom_direction: Optional[str]      # "less" | "more" | "same"
    categories: list[CategoryExpenseSummaryDto]
    monthly_trend: list[MonthlyTrendPointDto]
    income_expense_trend: list[IncomeExpenseTrendPointDto]
    monthly_income: float


class PeriodSpendingDto(BaseModel):
    """Spending over an arbitrary date range (a week, a handful of days, a
    custom range) — the lighter counterpart to ExpenseSummaryDto, which is
    locked to whole calendar months."""

    period_label: str                 # "this week", "the last 7 days", "Aug 1 to Aug 15, 2026"
    start_date: date                  # inclusive, in the app's local timezone
    end_date: date                    # inclusive
    total_expense: float
    transaction_count: int
    categories: list[CategoryExpenseSummaryDto]
    prev_period_total: Optional[float]   # same-length window immediately before; None if no prior spend
    change_pct: Optional[float]          # vs. prev_period_total; None when prev is 0
    change_direction: Optional[str]      # "less" | "more" | "same"


class ExpenseSummaryQueryDto(BaseModel):
    year: Optional[int] = None
    month: Optional[int] = None  # 1-12

    @field_validator("month")
    @classmethod
    def month_in_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not 1 <= v <= 12:
            raise ValueError("Month must be between 1 and 12.")
        return v


# ── Streak ────────────────────────────────────────────────────────────────────

class ExpenseStreakDayDto(BaseModel):
    date: date
    day_label: str   # "Mo", "Tu", ...
    logged: bool
    is_today: bool


class ExpenseStreakResponseDto(BaseModel):
    current_streak: int
    longest_streak: int
    last_logged_date: Optional[date]
    logged_today: bool
    days: list[ExpenseStreakDayDto]


class ExpenseFilterDto(PageQueryDto):
    search: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    source: Optional[Literal["manual", "receipt", "bank_sync"]] = None
    status: Optional[ExpenseStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    order_by: Literal["expense_date", "amount", "created_at"] = "expense_date"
    order_dir: Literal["asc", "desc"] = "desc"
