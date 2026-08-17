"""
The app's canonical local timezone (West Africa Time, UTC+1, no DST) — used
whenever a "this day"/"this month" boundary needs to be compared against
`Expense.expense_date` (stored as TIMESTAMP WITH TIME ZONE). The mobile app
already converts its local calendar days to UTC this way when it calls the
API; backend-side boundary calculations must match it exactly, or the same
"August" ends up meaning two different UTC ranges depending on which screen
computed it.
"""

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("Africa/Lagos")


def local_day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=APP_TZ)


def local_day_end(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=APP_TZ)


def local_month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    last_day = calendar.monthrange(year, month)[1]
    return local_day_start(date(year, month, 1)), local_day_end(date(year, month, last_day))
