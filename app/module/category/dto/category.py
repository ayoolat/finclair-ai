import uuid
from typing import Optional

from pydantic import BaseModel, computed_field


class CategoryDto(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_default(self) -> bool:
        return self.user_id is None

    model_config = {"from_attributes": True}


class CreateCategoryDto(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
