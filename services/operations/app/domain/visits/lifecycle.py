"""Starting, arriving, departing, ending, cancelling and restoring a visit (PRD VIS-2, VIS-4,
VIS-9; TRD §3.2.1; W10-8, W10-9). No I/O.

These are written for sync as well as for the routes: each takes the person, the visit as it is
and an `at` time, and returns what changes or raises the conflict `/sync` will report in Phase 5
(`not_owner`, `visit_cancelled`, `already_ended`, ...). The same move by the same person made
twice (a lost response, then a retry) changes nothing and is not an error: the result is empty.
Ending here is the lifecycle only; the VIS-6 media check arrives with media on visits (W12).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from mms_common.errors import Conflict, Forbidden, NotFound, ValidationFailed

from app.domain.visits.schedule import MAX_NOTES, can_attend, clean_notes
from app.domain.visits.state import VAction, VStatus, move

FUTURE_SKEW = timedelta(minutes=5)  # a phone's clock may run a little fast
PAST_LIMIT = timedelta(days=30)  # a visit done offline is synced within days, not months


@dataclass(frozen=True)
class Result:
    """The fields to set. Empty: the move was already made, nothing to do."""

    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def noop(self) -> bool:
        return not self.fields


def check_at(at: datetime | None, now: datetime) -> datetime:
    """The time a device says something happened: the server's now when none is given, else
    within five minutes of the future and thirty days of the past (W10-8)."""
    if at is None:
        return now
    if at > now + FUTURE_SKEW or at < now - PAST_LIMIT:
        raise ValidationFailed("That time is not possible", code="bad_time", field="at")
    return at


def _require_attending(user_id: str, is_admin: bool, visit: Mapping[str, Any]) -> None:
    if not can_attend(user_id, is_admin, visit):
        raise Forbidden("Only the people attending can do this", code="not_attending")


def _station(visit: Mapping[str, Any], station_id: str) -> dict[str, Any]:
    for station in visit["stations"]:
        if station["station_id"] == station_id:
            found: dict[str, Any] = station
            return found
    raise NotFound()


def _require_started(visit: Mapping[str, Any]) -> None:
    status = VStatus(visit["status"])
    if status is VStatus.CANCELLED:
        raise Conflict("This visit was cancelled", code="visit_cancelled")
    if status is VStatus.ENDED:
        raise Conflict("This visit has already ended", code="already_ended")
    if status is not VStatus.STARTED:
        raise Conflict("Start the visit first", code="not_started")


def start(visit: Mapping[str, Any], user_id: str, is_admin: bool, at: datetime | None,
          now: datetime) -> Result:
    _require_attending(user_id, is_admin, visit)
    status = VStatus(visit["status"])
    if status is VStatus.STARTED:
        return Result()
    to = move(status, VAction.START)
    return Result({"status": to.value, "started_at": check_at(at, now)})


def _with_station(visit: Mapping[str, Any], station_id: str, **changes: Any) -> dict[str, Any]:
    return {"stations": [
        {**s, **changes} if s["station_id"] == station_id else s for s in visit["stations"]
    ]}


def _require_owner(user_id: str, is_admin: bool, station: Mapping[str, Any]) -> None:
    if not (is_admin or station["owner_staff_id"] == user_id):
        raise Forbidden("Only the station's owner can do this", code="not_owner")


def arrive(visit: Mapping[str, Any], station_id: str, user_id: str, is_admin: bool,
           at: datetime | None, now: datetime) -> Result:
    station = _station(visit, station_id)
    _require_owner(user_id, is_admin, station)
    _require_started(visit)
    if station["arrived_at"] is not None:
        return Result()
    return Result(_with_station(visit, station_id, arrived_at=check_at(at, now)))


def depart(visit: Mapping[str, Any], station_id: str, user_id: str, is_admin: bool,
           at: datetime | None, now: datetime) -> Result:
    station = _station(visit, station_id)
    _require_owner(user_id, is_admin, station)
    _require_started(visit)
    if station["arrived_at"] is None:
        raise Conflict("Arrive at the station first", code="not_arrived")
    if station["departed_at"] is not None:
        return Result()
    when = check_at(at, now)
    if when < station["arrived_at"]:
        raise ValidationFailed("That is before the arrival", code="bad_time", field="at")
    return Result(_with_station(visit, station_id, departed_at=when))


def end(
    visit: Mapping[str, Any], user_id: str, is_admin: bool, *, additional_visit_required: bool,
    follow_up_notes: str | None, overrides: Sequence[Mapping[str, str]], at: datetime | None,
    now: datetime,
) -> Result:
    """VIS-9: say whether another visit is needed; if so, what remains."""
    _require_attending(user_id, is_admin, visit)
    status = VStatus(visit["status"])
    if status is VStatus.ENDED:
        if bool(visit.get("additional_visit_required")) == additional_visit_required:
            return Result()
        raise Conflict("This visit has already ended", code="already_ended")
    to = move(status, VAction.END)
    notes = clean_notes(follow_up_notes)
    if additional_visit_required and not notes:
        raise ValidationFailed("Say what work remains", code="notes_required",
                               field="follow_up_notes")
    if notes is not None and len(notes) > MAX_NOTES:  # clean_notes already checks; belt and braces
        raise ValidationFailed("Too long", code="too_long", field="follow_up_notes")
    return Result({
        "status": to.value, "ended_at": check_at(at, now),
        "additional_visit_required": additional_visit_required, "follow_up_notes": notes,
        "overrides": [dict(o) for o in overrides],
    })


def cancel(visit: Mapping[str, Any], reason: str | None, now: datetime) -> Result:
    status = VStatus(visit["status"])
    if status is VStatus.CANCELLED:
        return Result()
    if status is VStatus.STARTED:
        raise Conflict("A visit that has started can't be cancelled", code="visit_started")
    to = move(status, VAction.CANCEL)
    return Result({"status": to.value, "cancelled_at": now, "cancel_reason": reason})


def restore(visit: Mapping[str, Any]) -> Result:
    status = VStatus(visit["status"])
    if status is VStatus.PLANNED:
        return Result()
    to = move(status, VAction.RESTORE)
    return Result({"status": to.value, "cancelled_at": None, "cancel_reason": None})
