"""Corte lógico de las 04:00 y línea de tiempo."""

from __future__ import annotations

from datetime import datetime

from app.domain.logical_date import (
    get_logical_date,
    iter_timeline_hours,
    logical_day_bounds,
    split_interval_by_logical_date,
)


def test_logical_date_before_and_after_cutoff() -> None:
    before = datetime(2026, 1, 10, 3, 30)
    after = datetime(2026, 1, 10, 4, 30)
    assert get_logical_date(before, cutoff_hour=4) == "2026-01-09"
    assert get_logical_date(after, cutoff_hour=4) == "2026-01-10"

    # Exactamente a las 04:00 ya es el día nuevo.
    assert get_logical_date(datetime(2026, 1, 10, 4, 0), 4) == "2026-01-10"


def test_timeline_runs_from_0400_to_0300() -> None:
    hours = list(iter_timeline_hours(4))
    assert len(hours) == 24
    assert hours[0] == (4, 4, "04:00")
    assert hours[-1] == (27, 3, "03:00")
    assert [hour[2] for hour in hours[:3]] == ["04:00", "05:00", "06:00"]


def test_logical_day_bounds() -> None:
    start, end = logical_day_bounds("2026-01-10", 4)
    assert start == datetime(2026, 1, 10, 4, 0)
    assert end == datetime(2026, 1, 11, 4, 0)


def test_interval_split_across_cutoff() -> None:
    splits = split_interval_by_logical_date(
        datetime(2026, 1, 10, 2, 0),
        datetime(2026, 1, 10, 6, 0),
        cutoff_hour=4,
    )
    assert splits["2026-01-09"] == 120.0
    assert splits["2026-01-10"] == 120.0
