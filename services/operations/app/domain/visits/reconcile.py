"""Reconciling the inventory with a visit's sensor actions (PRD SEN-4, SEN-5, CAL-1; TRD §3.2.3;
W11-5 to W11-8). No I/O.

A station's work record lists what the technician did: install, remove, replace, calibrate, clean,
repair. When the visit has ended (and on every later save) the inventory must say the same, and
when the record is corrected the inventory must follow, exactly. `plan` takes the actions as they
are now, the applications already written for this visit and station, and the facts it needs
(the units, the installations, the models), and returns the steps to write. The caller runs them
in the same Mongo transaction as the work save and the events, so a refused correction writes
nothing.

- A **new** action is applied. An **unchanged** one (same `action_hash`) is skipped.
- A **changed** or **removed** action is reversed, and so is every action applied after it (its
  effects may rest on it), newest first; the ones still in the record are then applied again.
- Reversal is **refused** (`sensor_changed_later`) when a unit it touched has changed since for
  any reason that is not one of these actions, or the parameter it freed is taken now.

The planner runs the steps against a copy of the inventory as it goes, so a replace followed by
a calibration of the new unit works in one pass.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mms_common.errors import Conflict, ValidationFailed
from mms_common.ids import new_id

from app.domain.stations import sensors as rules
from app.domain.stations.sensors import UnitStatus

# What a reversal puts back on a unit (and nothing else: the unit's notes, interval and serial
# are not an action's business)
UNIT_FIELDS = (
    "status", "current_station_id", "current_org_id", "current_parameter", "last_calibrated_at",
    "last_calibration_result", "calibration_due_at", "flags",
)
AFTER_REMOVAL = {
    "faulty": UnitStatus.IN_REPAIR.value, "retired": UnitStatus.RETIRED.value,
    "calibration": UnitStatus.IN_STOCK.value, "other": UnitStatus.IN_STOCK.value,
}
NOTES_ONLY = frozenset({"clean", "repair"})


class SensorChangedLater(Conflict):
    code, title = "sensor_changed_later", "The inventory has changed since this action"


class SerialAmbiguous(ValidationFailed):
    code, title = "serial_ambiguous", "More than one model has that serial"


class ModelRequired(ValidationFailed):
    code, title = "model_required", "Say which model it is"


class NotAtStation(ValidationFailed):
    code, title = "unit_not_at_station", "That unit is not installed at this station"


class SerialModelMismatch(ValidationFailed):
    code, title = "serial_model_mismatch", "That serial belongs to another model"


def action_hash(action: Mapping[str, Any]) -> str:
    """What makes two versions of an action the same: everything that decides its effects, and
    not the note."""
    keys = ("action", "parameter", "sensor_model_id", "old_serial", "new_serial",
            "removal_reason", "calibration")
    text = json.dumps({k: action.get(k) for k in keys}, sort_keys=True, default=str,
                      separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def serials_in(actions: Sequence[Mapping[str, Any]]) -> set[str]:
    return {s for a in actions for s in (a.get("old_serial"), a.get("new_serial")) if s}


# --- What the planner reads and writes -----------------------------------------------------------


@dataclass
class Step:
    """One write. `op` names it; the rest is its data (see `api/visits/sensor_apply.py`)."""

    op: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    reversed_ids: list[str] = field(default_factory=list)
    applied_ids: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.steps


@dataclass
class World:
    """The inventory as the planner sees it, changed as the steps are planned."""

    station: dict[str, Any]
    units: dict[str, dict[str, Any]]
    models: dict[str, dict[str, Any]]
    installs: dict[str, dict[str, Any]]  # unit id -> its open installation at this station
    installations: dict[str, dict[str, Any]]  # every installation loaded, open or closed, by id
    now: datetime
    user_name: str

    @classmethod
    def of(
        cls, station: dict[str, Any], units: Sequence[dict[str, Any]],
        models: Mapping[str, dict[str, Any]], installations: Sequence[dict[str, Any]],
        now: datetime, user_name: str,
    ) -> World:
        """`installations`: those open at the station, and any an earlier application opened or
        closed (a reversal puts them back)."""
        loaded = {i["_id"]: copy.deepcopy(i) for i in installations}
        return cls(
            station=station, units={u["_id"]: copy.deepcopy(u) for u in units},
            models=dict(models),
            installs={i["sensor_unit_id"]: i for i in loaded.values()
                      if i["removed_at"] is None and i["station_id"] == station["_id"]},
            installations=loaded, now=now, user_name=user_name,
        )

    def occupied(self) -> set[str]:
        return {
            p for u in self.units.values()
            if u["status"] == UnitStatus.INSTALLED.value
            and u.get("current_station_id") == self.station["_id"]
            and (p := u.get("current_parameter"))
        }

    def holder(self, parameter: str) -> dict[str, Any] | None:
        for u in self.units.values():
            if (u["status"] == UnitStatus.INSTALLED.value
                    and u.get("current_station_id") == self.station["_id"]
                    and u.get("current_parameter") == parameter):
                return u
        return None

    def find(self, serial: str, model_id: str | None) -> dict[str, Any] | None:
        serial = rules.normalize_serial(serial)
        found = [u for u in self.units.values() if u["serial"] == serial
                 and (model_id is None or u["model_id"] == model_id)]
        if len(found) > 1:
            raise SerialAmbiguous("More than one model has that serial. Choose the model",
                                  field="sensor_actions", serial=serial)
        return found[0] if found else None


def _snapshot(unit: Mapping[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(unit.get(k)) for k in UNIT_FIELDS}


# --- Applying -----------------------------------------------------------------------------------


@dataclass
class Context:
    """What an action needs besides the world."""

    visit: Mapping[str, Any]
    station_visit: Mapping[str, Any]  # the station as it is on the visit
    user_id: str
    at: datetime  # when the work is taken to have happened


def _bump(world: World, unit_id: str, changes: dict[str, Any]) -> int:
    """Change a unit in the copy of the inventory; every write moves its version by one."""
    unit = world.units[unit_id]
    unit.update(changes)
    unit["version"] = int(unit["version"]) + 1
    return int(unit["version"])


def _new_unit(
    action: Mapping[str, Any], serial: str, world: World, ctx: Context
) -> dict[str, Any]:
    model_id = action.get("sensor_model_id")
    if not model_id or model_id not in world.models:
        raise ModelRequired(
            f"{serial} is not in the inventory. Say which model it is so it can be added",
            field="sensor_actions", serial=serial,
        )
    model = world.models[model_id]
    now = world.now
    doc = {
        "_id": new_id(), "model_id": model_id, "serial": serial,
        "status": UnitStatus.IN_STOCK.value, "current_station_id": None, "current_org_id": None,
        "current_parameter": None, "calibration_interval_days": None, "last_calibrated_at": None,
        "last_calibration_result": None, "calibration_due_at": None, "needs_review": True,
        "flags": [], "notes": f"Added from visit {ctx.visit['ref']} (check the details)",
        "created_at": now, "created_by": ctx.user_id, "updated_at": now, "updated_by": ctx.user_id,
        "version": 1,
    }
    doc["calibration_due_at"] = rules.due_at(None, rules.interval_days(doc, model))
    return doc


def _check_model(unit: Mapping[str, Any], action: Mapping[str, Any]) -> None:
    wanted = action.get("sensor_model_id")
    if wanted and unit["model_id"] != wanted:
        raise SerialModelMismatch(
            "That serial belongs to another model", field="sensor_actions",
            serial=unit["serial"],
        )


def _remove(
    world: World, ctx: Context, action: Mapping[str, Any], serial: str, model_id: str | None,
    reason: str | None, effects: dict[str, Any], out: list[Step],
) -> str | None:
    """Take an installed unit off the station. Returns the parameter it measured."""
    unit = world.find(serial, model_id)
    if (unit is None or unit["status"] != UnitStatus.INSTALLED.value
            or unit.get("current_station_id") != world.station["_id"]):
        raise NotAtStation(f"{serial} is not installed at this station", field="sensor_actions",
                           serial=serial)
    opened = world.installs.get(unit["_id"])
    if opened is None:  # pragma: no cover - an installed unit always has an open installation
        raise NotAtStation(f"{serial} has no open installation", field="sensor_actions",
                           serial=serial)
    parameter: str | None = unit.get("current_parameter")
    rules.check_when(ctx.at, world.now, not_before=opened["installed_at"])
    after = AFTER_REMOVAL.get(reason or "other", UnitStatus.IN_STOCK.value)
    before = _snapshot(unit)
    changes = {"status": after, "current_station_id": None, "current_org_id": None,
               "current_parameter": None}
    version_after = _bump(world, unit["_id"], changes)
    world.installs.pop(unit["_id"], None)
    opened["removed_at"] = ctx.at
    effects["units"].append({"unit_id": unit["_id"], "before": before,
                             "version_after": version_after, "created": False})
    effects["closed"].append({"installation_id": opened["_id"]})
    out.append(Step("remove", {
        "unit_id": unit["_id"], "changes": changes, "installation_id": opened["_id"],
        "at": ctx.at, "reason": reason, "action_id": action["id"],
        "removed_visit_id": ctx.visit["_id"],
    }))
    return parameter


def _install(
    world: World, ctx: Context, action: Mapping[str, Any], serial: str, parameter: str | None,
    effects: dict[str, Any], out: list[Step],
) -> None:
    unit = world.find(serial, action.get("sensor_model_id"))
    created = False
    if unit is None:
        if world.find(serial, None) is not None:  # the serial is another model's
            raise SerialModelMismatch(
                "That serial belongs to another model", field="sensor_actions", serial=serial)
        unit = _new_unit(action, serial, world, ctx)
        world.units[unit["_id"]] = copy.deepcopy(unit)
        out.append(Step("create_unit", {"doc": copy.deepcopy(unit), "action_id": action["id"]}))
        effects["units"].append({"unit_id": unit["_id"], "before": None, "version_after": 1,
                                 "created": True})
        created = True
    else:
        _check_model(unit, action)
    model = world.models[unit["model_id"]]
    rules.check_install(unit, model, world.station, parameter, world.occupied())
    rules.check_when(ctx.at, world.now)
    station = world.station
    before = _snapshot(unit)
    changes = {"status": UnitStatus.INSTALLED.value, "current_station_id": station["_id"],
               "current_org_id": station["owner_org_id"], "current_parameter": parameter}
    version_after = _bump(world, unit["_id"], changes)
    installation = {
        "_id": new_id(), "sensor_unit_id": unit["_id"], "station_id": station["_id"],
        "org_id": station["owner_org_id"], "parameter": parameter, "installed_at": ctx.at,
        "removed_at": None, "removal_reason": None, "installed_visit_id": ctx.visit["_id"],
        "removed_visit_id": None, "source_action_id": action["id"],
        "created_at": world.now, "created_by": ctx.user_id, "updated_at": world.now,
        "updated_by": ctx.user_id, "version": 1,
    }
    world.installs[unit["_id"]] = installation
    world.installations[installation["_id"]] = installation
    if created:  # the unit's only write is its insert plus this one: keep one effect per unit
        effects["units"][-1]["version_after"] = version_after
    else:
        effects["units"].append({"unit_id": unit["_id"], "before": before,
                                 "version_after": version_after, "created": False})
    effects["opened"].append({"installation_id": installation["_id"]})
    out.append(Step("install", {
        "unit_id": unit["_id"], "changes": changes, "installation": installation,
        "action_id": action["id"],
    }))


def _calibrate(
    world: World, ctx: Context, action: Mapping[str, Any], effects: dict[str, Any],
    out: list[Step],
) -> None:
    serial = action.get("old_serial") or action.get("new_serial")
    unit = world.find(str(serial), action.get("sensor_model_id"))
    if (unit is None or unit["status"] != UnitStatus.INSTALLED.value
            or unit.get("current_station_id") != world.station["_id"]):
        raise NotAtStation(f"{serial} is not installed at this station", field="sensor_actions",
                           serial=str(serial))
    data = action["calibration"]
    rules.check_when(ctx.at, world.now)
    readings = [dict(r) for r in data.get("readings", [])]
    rules.check_readings(readings)
    model = world.models.get(unit["model_id"])
    changes = rules.unit_after_calibration(unit, model, ctx.at, data["result"])
    before = _snapshot(unit)
    version_after = _bump(world, unit["_id"], changes) if changes else int(unit["version"])
    doc = {
        "_id": new_id(), "sensor_unit_id": unit["_id"], "station_id": world.station["_id"],
        "org_id": world.station["owner_org_id"], "visit_id": ctx.visit["_id"],
        "source_action_id": action["id"], "at": ctx.at, "method": data["method"],
        "reference_instrument": data.get("reference_instrument"), "readings": readings,
        "result": data["result"], "certificate_media_id": None,
        "performed_by": world.user_name, "notes": action.get("note"), "voided_at": None,
        "created_at": world.now, "created_by": ctx.user_id, "updated_at": world.now,
        "updated_by": ctx.user_id, "version": 1,
    }
    effects["units"].append({"unit_id": unit["_id"], "before": before if changes else None,
                             "version_after": version_after, "created": False,
                             "touched": bool(changes)})
    effects["calibrations"].append({"calibration_id": doc["_id"]})
    out.append(Step("calibrate", {
        "unit_id": unit["_id"], "changes": changes, "calibration": doc, "action_id": action["id"],
    }))


def _blank_effects() -> dict[str, Any]:
    return {"units": [], "opened": [], "closed": [], "calibrations": []}


def apply(
    world: World, ctx: Context, action: Mapping[str, Any]
) -> tuple[list[Step], dict[str, Any]]:
    """The steps for one action and the effects to remember for reversing it."""
    kind = action["action"]
    effects = _blank_effects()
    out: list[Step] = []
    if kind == "install":
        _install(world, ctx, action, action["new_serial"], action.get("parameter"), effects, out)
    elif kind == "remove":
        _remove(world, ctx, action, action["old_serial"], action.get("sensor_model_id"),
                action.get("removal_reason"), effects, out)
    elif kind == "replace":
        # the model named is the new sensor's (it may have to be created); the old one is found
        parameter = _remove(world, ctx, action, action["old_serial"], None,
                            action.get("removal_reason"), effects, out)
        _install(world, ctx, action, action["new_serial"], action.get("parameter") or parameter,
                 effects, out)
    elif kind == "calibrate":
        _calibrate(world, ctx, action, effects, out)
    elif kind in NOTES_ONLY:
        pass  # clean and repair are notes: the inventory does not change (W11, question 3)
    else:  # pragma: no cover - the schema allows only the six
        raise ValidationFailed("Unknown sensor action", code="bad_action", field="sensor_actions")
    effects["touched_units"] = sorted({e["unit_id"] for e in effects["units"]})
    return out, effects


# --- Reversing ----------------------------------------------------------------------------------


def _check_untouched(world: World, suffix: Sequence[Mapping[str, Any]]) -> None:
    """Refuse when something other than these actions has changed a unit they touched. Each
    write moves a unit's version by one, so the unit must stand at the version the last of these
    actions left it at."""
    last: dict[str, tuple[int, str]] = {}
    for app in suffix:
        for e in app["effects"]["units"]:
            last[e["unit_id"]] = (int(e["version_after"]), app["_id"])
    for unit_id, (version, action_id) in last.items():
        unit = world.units.get(unit_id)
        if unit is None or int(unit["version"]) != version:
            serial = unit["serial"] if unit else "?"
            raise SensorChangedLater(
                f"{serial} has been changed since this action was applied. Correct it on the "
                "later visit or ask an admin to change it in the inventory",
                field="sensor_actions", action_id=action_id, serial=serial,
            )


def reverse(world: World, app: Mapping[str, Any], out: list[Step]) -> None:
    """Undo one application exactly, in the copy of the inventory and as steps."""
    effects = app["effects"]
    for c in reversed(effects["closed"]):
        opened = world.installations.get(c["installation_id"])
        if opened is not None:
            opened["removed_at"] = None
            world.installs[opened["sensor_unit_id"]] = opened
    for o in reversed(effects["opened"]):
        gone = world.installations.pop(o["installation_id"], None)
        if gone is not None:
            world.installs.pop(gone["sensor_unit_id"], None)
    for e in reversed(effects["units"]):
        unit = world.units[e["unit_id"]]
        if e.get("created"):
            out.append(Step("undo_create", {"unit_id": unit["_id"], "action_id": app["_id"]}))
            world.units.pop(unit["_id"], None)
            world.installs.pop(unit["_id"], None)
            continue
        before = e["before"]
        if before is None:  # a calibration older than the unit's last one changed nothing
            continue
        restore = {k: before[k] for k in UNIT_FIELDS}
        parameter = before.get("current_parameter")
        if (before["status"] == UnitStatus.INSTALLED.value and parameter
                and (holder := world.holder(parameter)) is not None
                and holder["_id"] != unit["_id"]):
            raise SensorChangedLater(
                f"{parameter} at this station is now measured by {holder['serial']}",
                field="sensor_actions", action_id=app["_id"], serial=unit["serial"],
            )
        _bump(world, unit["_id"], restore)
        out.append(Step("restore_unit", {"unit_id": unit["_id"], "changes": restore,
                                         "action_id": app["_id"]}))
    for c in reversed(effects["closed"]):
        out.append(Step("reopen", {"installation_id": c["installation_id"],
                                   "action_id": app["_id"]}))
    for o in reversed(effects["opened"]):
        out.append(Step("undo_installation", {"installation_id": o["installation_id"],
                                              "action_id": app["_id"]}))
    for c in reversed(effects["calibrations"]):
        out.append(Step("void_calibration", {"calibration_id": c["calibration_id"],
                                             "action_id": app["_id"]}))
    out.append(Step("forget", {"action_id": app["_id"], "unit_ids": effects["touched_units"]}))


def plan(
    world: World, ctx: Context, actions: Sequence[Mapping[str, Any]],
    applications: Sequence[Mapping[str, Any]],
) -> Plan:
    """The steps that make the inventory agree with `actions`. `applications` are the rows
    written so far for this visit and station, in the order they were applied. Raises the
    errors above; the caller's transaction then writes nothing."""
    wanted = {a["id"]: a for a in actions}
    first_change = next(
        (i for i, app in enumerate(applications)
         if app["_id"] not in wanted or action_hash(wanted[app["_id"]]) != app["action_hash"]),
        None,
    )
    result = Plan()
    suffix = list(applications[first_change:]) if first_change is not None else []
    if suffix:
        _check_untouched(world, suffix)
        for app in reversed(suffix):
            reverse(world, app, result.steps)
            result.reversed_ids.append(app["_id"])
    kept = {app["_id"] for app in applications[:first_change]} if first_change is not None else {
        app["_id"] for app in applications}
    # Again, in the order they were applied; then the new ones in the order written
    again = [wanted[app["_id"]] for app in suffix if app["_id"] in wanted]
    fresh = [a for a in actions if a["id"] not in kept and a["id"] not in {x["id"] for x in again}]
    for action in [*again, *fresh]:
        steps, effects = apply(world, ctx, action)
        result.steps += steps
        result.steps.append(Step("remember", {
            "action_id": action["id"], "action_hash": action_hash(action), "effects": effects,
        }))
        result.applied_ids.append(action["id"])
    return result
