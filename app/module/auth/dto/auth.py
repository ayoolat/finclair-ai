import uuid
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, EmailStr, field_validator

# Strips whitespace and lowercases before EmailStr validation runs.
# Applied at the DTO boundary so emails are always stored and queried consistently.
NormalizedEmail = Annotated[EmailStr, BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v)]


class RegisterDto(BaseModel):
    email: NormalizedEmail
    username: str
    passcode: str
    default_currency: str = "USD"

    @field_validator("passcode")
    @classmethod
    def passcode_must_be_six_digits(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Passcode must be exactly 6 digits.")
        return v

    @field_validator("username")
    @classmethod
    def username_no_spaces(cls, v: str) -> str:
        if " " in v.strip():
            raise ValueError("Username must not contain spaces.")
        return v.strip().lower()


class LoginDto(BaseModel):
    email: NormalizedEmail
    passcode: str


class VerifyEmailDto(BaseModel):
    email: NormalizedEmail
    code: str


class ResendOtpDto(BaseModel):
    email: NormalizedEmail


class ForgotPasscodeDto(BaseModel):
    email: NormalizedEmail


class ResetPasscodeDto(BaseModel):
    email: NormalizedEmail
    code: str
    new_passcode: str

    @field_validator("new_passcode")
    @classmethod
    def passcode_must_be_six_digits(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Passcode must be exactly 6 digits.")
        return v


class OnboardingGoalsDto(BaseModel):
    goals: list[uuid.UUID]


class RefreshTokenDto(BaseModel):
    refresh_token: str


class TokenPairResponseDto(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
