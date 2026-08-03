import uuid
from datetime import datetime

from pydantic import BaseModel

from app.common.enums.notification import DevicePlatform


class RegisterDeviceTokenDto(BaseModel):
    token: str
    platform: DevicePlatform


class DeviceTokenResponseDto(BaseModel):
    id: uuid.UUID
    platform: DevicePlatform
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
