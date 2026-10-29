"""Which backups to keep: 14 daily, 12 monthly, and always the newest (TRD §16.4; W20-6)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backup"))

from retention import parse, to_delete


def name(day: date, time: str = "020000") -> str:
    return f"mms-{day:%Y%m%d}T{time}Z.archive.age"


def nightly(first: date, count: int) -> list[str]:
    return [name(first + timedelta(days=n)) for n in range(count)]


def test_a_file_name_gives_its_day_and_month():
    assert parse("mms-20261029T020000Z.archive.age")[:2] == ("2026-10-29", "2026-10")
    assert parse("mms-20261029.archive.age") is None
    assert parse("notes.txt") is None


def test_nothing_is_deleted_while_there_are_fewer_than_the_limits():
    assert to_delete(nightly(date(2026, 10, 1), 14)) == []
    assert to_delete([]) == []


def test_the_fifteenth_night_drops_the_oldest_unless_it_starts_a_month():
    names = nightly(date(2026, 10, 2), 15)  # Oct 2 to Oct 16
    # Oct 2 is outside the newest 14 days but it is the first backup of October: kept
    assert to_delete(names) == []
    # A run that has several in the same month: only the first of that month survives the 14 days
    names = nightly(date(2026, 10, 1), 20)
    assert to_delete(names) == [name(date(2026, 10, n)) for n in range(2, 7)]


def test_a_year_of_nights_keeps_fourteen_days_and_twelve_months():
    names = nightly(date(2025, 9, 1), 400)  # to 2026-10-05
    gone = set(to_delete(names))
    kept = [n for n in names if n not in gone]
    days = [n for n in kept if n >= name(date(2026, 9, 22))]
    firsts = [n for n in kept if n < name(date(2026, 9, 22))]
    assert len(days) == 14  # Sep 22 to Oct 5
    # the first night of each month back to Nov 2025 (Oct 2026's first is among the 14 days)
    assert firsts == [name(date(2025 + (m // 12), m % 12 + 1, 1)) for m in range(10, 21)]


def test_the_latest_of_a_day_wins_the_daily_slot_and_the_newest_is_never_deleted():
    morning, evening = name(date(2026, 10, 29), "020000"), name(date(2026, 10, 29), "190000")
    old = nightly(date(2026, 10, 1), 28)  # Oct 1 is the month's first, so the morning is not
    gone = to_delete([*old, morning, evening])
    assert morning in gone and evening not in gone
    assert to_delete([evening]) == []


def test_names_it_does_not_know_are_never_listed():
    stray = ["README", "mms-latest.archive.age", "mms-20261029T020000Z.archive.json"]
    assert to_delete([*stray, *nightly(date(2026, 8, 1), 60)]) and not set(stray) & set(
        to_delete([*stray, *nightly(date(2026, 8, 1), 60)])
    )
