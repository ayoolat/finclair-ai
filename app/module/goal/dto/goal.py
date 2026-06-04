import uuid

from pydantic import BaseModel


class FinancialGoalDto(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str
    icon_name: str

    model_config = {"from_attributes": True}
