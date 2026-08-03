from datetime import date
from decimal import Decimal


def iso_week_key(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def week_monday(key: str) -> date:
    year_str, week_str = key.split("-W")
    return date.fromisocalendar(int(year_str), int(week_str), 1)


def weeks_between(prev_key: str, curr_key: str) -> int:
    return (week_monday(curr_key) - week_monday(prev_key)).days // 7


_RECEIPT_AMOUNT_TOLERANCE_PCT = Decimal("0.01")  # 1% allowed drift (rounding, OCR noise)
_RECEIPT_AMOUNT_TOLERANCE_MIN = Decimal("0.01")  # minimum absolute tolerance


def receipt_amount_matches(claimed: Decimal, detected: Decimal) -> bool:
    tolerance = max(_RECEIPT_AMOUNT_TOLERANCE_MIN, claimed * _RECEIPT_AMOUNT_TOLERANCE_PCT)
    return abs(claimed - detected) <= tolerance
