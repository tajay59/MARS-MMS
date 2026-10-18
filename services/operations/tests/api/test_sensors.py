"""Sensor models, units, installations and calibrations (SEN-1 to SEN-3, CAL-1, CAL-3, CAL-4,
CAL-6, STN-4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mms_common.testing.leak import find_leaks
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@pytest.mark.req("SEN-1")
async def test_the_model_catalogue(ops):
    model = await ops.model()
    assert model["parameters"] == ["AT", "RH"] and model["default_calibration_interval_days"] == 365
    duplicate = await ops.http.post(
        "/api/v1/sensor-models",
        json={"kind": "sensor", "manufacturer": "vaisala ", "model": "hmp155"},
        headers=ops.bearer("admin"),
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "model_taken"
    await ops.model(kind="battery", manufacturer="Trojan", model="SCS200", parameters=[],
                    default_calibration_interval_days=None)
    listed = await ops.http.get("/api/v1/sensor-models?kind=sensor", headers=ops.bearer("viewer"))
    assert [m["model"] for m in listed.json()["items"]] == ["HMP155"]
    searched = await ops.http.get("/api/v1/sensor-models?q=troj", headers=ops.bearer("viewer"))
    assert [m["model"] for m in searched.json()["items"]] == ["SCS200"]
    first = (await ops.outbox("sensor_model.created"))[0]
    assert first.key == model["id"] and first.org_id is None


@pytest.mark.req("SEN-2")
async def test_units_by_serial(ops):
    model = await ops.model()
    unit = await ops.unit(model["id"], " SN-001 ", notes="Spare from 2024")
    assert unit["serial"] == "SN-001" and unit["status"] == "in_stock"
    assert unit["model"]["model"] == "HMP155" and unit["station"] is None
    again = await ops.http.post("/api/v1/sensor-units",
                                json={"model_id": model["id"], "serial": "SN-001"},
                                headers=ops.bearer("tech1"))
    assert again.status_code == 409 and again.json()["code"] == "serial_taken"
    [event] = await ops.outbox("sensor_unit.created")
    assert event.key == unit["id"]  # in stock: keyed by the unit itself


@pytest.mark.req("CAL-3")
async def test_due_date_follows_the_override_or_the_model_default(ops):
    model = await ops.model()
    last = NOW - timedelta(days=340)  # due in 25 days
    unit = await ops.unit(model["id"], last_calibrated_at=iso(last))
    assert unit["calibration_due_at"] == iso(last + timedelta(days=365))
    assert unit["effective_interval_days"] == 365 and unit["due_state"] == "due_soon"

    path = f"/api/v1/sensor-units/{unit['id']}"
    override = await ops.http.patch(path, json={"version": 1, "calibration_interval_days": 180},
                                    headers=ops.bearer("tech1"))
    body = override.json()
    assert body["calibration_due_at"] == iso(last + timedelta(days=180))
    assert body["due_state"] == "overdue"
    back = await ops.http.patch(path, json={"version": 2, "calibration_interval_days": None},
                                headers=ops.bearer("tech1"))
    assert back.json()["calibration_due_at"] == iso(last + timedelta(days=365))


@pytest.mark.req("CAL-3")
async def test_a_new_model_default_moves_the_units_that_follow_it(ops):
    model = await ops.model()
    last = NOW - timedelta(days=10)
    follows = await ops.unit(model["id"], "A", last_calibrated_at=iso(last))
    own = await ops.unit(model["id"], "B", last_calibrated_at=iso(last),
                         calibration_interval_days=90)
    response = await ops.http.patch(
        f"/api/v1/sensor-models/{model['id']}",
        json={"version": 1, "default_calibration_interval_days": 730},
        headers=ops.bearer("admin"),
    )
    assert response.status_code == 200, response.text
    a = (await ops.http.get(f"/api/v1/sensor-units/{follows['id']}",
                            headers=ops.bearer("tech1"))).json()
    b = (await ops.http.get(f"/api/v1/sensor-units/{own['id']}",
                            headers=ops.bearer("tech1"))).json()
    assert a["calibration_due_at"] == iso(last + timedelta(days=730))
    assert b["calibration_due_at"] == iso(last + timedelta(days=90))
    updates = await ops.outbox("sensor_unit.updated")
    assert [e.data["unit_id"] for e in updates] == [follows["id"]]


@pytest.mark.req("SEN-3")
async def test_install_and_remove_write_the_history(ops):
    station = await ops.station()
    model = await ops.model()
    unit = await ops.unit(model["id"])
    installed_at = NOW - timedelta(days=30)
    response = await ops.install(unit, station, "AT", at=iso(installed_at))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "installed" and body["parameter"] == "AT"
    assert body["station"] == {"id": station["id"], "code": "JM-KIN-001",
                               "name": "Kingston Harbour"}
    [installed] = await ops.outbox("sensor.installed")
    assert installed.key == station["id"] and installed.org_id == ORG_A
    assert installed.data["unit_status"] == "installed"
    assert installed.aggregate_version == body["version"]

    detail = (await ops.http.get(f"/api/v1/stations/{station['id']}",
                                 headers=ops.bearer("client_a1"))).json()
    [row] = detail["installed"]
    assert row["serial"] == "S-1" and row["installed_at"] == iso(installed_at)
    assert row["model"]["manufacturer"] == "Vaisala"

    removed = await ops.http.post(
        f"/api/v1/sensor-units/{unit['id']}/remove",
        json={"version": body["version"], "reason": "Drifting", "status": "in_repair"},
        headers=ops.bearer("tech2"),
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "in_repair" and removed.json()["station"] is None
    [event] = await ops.outbox("sensor.removed")
    assert event.data["reason"] == "Drifting" and event.key == station["id"]

    history = (await ops.http.get(f"/api/v1/stations/{station['id']}/installations",
                                  headers=ops.bearer("client_a1"))).json()
    assert len(history) == 1
    assert history[0]["removed_at"] == iso(NOW) and history[0]["removal_reason"] == "Drifting"
    unit_detail = (await ops.http.get(f"/api/v1/sensor-units/{unit['id']}",
                                      headers=ops.bearer("viewer"))).json()
    assert unit_detail["installations"][0]["station_code"] == "JM-KIN-001"


async def test_install_rules(ops):
    station = await ops.station()
    model = await ops.model()
    first = await ops.unit(model["id"], "A")
    second = await ops.unit(model["id"], "B")
    assert (await ops.install(first, station, "AT")).status_code == 200
    taken = await ops.install(second, station, "AT")
    assert taken.status_code == 409 and taken.json()["code"] == "parameter_taken"
    missing = await ops.install(second, station, "BP")
    assert missing.status_code == 422
    future = await ops.install(second, station, "RH", at=iso(NOW + timedelta(days=1)))
    assert future.status_code == 422
    twice = await ops.http.post(
        f"/api/v1/sensor-units/{first['id']}/install",
        json={"version": 2, "station_id": station["id"], "parameter": "RH"},
        headers=ops.bearer("tech1"),
    )
    assert twice.status_code == 409 and twice.json()["code"] == "unit_installed"
    status_edit = await ops.http.patch(f"/api/v1/sensor-units/{first['id']}",
                                       json={"version": 2, "status": "retired"},
                                       headers=ops.bearer("tech1"))
    assert status_edit.status_code == 409
    not_installed = await ops.http.post(
        f"/api/v1/sensor-units/{second['id']}/remove",
        json={"version": 1, "reason": "x"}, headers=ops.bearer("tech1"),
    )
    assert not_installed.status_code == 409


async def test_a_parameter_in_use_stays_on_the_station(ops):
    station = await ops.station()
    model = await ops.model()
    await ops.install(await ops.unit(model["id"]), station, "AT")
    response = await ops.http.patch(f"/api/v1/stations/{station['id']}",
                                    json={"version": 1, "parameters": ["RH"]},
                                    headers=ops.bearer("admin"))
    assert response.status_code == 409 and response.json()["code"] == "parameter_in_use"


@pytest.mark.req("STN-6")
async def test_clients_see_units_only_at_their_stations(ops):
    station = await ops.station()
    model = await ops.model()
    await ops.install(await ops.unit(model["id"]), station, "AT")
    own = await ops.http.get(f"/api/v1/stations/{station['id']}",
                             headers=ops.bearer("client_a1"))
    assert len(own.json()["installed"]) == 1
    assert find_leaks(own.json(), own_ids=frozenset({SEED_USERS["client_a1"].id, ORG_A})) == []
    other = await ops.http.get(f"/api/v1/stations/{station['id']}",
                               headers=ops.bearer("client_b1"))
    assert other.status_code == 404


@pytest.mark.req("CAL-1")
async def test_record_a_lab_calibration(ops):
    station = await ops.station()
    model = await ops.model()
    unit = await ops.unit(model["id"])
    installed = (await ops.install(unit, station, "AT")).json()
    at = NOW - timedelta(days=2)
    response = await ops.http.post("/api/v1/calibrations", json={
        "sensor_unit_id": unit["id"], "at": iso(at), "method": "lab", "result": "adjusted",
        "reference_instrument": {"model": "Fluke 1524", "serial": "R-1",
                                 "certificate_due": "2027-01-01"},
        "readings": [{"reference": 20.0, "before": 20.4, "after": 20.05, "unit": "°C"}],
    }, headers=ops.bearer("tech1"))
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["performed_by"] == "Tech 1" and record["station_id"] == station["id"]
    assert record["readings"][0]["before"] == 20.4

    after = (await ops.http.get(f"/api/v1/sensor-units/{unit['id']}",
                                headers=ops.bearer("tech1"))).json()
    assert after["last_calibrated_at"] == iso(at)
    assert after["last_calibration_result"] == "adjusted"
    assert after["calibration_due_at"] == iso(at + timedelta(days=365))
    assert after["version"] == installed["version"] + 1
    [event] = await ops.outbox("calibration.recorded")
    assert event.key == station["id"] and event.org_id == ORG_A
    assert event.data["due_at"] is not None and event.aggregate_version == 1

    listed = (await ops.http.get(f"/api/v1/calibrations?sensor_unit_id={unit['id']}",
                                 headers=ops.bearer("viewer"))).json()
    assert [c["id"] for c in listed["items"]] == [record["id"]]


@pytest.mark.req("CAL-6")
async def test_a_failed_calibration_flags_the_unit(ops):
    model = await ops.model()
    unit = await ops.unit(model["id"])
    response = await ops.http.post("/api/v1/calibrations", json={
        "sensor_unit_id": unit["id"], "at": iso(NOW), "result": "fail", "performed_by": "Lab X",
    }, headers=ops.bearer("admin"))
    assert response.status_code == 201
    assert response.json()["performed_by"] == "Lab X"
    after = (await ops.http.get(f"/api/v1/sensor-units/{unit['id']}",
                                headers=ops.bearer("admin"))).json()
    assert after["flags"] == ["calibration_failed"]


@pytest.mark.req("CAL-4")
async def test_the_calibration_due_list(ops):
    jamaica = await ops.station(code="A-1")
    trinidad = await ops.station(code="B-1", owner_org_id=ORG_B, country="TT",
                                 time_zone="America/Port_of_Spain")
    model = await ops.model()
    overdue = await ops.unit(model["id"], "OVER", last_calibrated_at=iso(NOW - timedelta(days=400)))
    soon = await ops.unit(model["id"], "SOON", last_calibrated_at=iso(NOW - timedelta(days=350)))
    await ops.unit(model["id"], "LATER", last_calibrated_at=iso(NOW - timedelta(days=10)))
    await ops.unit(model["id"], "NEVER")
    await ops.install(overdue, jamaica, "AT")
    await ops.install(soon, trinidad, "AT")

    async def serials(query: str = "") -> list[tuple[str, str]]:
        response = await ops.http.get(f"/api/v1/calibrations/due{query}",
                                      headers=ops.bearer("viewer"))
        assert response.status_code == 200, response.text
        return [(u["serial"], u["due_state"]) for u in response.json()["items"]]

    assert await serials() == [("OVER", "overdue"), ("SOON", "due_soon")]
    assert await serials("?country=TT") == [("SOON", "due_soon")]
    assert await serials(f"?org_id={ORG_A}") == [("OVER", "overdue")]
    assert await serials(f"?station_id={trinidad['id']}") == [("SOON", "due_soon")]
    assert await serials("?within_days=0") == [("OVER", "overdue")]
    assert len(await serials("?within_days=365")) == 3

    stations = (await ops.http.get("/api/v1/stations", headers=ops.bearer("tech1"))).json()
    due = {s["code"]: s["next_calibration_due_at"] for s in stations["items"]}
    assert due["A-1"] == iso(NOW - timedelta(days=400) + timedelta(days=365))


async def test_a_unit_found_in_the_field_is_corrected_in_review(ops):
    model = await ops.model()
    unit = await ops.unit(model["id"], "SN-0O1")
    await ops.db["sensor_units"].update_one({"_id": unit["id"]}, {"$set": {"needs_review": True}})
    flagged = (await ops.http.get("/api/v1/sensor-units?needs_review=true",
                                  headers=ops.bearer("tech1"))).json()
    assert [u["serial"] for u in flagged["items"]] == ["SN-0O1"]
    fixed = await ops.http.patch(f"/api/v1/sensor-units/{unit['id']}",
                                 json={"version": 1, "serial": "SN-001", "needs_review": False},
                                 headers=ops.bearer("admin"))
    assert fixed.status_code == 200 and fixed.json()["needs_review"] is False
    [event] = await ops.outbox("sensor_unit.updated")
    assert event.data["changed_fields"] == ["needs_review", "serial"]
