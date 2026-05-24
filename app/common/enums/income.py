from enum import Enum


class IncomeSource(str, Enum):
    SALARY = "salary"
    FREELANCE = "freelance"
    BUSINESS = "business"
    INVESTMENT = "investment"


class IncomeReoccurrence(str, Enum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
