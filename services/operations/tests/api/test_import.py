"""`POST /api/v1/stations/import` (STN-8; TP "Station import bad-rows fixture")."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mms_common.events import Actor
from mms_common.testing.seed import ORG_A, ORG_B

from app.events.publish import Emitter
from app.jobs import seed_data, station_import
from tests.conftest import station_body

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


async def existing(ops) -> None:
    """The fixture's last station row names a station that already exists."""
    await ops.station(code="TT-OLD-009", owner_org_id=ORG_B, country="TT",
                      time_zone="America/Port_of_Spain")


def files() -> dict[str, tuple[str, bytes, str]]:
    return {
        "stations": ("stations.csv", (FIXTURES / "stations_bad_rows.csv").read_bytes(), "text/csv"),
        "sensors": ("sensors.csv", (FIXTURES / "sensors_bad_rows.csv").read_bytes(), "text/csv"),
    }


async def test_a_dry_run_reports_and_writes_nothing(ops):
    await existing(ops)
    before = len(await ops.outbox())
    response = await ops.http.post("/api/v1/stations/import", files=files(),
                                   headers=ops.bearer("admin"))
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["dry_run"] is True
    assert (report["stations_created"], report["sensors_created"], report["models_created"]) == (
        2, 4, 3
    )
    assert len(report["errors"]) == 15  # 8 station and 7 sensor problems
    assert report["errors"][0] == {"sheet": "Stations", "row": 4, "column": "code",
                                   "message": "code is required"}
    assert await ops.db["stations"].count_documents({}) == 1
    assert len(await ops.outbox()) == before


@pytest.mark.req("STN-8")
async def test_the_valid_rows_are_imported_with_their_events(ops):
    await existing(ops)
    response = await ops.http.post("/api/v1/stations/import?dry_run=false", files=files(),
                                   headers=ops.bearer("admin"))
    assert response.status_code == 200, response.text
    report = response.json()
    assert (report["stations_created"], report["sensors_created"], report["models_created"]) == (
        2, 4, 3
    )
    stations = (await ops.http.get("/api/v1/stations", headers=ops.bearer("client_a1"))).json()
    assert [s["code"] for s in stations["items"]] == ["JM-KIN-001", "JM-MBJ-002"]
    kingston = (await ops.http.get(f"/api/v1/stations/{stations['items'][0]['id']}",
                                   headers=ops.bearer("tech1"))).json()
    assert [(u["parameter"], u["serial"]) for u in kingston["installed"]] == [
        (None, "B-1"), ("AT", "V-1"), ("RH", "V-2"),
    ]
    v1 = next(u for u in kingston["installed"] if u["serial"] == "V-1")
    assert v1["calibration_due_at"] == "2027-01-10T05:00:00Z"  # local midnight + 365 days

    types = [e.type for e in await ops.outbox()]
    assert types.count("sensor_model.created") == 3
    assert types.count("station.created") == 3
    assert types.count("sensor_unit.created") == 4
    assert types.count("sensor.installed") == 4
    created = await ops.outbox("station.created")
    assert [e.data["via"] for e in created] == ["api", "import", "import"]

    again = (await ops.http.post("/api/v1/stations/import?dry_run=false", files=files(),
                                 headers=ops.bearer("admin"))).json()
    assert again["stations_created"] == 0
    assert {(p["sheet"], p["row"]) for p in again["skipped"]} >= {("Stations", 2),
                                                                   ("Stations", 3)}


async def test_unreadable_and_oversized_files_are_refused(ops):
    pdf = await ops.http.post("/api/v1/stations/import",
                              files={"stations": ("s.pdf", b"%PDF-1.7", "application/pdf")},
                              headers=ops.bearer("admin"))
    assert pdf.status_code == 422 and pdf.json()["code"] == "unreadable_file"
    big = await ops.http.post(
        "/api/v1/stations/import",
        files={"stations": ("s.csv", b"x" * (10 * 1024 * 1024 + 1), "text/csv")},
        headers=ops.bearer("admin"),
    )
    assert big.status_code == 422 and big.json()["code"] == "file_too_large"


async def test_the_demo_seed_imports_cleanly_and_only_once(ops):
    db, client = ops.app.state.db, ops.app.state.mongo
    emitter = Emitter(db, ops.clock, Actor(name="test"), None)
    first = await station_import.run(client, db, ops.clock, emitter, seed_data.tables(),
                                     dry_run=False, by=None)
    assert first.errors == [] and first.stations_created == 5 and first.sensors_created == 16
    second = await station_import.run(client, db, ops.clock, emitter, seed_data.tables(),
                                      dry_run=False, by=None)
    assert second.stations_created == 0 and len(second.skipped) == 5 + 16


# --- The existing system's site export (decision W5-8) -----------------------------------------

ENT_A = "ENT" + "a" * 32


def site_export() -> bytes:
    """A made-up site with two devices (the repo is public)."""
    devices = [
        {"name": name, "longname": f"{name.title()} Station", "id": f"DEV{n:032x}",
         "lat": 18.0 + n / 100, "lon": -77.0, "timezone": "America/Jamaica",
         "params": [{"base": "RAIN", "param": "RAIN"}, {"base": "BV", "param": "BV"}]}
        for n, name in ((1, "HILLTOP"), (2, "RIVERSIDE"))
    ]
    site = {"type": "site", "id": "SITE" + "1" * 32, "name": "SITE ONE", "entity": ENT_A,
            "enabled": True, "devices": devices}
    return json.dumps([site]).encode()


@pytest.mark.req("STN-8")
async def test_the_site_export_imports_each_device_once(ops):
    await ops.db["organizations"].update_one({"_id": ORG_A}, {"$set": {"external_id": ENT_A}})
    upload = {"stations": ("sites.json", site_export(), "application/json")}
    response = await ops.http.post("/api/v1/stations/import?dry_run=false", files=upload,
                                   headers=ops.bearer("admin"))
    assert response.status_code == 200, response.text
    assert (response.json()["stations_created"], response.json()["errors"]) == (2, [])
    found = (await ops.http.get("/api/v1/stations", params={"q": f"DEV{2:032x}"},
                                headers=ops.bearer("client_a1"))).json()
    assert [(s["code"], s["external_id"], s["country"]) for s in found["items"]] == [
        ("RIVERSIDE", f"DEV{2:032x}", "JM"),
    ]
    again = await ops.http.post("/api/v1/stations/import?dry_run=false", files=upload,
                                headers=ops.bearer("admin"))
    assert again.json()["stations_created"] == 0
    assert len(again.json()["skipped"]) == 2


async def test_an_external_id_belongs_to_one_station(ops):
    await ops.station(code="ONE-001", external_id="DEV-1")
    response = await ops.http.post(
        "/api/v1/stations", json=station_body(code="TWO-002", external_id="DEV-1"),
        headers=ops.bearer("tech1"),
    )
    assert (response.status_code, response.json()["code"]) == (409, "external_id_taken")
