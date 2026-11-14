"""What a person may read of an audit record (PRD AUD-4, AUD-6; W19-1, W19-2). No I/O here.

An admin reads the whole record. Staff and the Viewer, on a resource's History tab, read who did
what and when, and the *names* of the fields that changed: never the IP address, the device, the
trace id, the old and new values or the event's data, which can hold personal data.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from mms_common.time import to_iso

from app.domain.audit import _ms

# What a History tab can be asked for, and which record belongs to which page (W19-2). A record
# belongs to a page when the page's thing is the record's resource, or the event names it in
# its data (a visit event carries its `request_id`).
HistoryType = Literal["station", "request", "visit"]

# Board edits and file steps would bury the page in noise: the History shows the visit's moves,
# not every note. The audit log (admins) still has them all.
NOISY_PREFIXES = ("visit.element_", "visit.media_", "media.")
# A station's page lists what happened to the station itself, not to its visits' boards.
STATION_PREFIXES = ("station.", "qr.", "sensor", "calibration.", "config.", "document.")

EXPORT_MAX = 50_000

# The action as a clause that follows the person's name.
WORDS: dict[str, str] = {
    "request.submitted": "created the request",
    "request.updated": "changed the request",
    "request.approved": "approved the request",
    "request.denied": "denied the request",
    "request.cancelled": "cancelled the request",
    "request.assigned": "assigned the request",
    "request.staff_changed": "changed who is on the request",
    "request.released": "let go of the request",
    "request.status_changed": "changed the status of the request",
    "request.client_review_started": "started the client review",
    "request.reopened": "sent the work back",
    "request.closed": "closed the request",
    "comment.added": "added a comment",
    "comment.updated": "changed a comment",
    "client_report.submitted": "submitted a report of their own",
    "visit.scheduled": "scheduled a visit",
    "visit.rescheduled": "moved a visit",
    "visit.cancelled": "cancelled a visit",
    "visit.restored": "restored a visit",
    "visit.started": "started the visit",
    "visit.ended": "ended the visit",
    "visit.prepared": "prepared the visit on a phone",
    "visit.station_owner_changed": "gave a station to someone else on the visit",
    "visit.station_arrived": "arrived at a station",
    "visit.station_departed": "left a station",
    "report.drafted": "made a draft report",
    "report.signed": "signed the report",
    "report.finalized": "finalized the report",
    "report.reopened": "reopened the report",
    "report.generated": "made a report PDF",
    "report.closeout_generated": "made the close-out report",
    "station.created": "added the station",
    "station.updated": "changed the station",
    "qr.regenerated": "replaced the QR label",
    "sensor.installed": "installed a sensor",
    "sensor.removed": "removed a sensor",
    "sensor.application_reversed": "undid a sensor change",
    "sensor_unit.created": "added a sensor unit",
    "sensor_unit.updated": "changed a sensor unit",
    "calibration.recorded": "recorded a calibration",
    "calibration.voided": "voided a calibration",
    "config.version_created": "saved a configuration version",
    "document.uploaded": "uploaded a document",
    "document.updated": "changed a document",
    "audit.exported": "exported the audit log",
    "audit.verified": "checked the audit chain",
}


def words(action: str, record: dict[str, Any] | None = None) -> str:
    """The action in words. A few read differently from their data (an internal comment)."""
    data = (record or {}).get("metadata") or {}
    if action in {"comment.added", "comment.updated"} and data.get("internal") is True:
        return WORDS[action].replace("a comment", "an internal comment")
    if action in WORDS:
        return WORDS[action]
    return action.replace("_", " ").replace(".", ": ", 1)


def _fields(record: dict[str, Any]) -> list[str]:
    before, after = record.get("before"), record.get("after")
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        return [str(k) for k in keys]
    listed = (record.get("metadata") or {}).get("changed_fields")
    if isinstance(listed, list):
        return sorted({str(k) for k in listed})
    return []


def _role(roles: list[str]) -> str | None:
    for name in ("admin", "technician", "viewer", "client"):
        if name in roles:
            return name
    return roles[0] if roles else None


def _time(value: Any) -> str | None:
    return to_iso(value) if isinstance(value, datetime) else None


def staff_view(record: dict[str, Any]) -> dict[str, Any]:
    """One History entry (W19-2): no address, device, trace id, values or data."""
    actor = record.get("actor") or {}
    return {
        "seq": record["seq"],
        "at": _time(record.get("at")),
        "actor_name": actor.get("name"),
        "actor_role": _role(list(actor.get("roles") or [])),
        "action": record["action"],
        "summary": words(record["action"], record),
        "changed_fields": _fields(record),
    }


def admin_view(record: dict[str, Any]) -> dict[str, Any]:
    """The whole record, for the audit log (W19-1)."""
    actor = record.get("actor") or {}
    before, after = record.get("before"), record.get("after")
    changes = (
        [{"field": f, "before": before.get(f), "after": after.get(f)} for f in _fields(record)]
        if isinstance(before, dict) and isinstance(after, dict) else []
    )
    return {
        "seq": record["seq"],
        "event_id": record["_id"],
        "at": _time(record.get("at")),
        "received_at": _time(record.get("received_at")),
        "actor": {
            "user_id": actor.get("user_id"), "name": actor.get("name"),
            "roles": list(actor.get("roles") or []), "ip": actor.get("ip"),
            "user_agent": actor.get("user_agent"), "device_id": actor.get("device_id"),
        },
        "action": record["action"],
        "summary": words(record["action"], record),
        "resource": record.get("resource"),
        "org_id": record.get("org_id"),
        "changes": changes,
        "before": before,
        "after": after,
        "metadata": record.get("metadata") or {},
        "correlation_id": record.get("correlation_id"),
        "source_service": record.get("source_service"),
        "hash": record["hash"],
        "prev_hash": record["prev_hash"],
    }


def export_header() -> list[str]:
    return ["seq", "at", "actor_name", "actor_roles", "actor_ip", "action", "resource_type",
            "resource_id", "org_id", "correlation_id", "source_service", "before", "after",
            "metadata", "hash"]


def export_row(record: dict[str, Any]) -> list[Any]:
    actor = record.get("actor") or {}
    resource = record.get("resource") or {}

    def as_json(value: Any) -> str:
        return "" if value is None else json.dumps(value, sort_keys=True, default=str,
                                                      ensure_ascii=False)

    return [
        record["seq"], record.get("at"), actor.get("name"), " ".join(actor.get("roles") or []),
        actor.get("ip"), record["action"], resource.get("type"), resource.get("id"),
        record.get("org_id"), record.get("correlation_id"), record.get("source_service"),
        as_json(record.get("before")), as_json(record.get("after")),
        as_json(record.get("metadata")), record["hash"],
    ]


def own_record(
    *, action: str, at: datetime, actor: dict[str, Any], correlation_id: str | None,
    metadata: dict[str, Any], event_id: str, org_id: str | None = None,
    resource: tuple[str, str] = ("audit_log", "audit"),
) -> dict[str, Any]:
    """A record the audit module writes about itself (W19-5): an export, a check. It goes
    through the same chain as every other, so looking at the trail leaves a trace in it."""
    return {
        "_id": event_id, "at": _ms(at), "received_at": _ms(at), "actor": actor, "action": action,
        "event_version": 1, "resource": {"type": resource[0], "id": resource[1]},
        "org_id": org_id, "before": None, "after": None, "metadata": metadata,
        "correlation_id": correlation_id, "source_service": "platform", "aggregate_version": 1,
    }

