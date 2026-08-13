import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.common.enums.friends import FriendshipStatus


class SendInviteDto(BaseModel):
    recipient_id: uuid.UUID


class FriendshipResponseDto(BaseModel):
    id: uuid.UUID
    requester_id: uuid.UUID
    recipient_id: uuid.UUID
    status: FriendshipStatus
    created_at: datetime
    friend_id: uuid.UUID
    friend_username: str
    friend_email: str
    friend_profile_icon: Optional[str] = None

    model_config = {"from_attributes": True}


class UserSearchResultDto(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    profile_icon: Optional[str] = None

    model_config = {"from_attributes": True}


class BlockedUserResponseDto(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    email: str
    profile_icon: Optional[str] = None
    blocked_at: datetime

    model_config = {"from_attributes": True}
