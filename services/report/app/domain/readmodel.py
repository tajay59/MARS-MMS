"""The report service's read model: rows from operations' events and snapshots (TRD §5.4, §8.6).

An event and a snapshot item carry the same fields (the snapshot is "shaped like the events'
data"), so one builder serves both. A row keeps the `aggregate_version` it was built from: the
repository writes it only if that is newer than the stored one, so events and a backfill can
arrive in any order and end in the same state.

No I/O here (rule 7).

Where the rows differ from the TRD's first sketch (as built, W16): `request_facts` has no `country`
or `visit_count` (the country is the first station's, joined in `station_facts` when a summary is
made, and the visit count is counted in `visit_facts`), and `visit_facts.element_counts` is filled
by the draft report (W16 slice 2), because board events carry the element's revision, not the
visit's version.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

STATIONS = "station_facts"
REQUESTS = "request_facts"
VISITS = "visit_facts"
CALIBRATIONS = "calibration_facts"
COLLECTIONS = (STATIONS, REQUESTS, VISITS, CALIBRATIONS)

# What a later event does not repeat: kept from the stored row when the new one lacks it
VISIT_KEEP = ("started_at", "ended_at", "additional_visit_required", "element_counts",
              "report_finalized_at")

# The request milestones the read model keeps as columns (REQ-16, PRD §5.1)
MILESTONES = ("submitted_at", "approved_at", "assigned_at", "first_visit_at",
              "review_started_at", "closed_at")

# Events that carry a request / a visit's state at the visit's own version. Board-element events
# are not here: their `aggregate_version` is the element's revision (W11-35).
REQUEST_EVENTS = (
    "request.submitted", "request.updated", "request.approved", "request.denied",
    "request.cancelled", "request.status_changed", "request.assigned", "request.staff_changed",
    "request.released",
)
VISIT_EVENTS = (
    "visit.scheduled", "visit.rescheduled", "visit.cancelled", "visit.restored", "visit.started",
    "visit.ended", "visit.station_owner_changed", "visit.station_arrived",
    "visit.station_departed",
)
STATION_EVENTS = ("station.created", "station.updated")
CALIBRATION_EVENTS = ("calibration.recorded",)


def when(value: Any) -> datetime | None:
    """A time from an event (a datetime) or a snapshot (an ISO string), in UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def station_row(data: Mapping[str, Any], version: int) -> dict[str, Any]:
    return {
        "_id": data["station_id"], "org_id": data["org_id"], "country": data["country"],
        "type": data.get("type"), "status": data["status"], "code": data["code"],
        "name": data["name"], "time_zone": data.get("time_zone"), "aggregate_version": version,
    }


def request_row(data: Mapping[str, Any], version: int) -> dict[str, Any]:
    milestones = data.get("milestones") or {}
    row: dict[str, Any] = {
        "_id": data["request_id"], "ref": data["ref"], "org_id": data["org_id"],
        "station_ids": list(data["station_ids"]), "category": data["category"],
        "priority": data["priority"], "status": data["status"],
        "reopen_count": data.get("reopen_count") or 0, "auto_closed": False,
        "aggregate_version": version,
    }
    for key in MILESTONES:
        row[key] = when(milestones.get(key))
    return row


def visit_row(data: Mapping[str, Any], version: int) -> dict[str, Any]:
    return {
        "_id": data["visit_id"], "ref": data.get("ref"), "request_id": data["request_id"],
        "org_id": data["org_id"], "status": data["status"],
        "staff_ids": list(data.get("staff_ids", [])), "lead_staff_id": data.get("lead_staff_id"),
        "station_ids": list(data.get("station_ids", [])),
        "planned_start": when(data.get("planned_start")),
        "planned_end": when(data.get("planned_end")),
        "started_at": when(data.get("started_at")), "ended_at": when(data.get("ended_at")),
        "additional_visit_required": data.get("additional_visit_required"),
        "element_counts": None, "report_finalized_at": None,
        "time_zone": data.get("time_zone"), "aggregate_version": version,
    }


def calibration_row(data: Mapping[str, Any], version: int) -> dict[str, Any]:
    return {
        "_id": data["calibration_id"], "sensor_unit_id": data["unit_id"],
        "station_id": data.get("station_id"), "org_id": data.get("org_id"),
        "method": data.get("method"), "at": when(data["at"]), "result": data["result"],
        "due_at": when(data.get("due_at")), "voided": False, "aggregate_version": version,
    }


def keep_from(
    stored: Mapping[str, Any], row: dict[str, Any], keep: tuple[str, ...]
) -> dict[str, Any]:
    """`row` with the kept fields filled from `stored` where the new row has none."""
    kept = {k: stored[k] for k in keep if row.get(k) is None and stored.get(k) is not None}
    return {**row, **kept}


Builder = Callable[[Mapping[str, Any], int], dict[str, Any]]

BUILDERS: dict[str, tuple[str, Builder]] = {
    **{t: (STATIONS, station_row) for t in STATION_EVENTS},
    **{t: (REQUESTS, request_row) for t in REQUEST_EVENTS},
    **{t: (VISITS, visit_row) for t in VISIT_EVENTS},
    **{t: (CALIBRATIONS, calibration_row) for t in CALIBRATION_EVENTS},
}

# What `/internal/snapshot/<entity>` fills
SNAPSHOT_ENTITIES: dict[str, tuple[str, Builder]] = {
    "stations": (STATIONS, station_row),
    "requests": (REQUESTS, request_row),
    "visits": (VISITS, visit_row),
    "calibrations": (CALIBRATIONS, calibration_row),
}
