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
UNITS = "unit_facts"
MODELS = "model_facts"
CONFIGS = "config_facts"
INSTALLS = "installation_facts"
STAFF = "staff_facts"
COLLECTIONS = (STATIONS, REQUESTS, VISITS, CALIBRATIONS, UNITS, MODELS, CONFIGS, INSTALLS, STAFF)

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
UNIT_EVENTS = ("sensor_unit.created", "sensor_unit.updated")
MODEL_EVENTS = ("sensor_model.created", "sensor_model.updated")


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
        "assigned_ids": list(data.get("assigned_staff_ids") or []),
        # Names ride along with the row and are kept in `staff_facts` (W19-11), not in the row
        "staff_names": dict(data.get("assigned_staff_names") or {}),
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
        "time_zone": data.get("time_zone"), "staff_names": dict(data.get("staff_names") or {}),
        "aggregate_version": version,
    }


def calibration_row(data: Mapping[str, Any], version: int) -> dict[str, Any]:
    return {
        "_id": data["calibration_id"], "sensor_unit_id": data["unit_id"],
        "station_id": data.get("station_id"), "org_id": data.get("org_id"),
        "method": data.get("method"), "at": when(data["at"]), "result": data["result"],
        "due_at": when(data.get("due_at")), "voided": False, "aggregate_version": version,
    }


def unit_row(data: Mapping[str, Any], version: int) -> dict[str, Any]:
    """A sensor unit: where it is and when its calibration is due (W19-6). Its organization is
    its station's, joined from `station_facts` when a report needs it."""
    return {
        "_id": data["unit_id"], "serial": data["serial"], "model_id": data["model_id"],
        "status": data["status"], "station_id": data.get("current_station_id"),
        "due_at": when(data.get("calibration_due_at")), "aggregate_version": version,
    }


def model_row(data: Mapping[str, Any], version: int) -> dict[str, Any]:
    return {
        "_id": data["model_id"], "kind": data["kind"], "manufacturer": data["manufacturer"],
        "model": data["model"], "parameters": list(data.get("parameters") or []),
        "interval_days": data.get("default_calibration_interval_days"),
        "aggregate_version": version,
    }


def config_row(data: Mapping[str, Any], version: int) -> dict[str, Any]:
    """A configuration version is written once and never changes (CFG-2): its row is too."""
    return {
        "_id": data["config_id"], "station_id": data["station_id"], "number": data["version"],
        "file_count": data.get("file_count") or 0, "visit_id": data.get("visit_id"),
        "created_at": when(data["created_at"]), "aggregate_version": version,
    }


# What an installation row may hold. An event or a snapshot item names some of these; the repository
# merges what is named, so a removal that arrives before its installation still ends up right.
INSTALL_FIELDS = ("unit_id", "serial", "model_id", "station_id", "parameter", "installed_at",
                  "removed_at")


def install_row(data: Mapping[str, Any]) -> dict[str, Any]:
    """The fields of an installation that `data` names: nothing is set to None, so an old
    snapshot cannot undo a removal that an event already recorded."""
    row: dict[str, Any] = {"_id": data["installation_id"]}
    for key in INSTALL_FIELDS:
        value = data.get(key)
        if value is not None:
            row[key] = when(value) if key.endswith("_at") else value
    return row


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
    **{t: (UNITS, unit_row) for t in UNIT_EVENTS},
    **{t: (MODELS, model_row) for t in MODEL_EVENTS},
}

# What `/internal/snapshot/<entity>` fills
SNAPSHOT_ENTITIES: dict[str, tuple[str, Builder]] = {
    "stations": (STATIONS, station_row),
    "requests": (REQUESTS, request_row),
    "visits": (VISITS, visit_row),
    "calibrations": (CALIBRATIONS, calibration_row),
    "sensor_units": (UNITS, unit_row),
    "sensor_models": (MODELS, model_row),
    "config_versions": (CONFIGS, config_row),
    "installations": (INSTALLS, lambda data, _version: install_row(data)),
}
