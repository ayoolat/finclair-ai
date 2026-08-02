import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, computed_field


class CreateUserDto(BaseModel):
    email: EmailStr
    username: str
    passcode: str
    default_currency: str = "USD"
    profile_icon: str | None = None


class UpdateUserDto(BaseModel):
    username: str | None = None
    preferred_name: str | None = None
    is_active: bool | None = None
    default_currency: str | None = None
    profile_icon: str | None = None


class UserResponseDto(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    preferred_name: str | None = None
    is_active: bool
    is_email_verified: bool
    default_currency: str
    profile_icon: str | None = None
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def display_name(self) -> str:
        return self.preferred_name or self.username

    model_config = {"from_attributes": True}
