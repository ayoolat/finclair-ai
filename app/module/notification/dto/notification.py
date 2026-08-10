import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.common.enums.notification import DevicePlatform, NotificationType


class RegisterDeviceTokenDto(BaseModel):
    token: str
    platform: DevicePlatform


class DeviceTokenResponseDto(BaseModel):
    id: uuid.UUID
    platform: DevicePlatform
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationResponseDto(BaseModel):
    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    data: Optional[dict] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountDto(BaseModel):
    count: int
