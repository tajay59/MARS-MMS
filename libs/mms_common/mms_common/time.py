"""Injectable clock. Time-dependent code reads this, never `datetime.now()` (TRD §17).

All times are UTC (CLAUDE.md rule 8). Station time zones are for display only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time as an aware UTC datetime."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ManualClock:
    """A clock tests move by hand (leader-lease expiry, auto-close, reminders)."""

    def __init__(self, start: datetime | None = None) -> None:
        start = start or datetime(2026, 1, 1, tzinfo=UTC)
        if start.tzinfo is None:
            raise ValueError("ManualClock needs an aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> datetime:
        self._now += timedelta(**delta)
        return self._now

    def set(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("ManualClock needs an aware datetime")
        self._now = value.astimezone(UTC)


def to_iso(value: datetime) -> str:
    """UTC ISO 8601 with a `Z` suffix, as the API and events carry it."""
    if value.tzinfo is None:
        raise ValueError("naive datetime: times are stored in UTC and must be aware")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
