import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.common.enums.income import IncomeReoccurrence


class CreateIncomeDto(BaseModel):
    amount: Decimal
    source_id: uuid.UUID
    reoccurrence: IncomeReoccurrence
    note: Optional[str] = None
    start_date: date
    bank_id: Optional[uuid.UUID] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


class UpdateIncomeDto(BaseModel):
    amount: Optional[Decimal] = None
    source_id: Optional[uuid.UUID] = None
    reoccurrence: Optional[IncomeReoccurrence] = None
    note: Optional[str] = None
    start_date: Optional[date] = None


class IncomeResponseDto(BaseModel):
    id: uuid.UUID
    amount: Decimal
    source_id: uuid.UUID
    source_name: str
    reoccurrence: str
    note: Optional[str]
    start_date: date
    bank_id: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}


class CreateCustomSourceDto(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Source name cannot be empty.")
        if len(v) > 50:
            raise ValueError("Source name must be 50 characters or fewer.")
        return v


class IncomeSourceDto(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
