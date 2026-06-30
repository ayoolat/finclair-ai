from typing import Optional

from pydantic import BaseModel, EmailStr


class NewsletterSubscribeDto(BaseModel):
    email: EmailStr
    name: Optional[str] = None


class WaitlistJoinDto(BaseModel):
    email: EmailStr
    name: Optional[str] = None
