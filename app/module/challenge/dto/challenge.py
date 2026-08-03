import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, computed_field, field_validator

from app.common.dto.pagination import PageQueryDto
from app.common.enums.challenge import ChallengeStatus, ChallengeType, EntryVerificationLevel


class CreateChallengeDto(BaseModel):
    name: str = "Friday Savings Challenge"
    weekly_target: Optional[Decimal] = None
    overall_target: Optional[Decimal] = None
    end_date: Optional[date] = None

    @field_validator("weekly_target", "overall_target")
    @classmethod
    def amount_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


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
    start_date: date
    end_date: Optional[date]
    status: ChallengeStatus
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def progress_percent(self) -> Optional[float]:
        if not self.overall_target or self.overall_target <= 0:
            return None
        return round(min(100.0, float(self.total_saved / self.overall_target) * 100), 1)

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
