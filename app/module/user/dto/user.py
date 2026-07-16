import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class CreateUserDto(BaseModel):
    email: EmailStr
    username: str
    passcode: str
    default_currency: str = "USD"
    profile_icon: str | None = None


class UpdateUserDto(BaseModel):
    username: str | None = None
    is_active: bool | None = None
    default_currency: str | None = None
    profile_icon: str | None = None


class UserResponseDto(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    is_active: bool
    is_email_verified: bool
    default_currency: str
    profile_icon: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
