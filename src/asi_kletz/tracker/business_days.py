"""Business-day arithmetic for the sprint planner: pure functions, no Tk, no storage.

The owner's rule (2026-10-28, ``docs/sprint-planner-plan.md``): a sprint spans 10 business days; Monday
to Friday count, weekends and holidays do not, so a sprint that contains a holiday ends one calendar day
later per holiday. Holidays come in as dates (any collection; a ``{date: name}`` mapping works through its
keys), whatever their status in the ``holiday`` table.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection

ONE_DAY = dt.timedelta(days=1)


def is_business_day(day: dt.date, holidays: Collection[dt.date] = ()) -> bool:
    """Monday to Friday and not a holiday."""
    return day.weekday() < 5 and day not in holidays


def next_business_day(day: dt.date, holidays: Collection[dt.date] = ()) -> dt.date:
    """The first business day strictly after ``day``."""
    day += ONE_DAY
    while not is_business_day(day, holidays):
        day += ONE_DAY
    return day


def add_business_days(start: dt.date, n: int, holidays: Collection[dt.date] = ()) -> dt.date:
    """The date ``n`` business days on from ``start``, counting business days only.

    ``n = 0`` is ``start`` itself when it is a business day, else the first business day after it; so a
    sprint that starts on a business day ends on ``add_business_days(start, 9)``, its tenth business day.
    """
    if n < 0:
        raise ValueError(f"n must be 0 or more, not {n}")
    day = start
    while not is_business_day(day, holidays):
        day += ONE_DAY
    for _ in range(n):
        day = next_business_day(day, holidays)
    return day


def business_days_between(start: dt.date, end: dt.date, holidays: Collection[dt.date] = ()) -> int:
    """The number of business days in ``[start, end]``, both ends included; 0 when ``end`` is before ``start``."""
    count = 0
    day = start
    while day <= end:
        if is_business_day(day, holidays):
            count += 1
        day += ONE_DAY
    return count


def holidays_within(start: dt.date, end: dt.date, holidays: Collection[dt.date]) -> list[dt.date]:
    """The holidays that fall in ``[start, end]``, sorted; weekend holidays included, they are still holidays."""
    return sorted(day for day in holidays if start <= day <= end)
