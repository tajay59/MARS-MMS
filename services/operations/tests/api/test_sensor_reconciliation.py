"""Sensor actions in a visit's work record reach the inventory, and corrections follow exactly
(PRD SEN-4, SEN-5, CAL-1, CFG-4; TRD §3.2.3; W11-5 to W11-9), over the real app and database."""

from __future__ import annotations

from typing import Any

import pytest
from mms_common.ids import new_id

from tests.api.test_visits import TECH1, a_request, move, plan
from tests.api.test_work_records import put, work_of


def at_station(unit: dict[str, Any]) -> str | None:
    return unit["station"]["id"] if unit["station"] else None


async def inventory(ops, unit_id: str) -> dict[str, Any]:
    r = await ops.http.get(f"/api/v1/sensor-units/{unit_id}", headers=ops.bearer("admin"))
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


async def a_station_with_a_unit(ops, serial: str = "V-1", parameter: str = "AT"):
    """A started visit at one station that has a unit installed, and the model."""
    request, stations = await a_request(ops, stations=1)
    model = await ops.model()
    unit = await ops.unit(model["id"], serial)
    assert (await ops.install(unit, stations[0], parameter)).status_code == 200
    visit = (await plan(ops, "tech1", request, stations)).json()
    assert (await move(ops, "tech1", visit["id"], "start")).status_code == 200
    return visit, stations[0], model, unit


def replace(old: str, new: str, id_: str | None = None, **fields: Any) -> dict[str, Any]:
    return {"id": id_ or new_id(), "action": "replace", "parameter": "AT", "old_serial": old,
            "new_serial": new, "removal_reason": "faulty", **fields}


async def end(ops, visit_id: str, who: str = "tech1"):
    return await move(ops, who, visit_id, "end", additional_visit_required=False)


async def by_serial(ops, serial: str) -> dict[str, Any]:
    r = await ops.http.get("/api/v1/sensor-units", params={"q": serial},
                           headers=ops.bearer("admin"))
    [found] = [u for u in r.json()["items"] if u["serial"] == serial]
    return await inventory(ops, found["id"])


# --- Applying -----------------------------------------------------------------------------------


@pytest.mark.req("SEN-4")
async def test_a_swap_reaches_the_inventory_when_the_visit_ends_not_before(ops):
    visit, station, model, old = await a_station_with_a_unit(ops)
    new = await ops.unit(model["id"], "V-2")
    saved = await put(ops, "tech1", visit["id"], station["id"], 0,
                      sensor_actions=[replace("V-1", "V-2")])
    assert saved.status_code == 200, saved.text
    assert (await inventory(ops, old["id"]))["status"] == "installed"  # a draft until the end
    assert await ops.outbox("sensor.removed") == []

    assert (await end(ops, visit["id"])).status_code == 200
    gone, came = await inventory(ops, old["id"]), await inventory(ops, new["id"])
    assert (gone["status"], at_station(gone)) == ("in_repair", None)
    assert (came["status"], came["parameter"]) == ("installed", "AT")
    assert at_station(came) == station["id"] and came["needs_review"] is False

    [removed] = await ops.outbox("sensor.removed")
    [installed_now] = [e for e in await ops.outbox("sensor.installed") if e.data["serial"] == "V-2"]
    assert removed.data["visit_id"] == visit["id"] and removed.data["unit_status"] == "in_repair"
    assert installed_now.data["action_id"] == saved.json()["stations"][0]["work"][
        "sensor_actions"][0]["id"]
    rows = await ops.db["sensor_applications"].find({"visit_id": visit["id"]}).to_list(None)
    assert len(rows) == 1 and rows[0]["station_id"] == station["id"]


@pytest.mark.req("SEN-4")
async def test_saving_the_same_record_after_the_end_changes_nothing_more(ops):
    visit, station, model, _ = await a_station_with_a_unit(ops)
    await ops.unit(model["id"], "V-2")
    actions = [replace("V-1", "V-2")]
    await put(ops, "tech1", visit["id"], station["id"], 0, sensor_actions=actions)
    await end(ops, visit["id"])
    before = len(await ops.outbox())
    again = await put(ops, "tech1", visit["id"], station["id"], 1, sensor_actions=actions,
                      notes="Only a note changed")
    assert again.status_code == 200, again.text
    kinds = [e.type for e in (await ops.outbox())[before:]]
    assert kinds == ["visit.work_updated"]  # the note moved; the inventory did not


@pytest.mark.req("SEN-4")
async def test_a_removal_sends_the_unit_where_the_reason_says(ops):
    visit, station, _, old = await a_station_with_a_unit(ops)
    action = {"id": new_id(), "action": "remove", "parameter": "AT", "old_serial": "V-1",
              "removal_reason": "retired"}
    await put(ops, "tech1", visit["id"], station["id"], 0, sensor_actions=[action])
    await end(ops, visit["id"])
    assert (await inventory(ops, old["id"]))["status"] == "retired"
    history = (await inventory(ops, old["id"]))["installations"]
    assert history[0]["removed_at"] is not None


@pytest.mark.req("SEN-5")
async def test_an_unknown_serial_is_added_once_flagged_and_installed(ops):
    visit, station, model, _ = await a_station_with_a_unit(ops)
    action = replace("V-1", "V-NEW", sensor_model_id=model["id"])
    await put(ops, "tech1", visit["id"], station["id"], 0, sensor_actions=[action])
    await end(ops, visit["id"])
    made = await by_serial(ops, "V-NEW")
    assert made["needs_review"] is True and made["status"] == "installed"
    flagged = (await ops.http.get("/api/v1/sensor-units", params={"needs_review": "true"},
                                  headers=ops.bearer("admin"))).json()["items"]
    assert [u["serial"] for u in flagged] == ["V-NEW"]
    created = await ops.outbox("sensor_unit.created")
    assert [e.data["via"] for e in created if e.data["serial"] == "V-NEW"] == ["visit"]
    # Saving again does not add a second one
    await put(ops, "tech1", visit["id"], station["id"], 1, sensor_actions=[action], notes="n")
    units = (await ops.http.get("/api/v1/sensor-units", params={"q": "V-NEW"},
                                headers=ops.bearer("admin"))).json()["items"]
    assert len(units) == 1


@pytest.mark.req("SEN-5")
async def test_an_unknown_serial_without_a_model_stops_the_end_and_nothing_moves(ops):
    visit, station, _, old = await a_station_with_a_unit(ops)
    await put(ops, "tech1", visit["id"], station["id"], 0,
              sensor_actions=[replace("V-1", "V-GHOST")])
    refused = await end(ops, visit["id"])
    assert refused.status_code == 422 and refused.json()["code"] == "model_required"
    assert (await inventory(ops, old["id"]))["status"] == "installed"
    got = await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer("tech1"))
    assert got.json()["status"] == "started"  # the end was undone with the rest
    assert await ops.outbox("visit.ended") == []


@pytest.mark.req("SEN-4")
async def test_every_station_is_applied_in_the_one_transaction_that_ends_the_visit(ops):
    request, stations = await a_request(ops, stations=2)
    model = await ops.model()
    a, b = await ops.unit(model["id"], "A-1"), await ops.unit(model["id"], "B-1")
    assert (await ops.install(a, stations[0], "AT")).status_code == 200
    assert (await ops.install(b, stations[1], "AT")).status_code == 200
    visit = (await plan(ops, "tech1", request, stations)).json()
    await move(ops, "tech1", visit["id"], "start")
    good = {"id": new_id(), "action": "remove", "parameter": "AT", "old_serial": "A-1",
            "removal_reason": "faulty"}
    bad = {"id": new_id(), "action": "remove", "parameter": "AT", "old_serial": "NOPE"}
    await put(ops, "tech1", visit["id"], stations[0]["id"], 0, sensor_actions=[good])
    await put(ops, "tech1", visit["id"], stations[1]["id"], 0, sensor_actions=[bad])
    refused = await end(ops, visit["id"])
    assert refused.status_code == 422 and refused.json()["code"] == "unit_not_at_station"
    assert (await inventory(ops, a["id"]))["status"] == "installed"  # the good one waited too
    await put(ops, "tech1", visit["id"], stations[1]["id"], 1, sensor_actions=[])
    assert (await end(ops, visit["id"])).status_code == 200
    assert (await inventory(ops, a["id"]))["status"] == "in_repair"
    assert (await inventory(ops, b["id"]))["status"] == "installed"


# --- Correcting ---------------------------------------------------------------------------------


@pytest.mark.req("SEN-4")
async def test_a_corrected_serial_undoes_the_swap_exactly_and_applies_the_right_one(ops):
    visit, station, model, old = await a_station_with_a_unit(ops)
    wrong = await ops.unit(model["id"], "V-2")
    right = await ops.unit(model["id"], "V-3")
    before = await inventory(ops, wrong["id"])
    action_id = new_id()
    first = await put(ops, "tech1", visit["id"], station["id"], 0,
                      sensor_actions=[replace("V-1", "V-2", action_id)])
    await end(ops, visit["id"])
    assert (await inventory(ops, wrong["id"]))["status"] == "installed"

    fixed = await put(ops, "tech1", visit["id"], station["id"], 1,
                      sensor_actions=[replace("V-1", "V-3", action_id)])
    assert fixed.status_code == 200, fixed.text
    after = await inventory(ops, wrong["id"])
    assert (after["status"], at_station(after), after["parameter"]) == (
        before["status"], at_station(before), before["parameter"])
    assert after["installations"] == []  # the mistaken installation is gone, not just closed
    got = await inventory(ops, right["id"])
    assert (got["status"], at_station(got)) == ("installed", station["id"])
    assert (await inventory(ops, old["id"]))["status"] == "in_repair"
    swaps = [i for i in (await inventory(ops, old["id"]))["installations"]]
    assert len(swaps) == 1  # one swap in the history

    [reversed_] = await ops.outbox("sensor.application_reversed")
    assert reversed_.data["action_id"] == action_id and wrong["id"] in reversed_.data["unit_ids"]
    assert first.json()["stations"][0]["work"]["version"] == 1


@pytest.mark.req("SEN-4")
async def test_removing_the_action_puts_the_old_unit_back_as_it_was(ops):
    visit, station, model, old = await a_station_with_a_unit(ops)
    new = await ops.unit(model["id"], "V-2")
    original = await inventory(ops, old["id"])
    await put(ops, "tech1", visit["id"], station["id"], 0, sensor_actions=[replace("V-1", "V-2")])
    await end(ops, visit["id"])
    undone = await put(ops, "tech1", visit["id"], station["id"], 1, sensor_actions=[])
    assert undone.status_code == 200, undone.text
    back = await inventory(ops, old["id"])
    assert (back["status"], at_station(back), back["parameter"]) == (
        "installed", station["id"], "AT")
    assert [i["id"] for i in back["installations"]] == [i["id"] for i in original["installations"]]
    assert back["installations"][0]["removed_at"] is None  # the same installation, open again
    assert (await inventory(ops, new["id"]))["status"] == "in_stock"


@pytest.mark.req("SEN-4")
async def test_a_correction_is_refused_once_the_unit_was_changed_and_nothing_is_written(ops):
    visit, station, model, _ = await a_station_with_a_unit(ops)
    new = await ops.unit(model["id"], "V-2")
    other = await ops.unit(model["id"], "V-9")
    action_id = new_id()
    await put(ops, "tech1", visit["id"], station["id"], 0,
              sensor_actions=[replace("V-1", "V-2", action_id)])
    await end(ops, visit["id"])
    # An admin takes V-2 off by hand afterwards
    fresh = await inventory(ops, new["id"])
    removed = await ops.http.post(
        f"/api/v1/sensor-units/{new['id']}/remove", headers=ops.bearer("admin"),
        json={"version": fresh["version"], "status": "in_stock", "reason": "damaged"},
    )
    assert removed.status_code == 200, removed.text
    outbox_before = len(await ops.outbox())

    refused = await put(ops, "tech1", visit["id"], station["id"], 1,
                        sensor_actions=[replace("V-1", "V-9", action_id)], notes="Trying to fix it")
    assert refused.status_code == 409 and refused.json()["code"] == "sensor_changed_later"
    assert refused.json()["action_id"] == action_id and refused.json()["serial"] == "V-2"
    assert (await inventory(ops, other["id"]))["status"] == "in_stock"
    got = await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer("tech1"))
    record = work_of(got.json(), station["id"])
    assert record["version"] == 1 and record["notes"] is None  # not even the note was saved
    assert len(await ops.outbox()) == outbox_before


@pytest.mark.req("SEN-4")
async def test_changing_a_swap_also_redoes_the_calibration_that_followed_it(ops):
    visit, station, model, old = await a_station_with_a_unit(ops)
    wrong = await ops.unit(model["id"], "V-2")
    right = await ops.unit(model["id"], "V-3")
    swap_id, cal_id = new_id(), new_id()

    def calibrate(serial: str) -> dict[str, Any]:
        return {"id": cal_id, "action": "calibrate", "parameter": "AT", "old_serial": serial,
                "calibration": {"method": "field_check", "result": "pass",
                                "readings": [{"reference": 20.0, "before": 20.3, "after": 20.0,
                                              "unit": "C"}]}}

    await put(ops, "tech1", visit["id"], station["id"], 0,
              sensor_actions=[replace("V-1", "V-2", swap_id), calibrate("V-2")])
    await end(ops, visit["id"])
    listed = (await ops.http.get("/api/v1/calibrations", params={"sensor_unit_id": wrong["id"]},
                                 headers=ops.bearer("admin"))).json()["items"]
    assert len(listed) == 1 and listed[0]["visit_id"] == visit["id"]

    fixed = await put(ops, "tech1", visit["id"], station["id"], 1,
                      sensor_actions=[replace("V-1", "V-3", swap_id), calibrate("V-3")])
    assert fixed.status_code == 200, fixed.text
    assert (await ops.http.get("/api/v1/calibrations", params={"sensor_unit_id": wrong["id"]},
                               headers=ops.bearer("admin"))).json()["items"] == []
    mine = (await ops.http.get("/api/v1/calibrations", params={"sensor_unit_id": right["id"]},
                               headers=ops.bearer("admin"))).json()["items"]
    assert len(mine) == 1 and mine[0]["result"] == "pass"
    assert (await inventory(ops, wrong["id"]))["last_calibrated_at"] is None
    assert (await inventory(ops, right["id"]))["last_calibrated_at"] is not None
    [voided] = await ops.outbox("calibration.voided")
    assert voided.data["unit_id"] == wrong["id"] and voided.data["reason"]
    assert old["id"]  # the old unit is in repair throughout


@pytest.mark.req("CAL-6")
async def test_a_failed_field_calibration_flags_the_unit_and_a_correction_clears_it(ops):
    visit, station, _, unit = await a_station_with_a_unit(ops)
    cal_id = new_id()
    action = {"id": cal_id, "action": "calibrate", "parameter": "AT", "old_serial": "V-1",
              "calibration": {"method": "field_check", "result": "fail",
                              "readings": [{"reference": 20.0, "before": 23.0, "unit": "C"}]}}
    await put(ops, "tech1", visit["id"], station["id"], 0, sensor_actions=[action])
    await end(ops, visit["id"])
    assert "calibration_failed" in (await inventory(ops, unit["id"]))["flags"]
    passed = {**action, "calibration": {**action["calibration"], "result": "pass"}}
    await put(ops, "tech1", visit["id"], station["id"], 1, sensor_actions=[passed])
    flags = (await inventory(ops, unit["id"]))["flags"]
    assert "calibration_failed" not in flags


@pytest.mark.req("SEN-4")
async def test_cleaning_and_repair_are_notes_that_leave_the_inventory_alone(ops):
    visit, station, _, unit = await a_station_with_a_unit(ops)
    before = await inventory(ops, unit["id"])
    notes = [{"id": new_id(), "action": "clean", "old_serial": "V-1", "note": "Wiped the shield"},
             {"id": new_id(), "action": "repair", "old_serial": "V-1", "note": "New cable"}]
    await put(ops, "tech1", visit["id"], station["id"], 0, sensor_actions=notes)
    await end(ops, visit["id"])
    after = await inventory(ops, unit["id"])
    assert (after["status"], after["version"]) == (before["status"], before["version"])


# --- Configuration versions (CFG-4) -------------------------------------------------------------


@pytest.mark.req("CFG-4")
async def test_a_configuration_captured_in_the_visit_becomes_a_version_at_the_end_once(ops):
    visit, station, _, _ = await a_station_with_a_unit(ops)
    file_id = ops.media.add(f"config:{station['id']}", by="tech1", kind="config",
                            filename="logger.cr1", sha="ab" * 32)
    entry = {"id": new_id(), "files": [file_id], "notes": "Sampling every 10 minutes"}
    await put(ops, "tech1", visit["id"], station["id"], 0, config_versions=[entry])
    assert (await ops.http.get(f"/api/v1/stations/{station['id']}/config-versions",
                               headers=ops.bearer("tech1"))).json() == []
    assert (await end(ops, visit["id"])).status_code == 200
    versions = (await ops.http.get(f"/api/v1/stations/{station['id']}/config-versions",
                                   headers=ops.bearer("tech1"))).json()
    assert [(v["id"], v["version"], v["visit_id"]) for v in versions] == [
        (entry["id"], 1, visit["id"])]
    # Saving again does not make a second, and a change to a created one is refused
    same = await put(ops, "tech1", visit["id"], station["id"], 1, config_versions=[entry],
                     notes="more")
    assert same.status_code == 200
    other_file = ops.media.add(f"config:{station['id']}", by="tech1", kind="config",
                               filename="other.cr1", sha="cd" * 32)
    changed = await put(ops, "tech1", visit["id"], station["id"], 2,
                        config_versions=[{**entry, "files": [other_file]}])
    assert changed.status_code == 409 and changed.json()["code"] == "config_version_immutable"
    newer = await put(ops, "tech1", visit["id"], station["id"], 2, config_versions=[
        entry, {"id": new_id(), "files": [other_file], "notes": "Corrected"}])
    assert newer.status_code == 200, newer.text
    assert [v["version"] for v in (await ops.http.get(
        f"/api/v1/stations/{station['id']}/config-versions", headers=ops.bearer("tech1")
    )).json()] == [2, 1]


@pytest.mark.req("CFG-4")
async def test_a_file_still_being_checked_stops_the_end(ops):
    visit, station, _, _ = await a_station_with_a_unit(ops)
    waiting = ops.media.add(f"config:{station['id']}", by="tech1", kind="config",
                            filename="logger.cr1", status="processing")
    await put(ops, "tech1", visit["id"], station["id"], 0,
              config_versions=[{"id": new_id(), "files": [waiting]}])
    refused = await end(ops, visit["id"])
    assert refused.status_code in (409, 422), refused.text
    got = await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer("tech1"))
    assert got.json()["status"] == "started"
    assert TECH1  # (the owner is the uploader the file is checked against)
