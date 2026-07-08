from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.module.expense.dto.expense import ExpenseSummaryDto


class ClaraChatRequestDto(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ClaraMessageDto(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    data: Optional[dict[str, Any]] = None
    created_at: datetime


class ClaraChatResponseDto(BaseModel):
    reply: str
    data: Optional[ExpenseSummaryDto] = None
