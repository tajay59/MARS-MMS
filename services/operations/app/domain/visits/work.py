"""The work record of a station on a visit (PRD VIS-7, VIS-8; TRD §3.2.1, §5.4 `WorkRecord`;
W11-1 to W11-4). No I/O.

A station's owner (or an admin) records what was found and done there. The record is saved whole,
with the version the editor was looking at (`base_version`): there is no merge (ADR-18), so a
stale save is a conflict, never a quiet overwrite. The checklist is copied from the templates
when the visit starts (VIS-8), so a template edited later changes nothing already started.

The same checks run when a phone's saved work syncs in Phase 5, so each returns or raises the
codes `/sync` will report (`not_owner`, `not_started`, `visit_cancelled`, `locked`, `work_changed`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from mms_common.errors import Conflict, Forbidden, ValidationFailed

from app.domain.visits.state import VStatus

MAX_CHECKLIST = 120  # template rows (60 each for the station and the add-ons) plus ad-hoc ones
MAX_AD_HOC = 40
MAX_ACTIONS = 20
MAX_CONFIG_VERSIONS = 20
MAX_PARTS = 30
MAX_ISSUES = 30
MAX_NOTES = 4000
MAX_LINE = 200
MAX_DESCRIPTION = 1000

RESULTS = frozenset({"ok", "fixed", "issue", "na"})

# What the server keeps and the client never sets
SERVER_FIELDS = ("version", "updated_by", "updated_at", "device_id")


def blank(items: Sequence[Mapping[str, Any]], now: datetime) -> dict[str, Any]:
    """A new record for a station: the template copy and a row of unanswered checks for each item
    (VIS-8). `version` 0 means nobody has saved it yet."""
    return {
        "checklist_template": {"items": [dict(i) for i in items], "copied_at": now},
        "condition_on_arrival": None,
        "checklist": [
            {"item_id": i["id"], "label": i["label"], "group": i.get("group"), "result": None,
             "note": None, "ad_hoc": False}
            for i in items
        ],
        "sensor_actions": [], "config_versions": [], "parts_used": [], "issues_found": [],
        "data_downloaded": None, "condition_on_departure": None, "notes": None,
        "version": 0, "updated_by": None, "updated_at": None, "device_id": None,
    }


def check_can_save(
    visit: Mapping[str, Any], station: Mapping[str, Any], user_id: str, is_admin: bool
) -> None:
    """Who and when (W11-2): the station's owner or an admin, while the visit is under way or
    has ended and is not yet locked by its report."""
    if not (is_admin or station["owner_staff_id"] == user_id):
        raise Forbidden("Only the station's owner can do this", code="not_owner")
    status = VStatus(visit["status"])
    if status is VStatus.CANCELLED:
        raise Conflict("This visit was cancelled", code="visit_cancelled")
    if status is VStatus.PLANNED:
        raise Conflict("Start the visit first", code="not_started")
    if visit.get("locked"):
        raise Conflict("The visit report has been finalized. Ask an admin to reopen it",
                       code="locked")


def _text(value: str | None, field: str, limit: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) > limit:
        raise ValidationFailed(f"Keep it under {limit} characters", code="too_long", field=field)
    return text or None


def _ids_unique(rows: Sequence[Mapping[str, Any]], field: str, key: str = "id") -> None:
    seen: set[str] = set()
    for row in rows:
        if row[key] in seen:
            raise ValidationFailed("Two entries share an id", code="duplicate_id", field=field)
        seen.add(row[key])


def _clean_checklist(
    rows: Sequence[Mapping[str, Any]], template_items: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Every template item has exactly one row (a missing one comes back unanswered: items
    cannot be removed, W11-3); the rest are the technician's own (`ad_hoc`)."""
    by_item = {i["id"]: i for i in template_items}
    given: dict[str, Mapping[str, Any]] = {}
    ad_hoc: list[dict[str, Any]] = []
    for row in rows:
        if row.get("result") is not None and row["result"] not in RESULTS:
            raise ValidationFailed("That is not a result", code="bad_result", field="checklist")
        note = _text(row.get("note"), "checklist", MAX_LINE * 5)
        if row.get("ad_hoc"):
            label = _text(row.get("label"), "checklist", MAX_LINE)
            if not label:
                raise ValidationFailed("Give the item a name", code="required", field="checklist")
            if row["item_id"] in by_item:
                raise ValidationFailed("That id belongs to a template item", code="duplicate_id",
                                       field="checklist")
            ad_hoc.append({"item_id": row["item_id"], "label": label, "group": None,
                           "result": row.get("result"), "note": note, "ad_hoc": True})
            continue
        item_id = row["item_id"]
        if item_id not in by_item:
            raise ValidationFailed("That item is not in this visit's checklist",
                                   code="unknown_item", field="checklist")
        if item_id in given:
            raise ValidationFailed("An item is answered twice", code="duplicate_id",
                                   field="checklist")
        given[item_id] = {**row, "note": note}
    if len(ad_hoc) > MAX_AD_HOC:
        raise ValidationFailed(f"Add at most {MAX_AD_HOC} items of your own", code="too_many",
                               field="checklist")
    _ids_unique(ad_hoc, "checklist", "item_id")
    out: list[dict[str, Any]] = []
    for item in template_items:  # the template's order, always complete
        row = given.get(item["id"], {})
        out.append({"item_id": item["id"], "label": item["label"], "group": item.get("group"),
                    "result": row.get("result"), "note": row.get("note"), "ad_hoc": False})
    return out + ad_hoc


def _clean_condition(value: Mapping[str, Any] | None, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    status = value.get("status")
    notes = _text(value.get("notes"), field, MAX_NOTES)
    if status is None and notes is None:
        return None
    return {"status": status, "notes": notes}


def clean_record(
    given: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """The record as it will be stored, from what the owner sent and the record as it is. The
    template copy and the server's fields are never taken from the client. Raises
    `ValidationFailed` naming the part that is wrong."""
    template_items = current["checklist_template"]["items"]
    checklist = _clean_checklist(given.get("checklist", []), template_items)
    if len(checklist) > MAX_CHECKLIST:
        raise ValidationFailed("The checklist is too long", code="too_many", field="checklist")

    actions = [dict(a) for a in given.get("sensor_actions", [])]
    if len(actions) > MAX_ACTIONS:
        raise ValidationFailed(f"Record at most {MAX_ACTIONS} sensor actions", code="too_many",
                               field="sensor_actions")
    _ids_unique(actions, "sensor_actions")
    for action in actions:
        action["note"] = _text(action.get("note"), "sensor_actions", MAX_DESCRIPTION)
        action["parameter"] = _text(action.get("parameter"), "sensor_actions", 32)
        for serial in ("old_serial", "new_serial"):
            action[serial] = _text(action.get(serial), "sensor_actions", 64)
        _check_action(action)

    versions = [dict(v) for v in given.get("config_versions", [])]
    if len(versions) > MAX_CONFIG_VERSIONS:
        raise ValidationFailed(f"Record at most {MAX_CONFIG_VERSIONS} configuration versions",
                               code="too_many", field="config_versions")
    _ids_unique(versions, "config_versions")
    for version in versions:
        version["notes"] = _text(version.get("notes"), "config_versions", MAX_DESCRIPTION)
        if len(set(version["files"])) != len(version["files"]) or not version["files"]:
            raise ValidationFailed("Add each file once, and at least one",
                                   code="bad_files", field="config_versions")

    parts = [dict(p) for p in given.get("parts_used", [])]
    issues = [dict(i) for i in given.get("issues_found", [])]
    if len(parts) > MAX_PARTS or len(issues) > MAX_ISSUES:
        raise ValidationFailed("Too many entries", code="too_many", field="parts_used")
    _ids_unique(parts, "parts_used")
    _ids_unique(issues, "issues_found")
    for part in parts:
        description = _text(part.get("description"), "parts_used", MAX_LINE)
        if not description:
            raise ValidationFailed("Say what the part is", code="required", field="parts_used")
        part["description"] = description
    for issue in issues:
        description = _text(issue.get("description"), "issues_found", MAX_DESCRIPTION)
        if not description:
            raise ValidationFailed("Say what the issue is", code="required",
                                   field="issues_found")
        issue["description"] = description

    downloaded = given.get("data_downloaded")
    if downloaded is not None:
        start, end = downloaded.get("from"), downloaded.get("to")
        if start and end and end < start:
            raise ValidationFailed("The period ends before it starts", code="bad_window",
                                   field="data_downloaded")
        downloaded = {"done": bool(downloaded.get("done")), "from": start, "to": end}

    return {
        "checklist_template": current["checklist_template"],
        "condition_on_arrival": _clean_condition(given.get("condition_on_arrival"),
                                                 "condition_on_arrival"),
        "checklist": checklist, "sensor_actions": actions, "config_versions": versions,
        "parts_used": parts, "issues_found": issues, "data_downloaded": downloaded,
        "condition_on_departure": _clean_condition(given.get("condition_on_departure"),
                                                   "condition_on_departure"),
        "notes": _text(given.get("notes"), "notes", MAX_NOTES),
    }


def _check_action(action: Mapping[str, Any]) -> None:
    """What each kind of action needs before it can be applied (slice 2 applies them)."""
    kind = action["action"]
    field = "sensor_actions"
    if kind in ("install", "replace") and not action.get("new_serial"):
        raise ValidationFailed("Enter the new serial", code="serial_required", field=field)
    if kind in ("remove", "replace") and not action.get("old_serial"):
        raise ValidationFailed("Enter the serial of the unit taken out", code="serial_required",
                               field=field)
    if kind in ("calibrate", "clean", "repair") and not (
        action.get("old_serial") or action.get("new_serial")
    ):
        raise ValidationFailed("Enter the serial of the sensor", code="serial_required",
                               field=field)
    if kind in ("install", "replace", "remove", "calibrate") and not action.get("parameter"):
        raise ValidationFailed("Say which parameter it measures", code="parameter_required",
                               field=field)
    if kind == "calibrate" and action.get("calibration") is None:
        raise ValidationFailed("Record the calibration", code="calibration_required", field=field)
    if kind != "calibrate" and action.get("calibration") is not None:
        raise ValidationFailed("Only a calibration has readings", code="unexpected_calibration",
                               field=field)


def content_hash(record: Mapping[str, Any]) -> str:
    """What the owner wrote, without the server's fields: two saves of the same content hash the
    same, so a retry after a lost answer is recognised (the save is idempotent)."""
    content = {k: v for k, v in record.items() if k not in SERVER_FIELDS}
    text = json.dumps(content, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def save(
    current: Mapping[str, Any], cleaned: Mapping[str, Any], base_version: int,
    user_id: str, device_id: str | None, now: datetime,
) -> dict[str, Any] | None:
    """The record to store, or None when it is already stored (a retry of a save that was
    applied: same content, whatever `base_version` the retry carried). A save from a version
    that is not the current one is a conflict (ADR-18): the owner sees the record as it is."""
    if content_hash(cleaned) == content_hash(current):
        return None
    if base_version != current["version"]:
        raise Conflict("This work record was changed since you opened it. Reload it",
                       code="work_changed", version=current["version"])
    return {
        **cleaned, "version": current["version"] + 1, "updated_by": user_id,
        "updated_at": now, "device_id": device_id,
    }
