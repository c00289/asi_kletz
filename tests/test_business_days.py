"""The business-day arithmetic of the weekly tracker (the burndown's working days, the holidays a sprint names):
pure functions over dates and a set of holidays. Sprint dates are not business days since 0.18.0: the law of
2026-10-29 makes a sprint 14 calendar days, Tuesday to Monday (``test_sprint.py``)."""

from __future__ import annotations

import datetime as dt

import pytest

from asi_kletz.tracker.business_days import (
    add_business_days,
    business_days_between,
    holidays_within,
    is_business_day,
    next_business_day,
)

MON, TUE, WED, THU, FRI, SAT, SUN = (dt.date(2026, 11, 2) + dt.timedelta(days=i) for i in range(7))


def test_a_plain_week_counts_monday_to_friday():
    assert all(is_business_day(d) for d in (MON, TUE, WED, THU, FRI))
    assert add_business_days(MON, 4) == FRI and add_business_days(MON, 5) == dt.date(2026, 11, 9)
    assert add_business_days(MON, 9) == dt.date(2026, 11, 13)  # the tenth working day
    assert business_days_between(MON, FRI) == 5 and business_days_between(MON, dt.date(2026, 11, 13)) == 10
    assert add_business_days(MON, 0) == MON and business_days_between(FRI, MON) == 0
    with pytest.raises(ValueError):
        add_business_days(MON, -1)


def test_a_weekend_is_skipped():
    assert not is_business_day(SAT) and not is_business_day(SUN)
    assert next_business_day(FRI) == dt.date(2026, 11, 9) and next_business_day(SAT) == dt.date(2026, 11, 9)
    assert add_business_days(FRI, 1) == dt.date(2026, 11, 9)
    assert add_business_days(SAT, 0) == dt.date(2026, 11, 9)  # a start on a weekend moves to the Monday
    assert business_days_between(SAT, SUN) == 0 and business_days_between(FRI, dt.date(2026, 11, 9)) == 2


def test_one_holiday_is_one_working_day_fewer():
    veterans = {dt.date(2026, 11, 11)}  # a Wednesday
    start = dt.date(2026, 11, 9)
    assert add_business_days(start, 9) == dt.date(2026, 11, 20)
    assert add_business_days(start, 9, veterans) == dt.date(2026, 11, 23)
    assert not is_business_day(dt.date(2026, 11, 11), veterans)
    assert business_days_between(start, dt.date(2026, 11, 23), veterans) == 10
    assert business_days_between(start, dt.date(2026, 11, 20), veterans) == 9
    assert holidays_within(start, dt.date(2026, 11, 23), veterans) == [dt.date(2026, 11, 11)]
    assert holidays_within(dt.date(2026, 11, 12), dt.date(2026, 11, 30), veterans) == []


def test_a_holiday_on_a_monday():
    mlk = {dt.date(2027, 1, 18): "Martin Luther King Jr. Day"}  # a mapping works through its keys
    friday = dt.date(2027, 1, 15)
    assert next_business_day(friday, mlk) == dt.date(2027, 1, 19)
    assert add_business_days(dt.date(2027, 1, 18), 0, mlk) == dt.date(2027, 1, 19)
    assert add_business_days(friday, 10, mlk) == dt.date(2027, 2, 1)
    assert business_days_between(dt.date(2027, 1, 18), dt.date(2027, 1, 22), mlk) == 4


def test_the_christmas_and_new_year_span():
    holidays = {dt.date(2026, 12, 24), dt.date(2026, 12, 25), dt.date(2027, 1, 1)}
    start = dt.date(2026, 12, 21)
    end = add_business_days(start, 9, holidays)
    assert end == dt.date(2027, 1, 6) and (end - start).days + 1 == 17  # ten working days over 17 calendar days
    assert business_days_between(start, end, holidays) == 10
    assert holidays_within(start, end, holidays) == sorted(holidays)
    # the picture's Sprint 35 (12/22 to 1/4) runs straight through them: 7 working days of its 14, the dates fixed
    assert business_days_between(dt.date(2026, 12, 22), dt.date(2027, 1, 4), holidays) == 7
    assert next_business_day(dt.date(2026, 12, 23), holidays) == dt.date(2026, 12, 28)
    assert next_business_day(dt.date(2026, 12, 31), holidays) == dt.date(2027, 1, 4)
