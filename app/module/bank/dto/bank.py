import uuid
from typing import Optional

from pydantic import BaseModel


class LinkBankDto(BaseModel):
    """Payload after user completes Mono Connect on mobile."""
    code: str


class BankResponseDto(BaseModel):
    id: uuid.UUID
    name: str
    account_number: str
    mono_account_id: Optional[str]

    model_config = {"from_attributes": True}


class MonoWebhookDto(BaseModel):
    event: str
    data: dict
