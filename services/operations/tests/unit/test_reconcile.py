"""Reconciling the inventory with a visit's sensor actions (PRD SEN-4, SEN-5, CAL-1; TRD §3.2.3;
W11-5 to W11-8), step by step, with no I/O. The planner runs against a copy of the inventory, so
a plan's effect is read straight from that copy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mms_common.errors import Conflict, ValidationFailed

from app.domain.visits import reconcile as r

NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)
AT = NOW - timedelta(hours=3)  # the owner arrived three hours ago
STATION = {"_id": "st1", "owner_org_id": "org1", "status": "operational",
           "parameters": ["AT", "RH", "BP"]}
MODEL = {"_id": "m1", "kind": "sensor", "manufacturer": "Vaisala", "model": "HMP155",
         "parameters": ["AT", "RH", "BP"], "default_calibration_interval_days": 365}
VISIT = {"_id": "v1", "ref": "VR-2026-0001-01", "started_at": AT}
CTX = r.Context(VISIT, {"station_id": "st1"}, "u1", AT)


def unit(uid: str, serial: str, **fields: Any) -> dict[str, Any]:
    return {
        "_id": uid, "model_id": "m1", "serial": serial, "status": "in_stock",
        "current_station_id": None, "current_org_id": None, "current_parameter": None,
        "calibration_interval_days": None, "last_calibrated_at": None,
        "last_calibration_result": None, "calibration_due_at": None, "needs_review": False,
        "flags": [], "version": 1, **fields,
    }


def installed(uid: str, serial: str, parameter: str, **fields: Any) -> dict[str, Any]:
    return unit(uid, serial, status="installed", current_station_id="st1",
                current_org_id="org1", current_parameter=parameter, **fields)


def install_row(uid: str, parameter: str, iid: str = "i-old") -> dict[str, Any]:
    return {"_id": iid, "sensor_unit_id": uid, "station_id": "st1", "org_id": "org1",
            "parameter": parameter, "installed_at": AT - timedelta(days=400), "removed_at": None,
            "removal_reason": None, "version": 1}


def world(units: list[dict[str, Any]], installations: list[dict[str, Any]] | None = None):
    return r.World.of(dict(STATION), units, {"m1": MODEL}, installations or [], NOW, "Tech One")


def action(kind: str, id_: str = "a1", **fields: Any) -> dict[str, Any]:
    return {"id": id_, "action": kind, "parameter": None, "sensor_model_id": None,
            "old_serial": None, "new_serial": None, "removal_reason": None, "calibration": None,
            "note": None, **fields}


def ops(plan: r.Plan) -> list[str]:
    return [s.op for s in plan.steps]


def rows(plan: r.Plan, start: int = 1) -> list[dict[str, Any]]:
    """The application rows the executor would have written for a plan."""
    made = []
    for step in plan.steps:
        if step.op == "remember":
            made.append({"_id": step.data["action_id"], "action_hash": step.data["action_hash"],
                         "effects": step.data["effects"], "seq": start + len(made)})
    return made


CALIBRATION = {"method": "field_check", "result": "pass", "reference_instrument": None,
               "readings": [{"reference": 20.0, "before": 20.4, "after": 20.1, "unit": "C"}]}


# --- Applying -----------------------------------------------------------------------------------


@pytest.mark.req("SEN-4")
def test_installing_a_unit_from_stock_opens_an_installation():
    w = world([unit("u2", "V-2")])
    plan = r.plan(w, CTX, [action("install", new_serial="V-2", parameter="AT")], [])
    assert ops(plan) == ["install", "remember"]
    assert w.units["u2"]["status"] == "installed" and w.units["u2"]["current_parameter"] == "AT"
    [step] = [s for s in plan.steps if s.op == "install"]
    inst = step.data["installation"]
    assert inst["source_action_id"] == "a1" and inst["installed_visit_id"] == "v1"
    assert inst["installed_at"] == AT and inst["removed_at"] is None
    assert plan.applied_ids == ["a1"]


@pytest.mark.req("SEN-5")
def test_an_unknown_serial_is_added_once_in_stock_flagged_and_installed():
    w = world([])
    plan = r.plan(w, CTX, [action("install", new_serial="V-NEW", parameter="AT",
                                  sensor_model_id="m1")], [])
    assert ops(plan) == ["create_unit", "install", "remember"]
    created = plan.steps[0].data["doc"]
    assert created["serial"] == "V-NEW" and created["needs_review"] is True
    assert created["model_id"] == "m1" and created["version"] == 1
    assert w.units[created["_id"]]["status"] == "installed"
    effect = plan.steps[-1].data["effects"]["units"][0]
    assert effect["created"] is True and effect["version_after"] == 2


@pytest.mark.req("SEN-5")
def test_an_unknown_serial_without_a_model_cannot_be_added():
    with pytest.raises(r.ModelRequired):
        r.plan(world([]), CTX, [action("install", new_serial="V-NEW", parameter="AT")], [])


@pytest.mark.req("SEN-5")
def test_a_serial_that_exists_under_another_model_is_refused():
    w = world([unit("u2", "V-2")])
    with pytest.raises(r.SerialModelMismatch):  # V-2 is a unit of model m1, not of m2
        r.plan(w, CTX, [action("install", new_serial="V-2", parameter="AT",
                               sensor_model_id="m2")], [])
    two = world([unit("u2", "V-2"), unit("u3", "V-2", model_id="m2")])
    with pytest.raises(r.SerialAmbiguous):
        r.plan(two, CTX, [action("install", new_serial="V-2", parameter="AT")], [])


@pytest.mark.req("SEN-3")
def test_the_install_checks_of_the_inventory_still_apply():
    w = world([unit("u2", "V-2"), installed("u1", "V-1", "AT")], [install_row("u1", "AT")])
    with pytest.raises(Conflict) as taken:
        r.plan(w, CTX, [action("install", new_serial="V-2", parameter="AT")], [])
    assert taken.value.code == "parameter_taken"
    with pytest.raises(ValidationFailed):
        r.plan(world([unit("u3", "V-3")]), CTX,
               [action("install", new_serial="V-3", parameter="ZZ")], [])  # not at the station


@pytest.mark.req("SEN-4")
@pytest.mark.parametrize(("reason", "status"), [
    ("faulty", "in_repair"), ("retired", "retired"), ("calibration", "in_stock"),
    ("other", "in_stock"), (None, "in_stock"),
])
def test_removing_a_unit_sends_it_where_the_reason_says(reason, status):
    w = world([installed("u1", "V-1", "AT")], [install_row("u1", "AT")])
    plan = r.plan(w, CTX, [action("remove", old_serial="V-1", removal_reason=reason)], [])
    assert ops(plan) == ["remove", "remember"]
    assert w.units["u1"]["status"] == status and w.units["u1"]["current_station_id"] is None
    [step] = [s for s in plan.steps if s.op == "remove"]
    assert step.data["installation_id"] == "i-old" and step.data["removed_visit_id"] == "v1"
    assert "u1" not in w.installs


@pytest.mark.req("SEN-4")
def test_removing_a_unit_that_is_not_at_the_station_is_refused():
    elsewhere = unit("u1", "V-1", status="installed", current_station_id="elsewhere",
                     current_org_id="org9", current_parameter="AT")
    w = world([unit("u2", "V-2"), elsewhere])
    for serial in ("V-2", "V-1", "V-9"):
        with pytest.raises(r.NotAtStation):
            r.plan(w, CTX, [action("remove", old_serial=serial)], [])


@pytest.mark.req("SEN-4")
def test_replacing_takes_the_old_unit_out_and_the_new_one_in_on_the_same_parameter():
    w = world([installed("u1", "V-1", "AT"), unit("u2", "V-2")], [install_row("u1", "AT")])
    plan = r.plan(w, CTX, [action("replace", old_serial="V-1", new_serial="V-2",
                                  removal_reason="faulty")], [])
    assert ops(plan) == ["remove", "install", "remember"]
    assert w.units["u1"]["status"] == "in_repair"
    assert (w.units["u2"]["status"], w.units["u2"]["current_parameter"]) == ("installed", "AT")
    effects = plan.steps[-1].data["effects"]
    assert [e["unit_id"] for e in effects["units"]] == ["u1", "u2"]


@pytest.mark.req("SEN-4")
def test_replacing_with_a_new_serial_names_the_model_of_the_new_one_only():
    other = unit("u1", "V-1", model_id="m9", status="installed", current_station_id="st1",
                 current_org_id="org1", current_parameter="AT")
    w = r.World.of(dict(STATION), [other], {"m1": MODEL, "m9": {**MODEL, "_id": "m9"}},
                   [install_row("u1", "AT")], NOW, "Tech")
    plan = r.plan(w, CTX, [action("replace", old_serial="V-1", new_serial="V-NEW",
                                  sensor_model_id="m1")], [])
    assert ops(plan) == ["remove", "create_unit", "install", "remember"]


@pytest.mark.req("CAL-1")
def test_a_field_calibration_records_itself_and_moves_the_due_date():
    w = world([installed("u1", "V-1", "AT")], [install_row("u1", "AT")])
    plan = r.plan(w, CTX, [action("calibrate", old_serial="V-1", parameter="AT",
                                  calibration=CALIBRATION, note="Dry day")], [])
    assert ops(plan) == ["calibrate", "remember"]
    [step] = [s for s in plan.steps if s.op == "calibrate"]
    cal = step.data["calibration"]
    assert cal["visit_id"] == "v1" and cal["source_action_id"] == "a1" and cal["at"] == AT
    assert cal["result"] == "pass" and cal["notes"] == "Dry day"
    assert w.units["u1"]["last_calibrated_at"] == AT
    assert w.units["u1"]["calibration_due_at"] == AT + timedelta(days=365)


@pytest.mark.req("CAL-6")
def test_a_failed_field_calibration_flags_the_unit():
    w = world([installed("u1", "V-1", "AT")], [install_row("u1", "AT")])
    r.plan(w, CTX, [action("calibrate", old_serial="V-1", parameter="AT",
                           calibration={**CALIBRATION, "result": "fail"})], [])
    assert "calibration_failed" in w.units["u1"]["flags"]


@pytest.mark.req("CAL-1")
def test_a_calibration_needs_a_real_reading():
    w = world([installed("u1", "V-1", "AT")], [install_row("u1", "AT")])
    empty = {**CALIBRATION, "readings": [{"unit": "C"}]}
    with pytest.raises(ValidationFailed):
        r.plan(w, CTX, [action("calibrate", old_serial="V-1", parameter="AT",
                               calibration=empty)], [])


@pytest.mark.req("SEN-4")
def test_cleaning_and_repair_are_notes_and_change_nothing():
    w = world([installed("u1", "V-1", "AT")], [install_row("u1", "AT")])
    before = dict(w.units["u1"])
    plan = r.plan(w, CTX, [action("clean", "a1", old_serial="V-1"),
                           action("repair", "a2", old_serial="V-1")], [])
    assert ops(plan) == ["remember", "remember"]
    assert w.units["u1"] == before


def test_a_later_action_can_use_what_an_earlier_one_did():
    w = world([installed("u1", "V-1", "AT"), unit("u2", "V-2")], [install_row("u1", "AT")])
    plan = r.plan(w, CTX, [
        action("replace", "a1", old_serial="V-1", new_serial="V-2", removal_reason="faulty"),
        action("calibrate", "a2", old_serial="V-2", parameter="AT", calibration=CALIBRATION),
    ], [])
    assert ops(plan) == ["remove", "install", "remember", "calibrate", "remember"]
    assert w.units["u2"]["last_calibrated_at"] == AT


# --- Applying again, changing, removing (TRD §3.2.3 items 2 and 3) ------------------------------


def applied_once(units, installations, actions):
    w = world(units, installations)
    first = r.plan(w, CTX, actions, [])
    return w, first, rows(first)


@pytest.mark.req("SEN-4")
def test_an_unchanged_action_is_skipped_so_a_second_save_writes_nothing():
    acts = [action("install", new_serial="V-2", parameter="AT")]
    w, _, applications = applied_once([unit("u2", "V-2")], [], acts)
    again = r.plan(w, CTX, [{**acts[0], "note": "reworded"}], applications)
    assert again.empty and again.applied_ids == [] and again.reversed_ids == []


@pytest.mark.req("SEN-4")
def test_a_changed_action_is_undone_exactly_and_applied_again():
    units = [unit("u2", "V-2"), unit("u3", "V-3")]
    acts = [action("install", new_serial="V-2", parameter="AT")]
    w, _, applications = applied_once(units, [], acts)
    fixed = [action("install", new_serial="V-3", parameter="AT")]  # a corrected serial
    plan = r.plan(w, CTX, fixed, applications)
    assert ops(plan) == ["restore_unit", "undo_installation", "forget", "install", "remember"]
    assert plan.reversed_ids == ["a1"] and plan.applied_ids == ["a1"]
    restore = plan.steps[0].data["changes"]
    assert restore["status"] == "in_stock" and restore["current_station_id"] is None
    assert w.units["u2"]["status"] == "in_stock" and w.units["u2"]["current_parameter"] is None
    assert w.units["u3"]["status"] == "installed" and w.units["u3"]["current_parameter"] == "AT"


@pytest.mark.req("SEN-4")
def test_a_removed_action_is_undone_and_nothing_is_applied_in_its_place():
    acts = [action("remove", old_serial="V-1", removal_reason="faulty")]
    w, _, applications = applied_once([installed("u1", "V-1", "AT")], [install_row("u1", "AT")],
                                      acts)
    assert w.units["u1"]["status"] == "in_repair"
    plan = r.plan(w, CTX, [], applications)
    assert ops(plan) == ["restore_unit", "reopen", "forget"]
    assert w.units["u1"]["status"] == "installed" and w.units["u1"]["current_parameter"] == "AT"
    assert "u1" in w.installs  # the installation is open again


@pytest.mark.req("SEN-4")
def test_an_action_that_created_a_unit_takes_it_away_again():
    acts = [action("install", new_serial="V-NEW", parameter="AT", sensor_model_id="m1")]
    w, _, applications = applied_once([], [], acts)
    plan = r.plan(w, CTX, [], applications)
    assert ops(plan) == ["undo_create", "undo_installation", "forget"]
    assert w.units == {}


@pytest.mark.req("SEN-4")
def test_changing_an_earlier_action_undoes_the_ones_after_it_and_applies_them_again():
    units = [installed("u1", "V-1", "AT"), unit("u2", "V-2"), unit("u3", "V-3")]
    acts = [action("replace", "a1", old_serial="V-1", new_serial="V-2", removal_reason="faulty"),
            action("calibrate", "a2", old_serial="V-2", parameter="AT", calibration=CALIBRATION)]
    w, _, applications = applied_once(units, [install_row("u1", "AT")], acts)
    corrected = [{**acts[0], "new_serial": "V-3"}, acts[1]]  # the wrong serial was typed
    corrected[1] = {**acts[1], "old_serial": "V-3"}  # ... and so the calibration followed it
    plan = r.plan(w, CTX, corrected, applications)
    assert plan.reversed_ids == ["a2", "a1"]  # newest first
    assert plan.applied_ids == ["a1", "a2"]
    assert w.units["u2"]["status"] == "in_stock" and w.units["u2"]["last_calibrated_at"] is None
    assert w.units["u3"]["status"] == "installed" and w.units["u3"]["last_calibrated_at"] == AT
    assert w.units["u1"]["status"] == "in_repair"


@pytest.mark.req("SEN-4")
def test_actions_before_the_one_that_changed_are_left_alone():
    units = [installed("u1", "V-1", "AT"), installed("u4", "V-4", "RH"), unit("u2", "V-2")]
    acts = [action("calibrate", "a1", old_serial="V-4", parameter="RH", calibration=CALIBRATION),
            action("replace", "a2", old_serial="V-1", new_serial="V-2", removal_reason="faulty")]
    w, _, applications = applied_once(units, [install_row("u1", "AT", "i1"),
                                              install_row("u4", "RH", "i4")], acts)
    plan = r.plan(w, CTX, [acts[0], {**acts[1], "removal_reason": "retired"}], applications)
    assert plan.reversed_ids == ["a2"] and plan.applied_ids == ["a2"]
    assert w.units["u4"]["last_calibrated_at"] == AT  # a1 was not undone
    assert w.units["u1"]["status"] == "retired"


@pytest.mark.req("SEN-4")
def test_a_new_action_is_applied_after_the_ones_already_applied():
    acts = [action("install", "a1", new_serial="V-2", parameter="AT")]
    w, _, applications = applied_once([unit("u2", "V-2"), unit("u3", "V-3")], [], acts)
    more = [*acts, action("install", "a2", new_serial="V-3", parameter="RH")]
    plan = r.plan(w, CTX, more, applications)
    assert plan.reversed_ids == [] and plan.applied_ids == ["a2"]


# --- Refusing a correction when something moved on (TRD §3.2.3 item 3) --------------------------


@pytest.mark.req("SEN-4")
def test_a_correction_is_refused_when_the_unit_was_changed_since():
    acts = [action("install", new_serial="V-2", parameter="AT")]
    w, _, applications = applied_once([unit("u2", "V-2")], [], acts)
    w.units["u2"]["version"] += 1  # a later visit, or an admin, touched it
    with pytest.raises(r.SensorChangedLater) as e:
        r.plan(w, CTX, [], applications)
    assert e.value.extra["action_id"] == "a1" and e.value.extra["serial"] == "V-2"
    assert e.value.status == 409


@pytest.mark.req("SEN-4")
def test_undoing_a_removal_is_refused_when_the_parameter_was_taken_meanwhile():
    acts = [action("remove", old_serial="V-1", removal_reason="faulty")]
    w, _, applications = applied_once([installed("u1", "V-1", "AT"), unit("u5", "V-5")],
                                      [install_row("u1", "AT")], acts)
    # someone installs another unit on the same parameter afterwards (a manual install bumps u5)
    w.units["u5"].update(status="installed", current_station_id="st1", current_parameter="AT")
    with pytest.raises(r.SensorChangedLater):
        r.plan(w, CTX, [], applications)


@pytest.mark.req("SEN-4")
def test_a_refusal_names_the_action_and_nothing_is_planned():
    units = [installed("u1", "V-1", "AT"), unit("u2", "V-2")]
    acts = [action("replace", "a1", old_serial="V-1", new_serial="V-2", removal_reason="faulty")]
    w, _, applications = applied_once(units, [install_row("u1", "AT")], acts)
    w.units["u1"]["version"] += 3
    result: r.Plan | None = None
    with pytest.raises(r.SensorChangedLater):
        result = r.plan(w, CTX, [{**acts[0], "removal_reason": "retired"}], applications)
    assert result is None


# --- The hash ----------------------------------------------------------------------------------


@pytest.mark.req("SEN-4")
def test_the_hash_ignores_the_note_and_notices_everything_that_decides_the_effects():
    base = action("replace", old_serial="V-1", new_serial="V-2", parameter="AT",
                  removal_reason="faulty")
    assert r.action_hash({**base, "note": "x"}) == r.action_hash(base)
    for change in ({"new_serial": "V-3"}, {"old_serial": "V-9"}, {"parameter": "RH"},
                   {"removal_reason": "retired"}, {"action": "install"},
                   {"sensor_model_id": "m1"}, {"calibration": CALIBRATION}):
        assert r.action_hash({**base, **change}) != r.action_hash(base), change


def test_serials_come_from_both_fields():
    assert r.serials_in([action("replace", old_serial="A", new_serial="B"),
                         action("clean", old_serial="C"), action("clean")]) == {"A", "B", "C"}
