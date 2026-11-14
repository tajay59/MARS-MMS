"""Planning a visit: who, where, when (PRD VIS-1, VIS-2; AFD J5 steps 3, 5 and 5b; W10-3 to
W10-5). No I/O: the route looks people and stations up and passes what it found.

A visit has attending staff (one of them the lead) and one owner per station, chosen from the
attending staff (ADR-18). Dates are UTC (rule 8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from mms_common.errors import Conflict, Forbidden, ValidationFailed

MAX_STAFF = 10
MAX_STATIONS = 20
MAX_DAYS = 31
MAX_NOTES = 2000


def clean_notes(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    if len(stripped) > MAX_NOTES:
        raise ValidationFailed(f"Keep it under {MAX_NOTES} characters", code="too_long",
                               field="notes")
    return stripped or None


def check_window(start: datetime, end: datetime) -> None:
    if end <= start:
        raise ValidationFailed("The visit must end after it starts", code="bad_window",
                               field="planned_end")
    if end - start > timedelta(days=MAX_DAYS):
        raise ValidationFailed(f"A visit lasts at most {MAX_DAYS} days", code="too_long",
                               field="planned_end")


def clean_staff(staff_ids: Sequence[str], lead: str | None) -> tuple[list[str], str]:
    """One to ten people, each once, and the lead (the first by default) is one of them."""
    unique = list(dict.fromkeys(staff_ids))
    if not unique:
        raise ValidationFailed("Pick at least one person", code="staff_required",
                               field="staff_ids")
    if len(unique) > MAX_STAFF:
        raise ValidationFailed(f"Pick up to {MAX_STAFF} people", code="too_many_staff",
                               field="staff_ids")
    chosen = lead or unique[0]
    if chosen not in unique:
        raise ValidationFailed("The lead must be one of the people attending",
                               code="lead_not_attending", field="lead_staff_id")
    return unique, chosen


def clean_owners(
    stations: Sequence[tuple[str, str | None]], staff_ids: Sequence[str], lead: str,
    request_station_ids: Sequence[str],
) -> dict[str, str]:
    """Each station once, each on the request, each with an owner from the attending staff
    (the lead when none is named). The order given is kept."""
    seen: dict[str, str] = {}
    for station_id, owner in stations:
        if station_id in seen:
            continue
        if station_id not in request_station_ids:
            raise ValidationFailed("That station is not on this request",
                                   code="station_not_on_request", field="stations",
                                   station_id=station_id)
        chosen = owner or lead
        if chosen not in staff_ids:
            raise ValidationFailed("A station's owner must be one of the people attending",
                                   code="owner_not_attending", field="stations",
                                   station_id=station_id)
        seen[station_id] = chosen
    if not seen:
        raise ValidationFailed("Pick at least one station", code="stations_required",
                               field="stations")
    if len(seen) > MAX_STATIONS:
        raise ValidationFailed(f"Pick up to {MAX_STATIONS} stations", code="too_many_stations",
                               field="stations")
    return seen


def check_stations_free(station_ids: Sequence[str], others: Sequence[Mapping[str, Any]]) -> None:
    """A station is in one live visit of a request at a time (W10-5): two owners on one station
    is what ADR-18 exists to prevent. `others` are the request's other live visits."""
    for other in others:
        taken = {s["station_id"] for s in other["stations"]}
        clash = [s for s in station_ids if s in taken]
        if clash:
            raise Conflict(
                "A station can be in only one planned or started visit of a request at a time",
                code="station_in_other_visit", station_id=clash[0], visit_ref=other["ref"],
            )


# --- who may ------------------------------------------------------------------------------------


def can_schedule(user_id: str, is_admin: bool, assigned_ids: Sequence[str]) -> bool:
    """The request's assigned staff, or an admin (VIS-1)."""
    return is_admin or user_id in assigned_ids


def can_manage(
    user_id: str, is_admin: bool, visit: Mapping[str, Any], assigned_ids: Sequence[str]
) -> bool:
    """Reschedule or cancel: an admin, the request's assigned staff, the person who scheduled it
    or anyone attending."""
    return (
        is_admin or user_id in assigned_ids or user_id in visit["staff_ids"]
        or user_id == visit.get("created_by")
    )


def can_attend(user_id: str, is_admin: bool, visit: Mapping[str, Any]) -> bool:
    return is_admin or user_id in visit["staff_ids"]


def require_manage(
    user_id: str, is_admin: bool, visit: Mapping[str, Any], assigned_ids: Sequence[str]
) -> None:
    if not can_manage(user_id, is_admin, visit, assigned_ids):
        raise Forbidden("Only the people on this request can change the visit",
                        code="not_assigned")


# --- stations on a visit ------------------------------------------------------------------------


def new_station(station_id: str, owner: str, info: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "station_id": station_id, "station_code": info.get("code"),
        "station_name": info.get("name"), "time_zone": info.get("time_zone"),
        "owner_staff_id": owner, "arrived_at": None, "departed_at": None,
    }


def rebuilt_stations(
    current: Sequence[Mapping[str, Any]], owners: Mapping[str, str],
    details: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The visit's stations in the order given: one already on the visit keeps its times and
    records, one that joins starts empty (`details` holds its code, name and time zone)."""
    have = {s["station_id"]: dict(s) for s in current}
    out: list[dict[str, Any]] = []
    for station_id, owner in owners.items():
        if station_id in have:
            out.append({**have[station_id], "owner_staff_id": owner})
        else:
            out.append(new_station(station_id, owner, (details or {}).get(station_id, {})))
    return out


# --- changing a visit ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Edit:
    """What a PATCH asks for; `None` means leave it. `stations` is `(station_id, owner|None)`."""

    planned_start: datetime | None = None
    planned_end: datetime | None = None
    staff_ids: Sequence[str] | None = None
    lead_staff_id: str | None = None
    stations: Sequence[tuple[str, str | None]] | None = None
    notes: str | None = None
    notes_given: bool = False


@dataclass(frozen=True)
class Changes:
    fields: dict[str, Any] = field(default_factory=dict)
    changed: list[str] = field(default_factory=list)  # for the rescheduled event
    owner_changes: list[tuple[str, str, str]] = field(default_factory=list)  # station, from, to


def edit_planned(
    visit: Mapping[str, Any], edit: Edit, request_station_ids: Sequence[str],
    others: Sequence[Mapping[str, Any]],
    details: Mapping[str, Mapping[str, Any]] | None = None,
) -> Changes:
    """A planned visit: dates, people, lead, stations, owners and notes can all change."""
    start = edit.planned_start or visit["planned_start"]
    end = edit.planned_end or visit["planned_end"]
    check_window(start, end)

    staff_in = edit.staff_ids if edit.staff_ids is not None else visit["staff_ids"]
    lead_in = edit.lead_staff_id if edit.lead_staff_id is not None else visit["lead_staff_id"]
    if edit.lead_staff_id is None and lead_in not in staff_in:
        lead_in = None  # the lead left the visit: the first person takes over
    staff_ids, lead = clean_staff(staff_in, lead_in)

    current_owners = {s["station_id"]: s["owner_staff_id"] for s in visit["stations"]}
    if edit.stations is not None:
        wanted: list[tuple[str, str | None]] = list(edit.stations)
    else:  # an owner who left the visit hands the station to the lead
        wanted = [(sid, owner if owner in staff_ids else None)
                  for sid, owner in current_owners.items()]
    owners = clean_owners(wanted, staff_ids, lead, request_station_ids)
    check_stations_free(list(owners), others)

    fields: dict[str, Any] = {}
    changed: list[str] = []
    if start != visit["planned_start"] or end != visit["planned_end"]:
        fields.update(planned_start=start, planned_end=end)
        changed.append("dates")
    if staff_ids != visit["staff_ids"]:
        fields["staff_ids"] = staff_ids
        changed.append("staff")
    if lead != visit["lead_staff_id"]:
        fields["lead_staff_id"] = lead
        changed.append("lead")
    if list(owners) != list(current_owners):
        changed.append("stations")
    owner_changes = [
        (sid, current_owners[sid], owner) for sid, owner in owners.items()
        if sid in current_owners and current_owners[sid] != owner
    ]
    if owner_changes:
        changed.append("owners")
    if "stations" in changed or "owners" in changed:
        fields["stations"] = rebuilt_stations(visit["stations"], owners, details)
    if edit.notes_given:
        notes = clean_notes(edit.notes)
        if notes != visit.get("notes"):
            fields["notes"] = notes
    return Changes(fields=fields, changed=changed, owner_changes=owner_changes)


def change_owners(
    visit: Mapping[str, Any], wanted: Mapping[str, str], user_id: str, is_admin: bool,
) -> Changes:
    """A started visit: only owners change, by the lead or an admin (TRD §3.2, AFD J5 step 5b).
    Each new owner is one of the people attending."""
    if not (is_admin or user_id == visit["lead_staff_id"]):
        raise Forbidden("Only the lead or an admin can change an owner", code="not_lead")
    current = {s["station_id"]: s["owner_staff_id"] for s in visit["stations"]}
    moves: list[tuple[str, str, str]] = []
    for station_id, owner in wanted.items():
        if station_id not in current:
            raise ValidationFailed("That station is not on this visit",
                                   code="station_not_on_visit", field="stations",
                                   station_id=station_id)
        if owner not in visit["staff_ids"]:
            raise ValidationFailed("A station's owner must be one of the people attending",
                                   code="owner_not_attending", field="stations",
                                   station_id=station_id)
        if current[station_id] != owner:
            moves.append((station_id, current[station_id], owner))
    if not moves:
        return Changes()
    new = {sid: owner for sid, _, owner in moves}
    owners = {sid: new.get(sid, owner) for sid, owner in current.items()}
    return Changes(
        fields={"stations": rebuilt_stations(visit["stations"], owners)},
        changed=["owners"], owner_changes=moves,
    )
