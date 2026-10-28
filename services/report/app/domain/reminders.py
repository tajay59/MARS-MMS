"""Reminders for a report that is not finalized (PRD RPT-7, Appendix B; W17-11). No I/O.

A draft is reminded once at 2 working days and once at 5, counted from when the visit ended (from
the reopen, for a corrected version). Working days are Monday to Friday in the zone of the visit's
first station; there is no holiday calendar. The reminder keeps the time of day: a visit that ended
on Friday at 16:40 is two working days old on Tuesday at 16:40.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

LEVELS = (2, 5)  # working days; the event schema allows these two


def zone_of(report: Mapping[str, Any]) -> ZoneInfo:
    """The first station's zone; UTC when it has none or the name is unknown."""
    facts = report["content"]["facts"]
    name = next((s.get("time_zone") for s in (facts or {}).get("stations", [])
                 if s.get("time_zone")), None)
    try:
        return ZoneInfo(name or "UTC")
    except (KeyError, ValueError):
        return ZoneInfo("UTC")


def add_working_days(start: datetime, days: int, zone: ZoneInfo) -> datetime:
    """`start` plus `days` Monday-to-Friday days, at the same wall-clock time in `zone`."""
    local = (start if start.tzinfo else start.replace(tzinfo=UTC)).astimezone(zone)
    day = local.replace(tzinfo=None)
    counted = 0
    while counted < days:
        day += timedelta(days=1)
        if day.weekday() < 5:
            counted += 1
    return day.replace(tzinfo=zone).astimezone(UTC)


def anchor(report: Mapping[str, Any]) -> datetime:
    """Where the counting starts: the visit's end, or the reopen for a corrected version."""
    start: datetime = report.get("remind_from") or report["ended_at"]
    return start if start.tzinfo else start.replace(tzinfo=UTC)


def due_levels(report: Mapping[str, Any], now: datetime) -> list[int]:
    """The levels whose time has come and that were not sent yet for this version."""
    zone, start = zone_of(report), anchor(report)
    sent = set(report.get("reminders_sent") or [])
    return [
        level for level in LEVELS
        if level not in sent and now >= add_working_days(start, level, zone)
    ]


def recipients(report: Mapping[str, Any], signed_ids: Collection[str]) -> list[str]:
    """The attending people who have not signed; when everyone has, the lead, who finalizes."""
    waiting = [i for i in report["staff_ids"] if i not in signed_ids]
    return waiting or [report["lead_staff_id"]]


def reminder_levels(due: Sequence[int]) -> tuple[int, list[int]]:
    """What to say and what to mark as done: only the latest level is sent, so a draft found
    after a long gap gets one reminder, not two; every level due is marked."""
    return max(due), list(due)
