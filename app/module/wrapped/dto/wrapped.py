from datetime import date
from typing import Optional

from pydantic import BaseModel


class WrappedCoverDto(BaseModel):
    year: int
    username: str
    headline: str


class IncomeExpenseDto(BaseModel):
    total_income: float
    total_expenses: float
    net_balance: float
    headline: str


class CategoryShareDto(BaseModel):
    name: str
    icon: Optional[str] = None
    amount: float
    percentage: float


class SpendingBreakdownDto(BaseModel):
    total_expenses: float
    categories: list[CategoryShareDto]
    headline: str


class TopCategoryDto(BaseModel):
    name: str
    icon: Optional[str] = None
    amount: float
    percentage: float
    headline: str


class MonthlySavingsDto(BaseModel):
    month: int
    income: float
    expenses: float
    net_saved: float


class SavingsDto(BaseModel):
    savings_rate: float
    total_saved: float
    headline: str
    monthly_trend: list[MonthlySavingsDto]


class MoneyPersonalityDto(BaseModel):
    key: str
    name: str
    description: str


class TipDto(BaseModel):
    title: str
    body: str


class BadgeDto(BaseModel):
    key: str
    name: str
    headline: str
    description: str
    months_on_track: int
    months_tracked: int


class SharePassportDto(BaseModel):
    username: str
    year: int
    total_income: float
    total_expenses: float
    total_saved: float
    top_category: Optional[str] = None
    personality_name: str
    badge_name: str


class WrappedDto(BaseModel):
    year: int
    start_date: date
    end_date: date
    symbol: str
    cover: WrappedCoverDto
    income_vs_expense: IncomeExpenseDto
    spending_breakdown: SpendingBreakdownDto
    top_category: Optional[TopCategoryDto] = None
    savings: SavingsDto
    personality: MoneyPersonalityDto
    tip: TipDto
    badge: BadgeDto
    share_passport: SharePassportDto
