import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.common.enums.groups import GroupInviteStatus, GroupMemberStatus, InviteResponse, MessageRole, MessageType


class CreateGroupDto(BaseModel):
    name: str
    target_amount: Decimal
    end_date: date
    member_ids: list[uuid.UUID] = []

    @field_validator("target_amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Target amount must be greater than zero.")
        return v


class UpdateGroupDto(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[Decimal] = None
    end_date: Optional[date] = None


class RespondToInviteDto(BaseModel):
    response: InviteResponse


class UpdateMemberDto(BaseModel):
    target_amount: Decimal

    @field_validator("target_amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Target amount must be greater than zero.")
        return v


class AddMemberDto(BaseModel):
    user_id: uuid.UUID


class GroupMemberResponseDto(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    status: GroupMemberStatus
    invite_status: GroupInviteStatus
    target_amount: Optional[Decimal]
    contributed_amount: Decimal
    joined_at: datetime

    model_config = {"from_attributes": True}


class GroupResponseDto(BaseModel):
    id: uuid.UUID
    name: str
    target_amount: Decimal
    end_date: date
    owner_id: uuid.UUID
    created_at: datetime
    invite_status: GroupInviteStatus
    total_raised: Decimal
    balance: Decimal
    days_left: int
    member_count: int
    progress_percent: float
    shareable_link: str
    amount_paid: Decimal
    amount_left: Decimal
    amount_assigned: Decimal

    model_config = {"from_attributes": True}


class GroupDetailResponseDto(GroupResponseDto):
    members: list[GroupMemberResponseDto]


class RecordSavingsDto(BaseModel):
    amount: Decimal
    note: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v


class SavingsEntryResponseDto(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: Decimal
    cumulative_at_time: Optional[Decimal]
    note: Optional[str]
    file_url: Optional[str]
    recorded_at: datetime

    model_config = {"from_attributes": True}


class SendMessageDto(BaseModel):
    content: str


class MessageResponseDto(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    sender_id: Optional[uuid.UUID]
    sender_username: Optional[str]
    role: MessageRole
    message_type: MessageType
    content: Optional[str]
    file_url: Optional[str]
    extra_data: Optional[dict] = None
    sent_at: datetime

    model_config = {"from_attributes": True}
