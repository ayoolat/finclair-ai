from datetime import date
from pydantic import BaseModel


class HomeInsightDto(BaseModel):
    insight: str
    start_date: date
    end_date: date
    total_income: float
    total_expenses: float
    available_balance: float
