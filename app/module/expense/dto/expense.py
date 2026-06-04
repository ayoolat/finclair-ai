import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, computed_field, field_validator

from app.common.dto.pagination import PageQueryDto
from app.common.enums.expense import ExpenseStatus
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

    @computed_field  # type: ignore[misc]
    @property
    def receipt_url(self) -> Optional[str]:
        if self.file is None:
            return None
        return f"{settings.spaces_cdn_url}/{self.file.folder}/{self.file.file_name}"

    model_config = {"from_attributes": True}


class ExpenseFilterDto(PageQueryDto):
    search: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    source: Optional[Literal["manual", "receipt", "bank_sync"]] = None
    status: Optional[ExpenseStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    order_by: Literal["expense_date", "amount", "created_at"] = "expense_date"
    order_dir: Literal["asc", "desc"] = "desc"
