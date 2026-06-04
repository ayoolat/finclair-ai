import uuid
from typing import Optional

from pydantic import BaseModel


class CategoryDto(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]

    model_config = {"from_attributes": True}
