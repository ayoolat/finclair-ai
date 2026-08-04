import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, computed_field, field_validator, model_validator

from app.common.dto.pagination import PageQueryDto
from app.common.enums.challenge import ChallengeStatus, ChallengeType, EntryVerificationLevel


class CreateChallengeDto(BaseModel):
    type: ChallengeType = ChallengeType.FRIDAY_SAVINGS
    name: Optional[str] = None
    weekly_target: Optional[Decimal] = None
    overall_target: Optional[Decimal] = None
    target_category_id: Optional[uuid.UUID] = None
    end_date: Optional[date] = None

    @field_validator("weekly_target", "overall_target")
    @classmethod
    def amount_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v

    @model_validator(mode="after")
    def budget_category_requires_cap_and_period(self) -> "CreateChallengeDto":
        if self.type == ChallengeType.BUDGET_CATEGORY:
            missing = [
                field
                for field, value in (
                    ("target_category_id", self.target_category_id),
                    ("overall_target", self.overall_target),
                    ("end_date", self.end_date),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    f"A budget category challenge requires: {', '.join(missing)}."
                )
        return self


class UpdateChallengeDto(BaseModel):
    name: Optional[str] = None
    weekly_target: Optional[Decimal] = None
    overall_target: Optional[Decimal] = None
    end_date: Optional[date] = None

    @field_validator("weekly_target", "overall_target")
    @classmethod
    def amount_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


class ChallengeResponseDto(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: ChallengeType
    name: str
    weekly_target: Optional[Decimal]
    overall_target: Optional[Decimal]
    total_saved: Decimal
    current_streak: int
    longest_streak: int
    last_entry_week: Optional[str]
    target_category_id: Optional[uuid.UUID]
    current_period_spent: Optional[Decimal]
    start_date: date
    end_date: Optional[date]
    status: ChallengeStatus
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def progress_percent(self) -> Optional[float]:
        # budget_category tracks progress toward a spend cap via
        # current_period_spent; every other type tracks total_saved.
        amount = self.current_period_spent if self.type == ChallengeType.BUDGET_CATEGORY else self.total_saved
        if not self.overall_target or self.overall_target <= 0 or amount is None:
            return None
        return round(min(100.0, float(amount / self.overall_target) * 100), 1)

    model_config = {"from_attributes": True}


class RecordEntryDto(BaseModel):
    amount: Optional[Decimal] = None
    note: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


class ChallengeEntryResponseDto(BaseModel):
    id: uuid.UUID
    amount: Optional[Decimal]
    verification_level: EntryVerificationLevel
    note: Optional[str]
    file_url: Optional[str]
    recorded_at: datetime

    model_config = {"from_attributes": True}


class ChallengeFilterDto(PageQueryDto):
    status: Optional[ChallengeStatus] = None


class BadgeResponseDto(BaseModel):
    key: str
    name: str
    description: str
    icon_name: Optional[str]
    category: Optional[str]

    model_config = {"from_attributes": True}


class UserBadgeResponseDto(BaseModel):
    badge: BadgeResponseDto
    earned_period: Optional[str]
    earned_at: datetime

    model_config = {"from_attributes": True}
