"""Work records, W11 slice 1 (PRD VIS-7, VIS-8; ADR-18; rules 2 to 6), over the real app: the
template copied at start, the owner's whole-record save with `base_version`, who may and when,
no merge, and a client never seeing a record."""

from __future__ import annotations

from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from tests.api.test_visits import (
    TECH1,
    TECH2,
    a_request,
    move,
    plan,
    scheduled,
)

TEMPLATES = "/api/v1/checklist-templates"
ITEMS = [{"label": "Mast: guy wires, corrosion"}, {"label": "Battery voltage", "help": "Note it"}]


def url(visit_id: str, station_id: str) -> str:
    return f"/api/v1/visits/{visit_id}/stations/{station_id}/work"


async def put(ops, who: str, visit_id: str, station_id: str, base: int = 0, **record: Any):
    return await ops.http.put(
        url(visit_id, station_id), json={"base_version": base, **record},
        headers=ops.bearer(who),
    )


async def started(ops, **kw: Any):
    """A started visit of two stations, both owned by tech1."""
    visit, request, stations = await scheduled(ops, **kw)
    r = await move(ops, "tech1", visit["id"], "start")
    assert r.status_code == 200, r.text
    return r.json(), request, stations


async def template(ops, **fields: Any) -> dict[str, Any]:
    body = {"name": "Site visit", "station_type": "Synoptic", "items": ITEMS, **fields}
    r = await ops.http.post(TEMPLATES, json=body, headers=ops.bearer("admin"))
    assert r.status_code == 201, r.text
    data: dict[str, Any] = r.json()
    return data


def work_of(visit: dict[str, Any], station_id: str) -> dict[str, Any]:
    found = next(s for s in visit["stations"] if s["station_id"] == station_id)
    work: dict[str, Any] = found["work"]
    return work


async def read(ops, who: str, visit_id: str) -> dict[str, Any]:
    r = await ops.http.get(f"/api/v1/visits/{visit_id}", headers=ops.bearer(who))
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


# --- The template copy (VIS-8) ------------------------------------------------------------------


@pytest.mark.req("VIS-8")
async def test_starting_copies_the_station_template_and_later_edits_change_nothing(ops):
    made = await template(ops)
    visit, _, stations = await started(ops)
    work = work_of(visit, stations[0]["id"])
    assert work["version"] == 0 and work["updated_by"] is None
    assert [r["label"] for r in work["checklist"]] == [i["label"] for i in ITEMS]
    assert all(r["result"] is None and r["ad_hoc"] is False for r in work["checklist"])
    ids = [r["item_id"] for r in work["checklist"]]

    edit = await ops.http.patch(
        f"{TEMPLATES}/{made['id']}", headers=ops.bearer("admin"),
        json={"version": 1, "items": [{"label": "Something else entirely"}]},
    )
    assert edit.status_code == 200, edit.text
    again = work_of(await read(ops, "tech1", visit["id"]), stations[0]["id"])
    assert [r["item_id"] for r in again["checklist"]] == ids  # version 1 is what this visit has


@pytest.mark.req("VIS-8")
async def test_a_station_with_no_template_starts_with_an_empty_checklist(ops):
    visit, _, stations = await started(ops)
    assert work_of(visit, stations[0]["id"])["checklist"] == []


@pytest.mark.req("VIS-8")
async def test_a_visit_started_before_records_existed_copies_the_template_on_first_save(ops):
    await template(ops)
    visit, _, stations = await started(ops)
    await ops.db["site_visits"].update_one(
        {"_id": visit["id"]}, {"$set": {"stations.$[].work": None}}
    )
    r = await put(ops, "tech1", visit["id"], stations[0]["id"], 0, notes="Late")
    assert r.status_code == 200, r.text
    work = work_of(r.json(), stations[0]["id"])
    assert work["version"] == 1 and len(work["checklist"]) == 2


# --- Saving (VIS-7) -----------------------------------------------------------------------------


@pytest.mark.req("VIS-7")
async def test_the_owner_saves_a_record_and_it_comes_back_stamped(ops):
    await template(ops)
    visit, _, stations = await started(ops)
    sid = stations[0]["id"]
    rows = work_of(visit, sid)["checklist"]
    r = await put(
        ops, "tech1", visit["id"], sid, 0, device_id="phone-1",
        condition_on_arrival={"status": "degraded", "notes": "Water in the enclosure"},
        checklist=[{"item_id": rows[0]["item_id"], "result": "fixed", "note": "Re-tensioned"},
                   {"item_id": new_id(), "ad_hoc": True, "label": "Fence gate", "result": "ok"}],
        parts_used=[{"id": new_id(), "description": "Desiccant", "quantity": 2}],
        issues_found=[{"id": new_id(), "description": "Rust on the mast", "severity": "low"}],
        data_downloaded={"done": True, "from": "2026-10-01T00:00:00Z",
                         "to": "2026-10-22T00:00:00Z"},
        condition_on_departure={"status": "operational"}, notes="All good now",
    )
    assert r.status_code == 200, r.text
    work = work_of(r.json(), sid)
    assert (work["version"], work["updated_by"], work["device_id"]) == (1, TECH1, "phone-1")
    assert work["updated_at"] is not None
    assert work["condition_on_arrival"]["status"] == "degraded"
    labels = [(x["label"], x["result"], x["ad_hoc"]) for x in work["checklist"]]
    assert labels == [(ITEMS[0]["label"], "fixed", False), (ITEMS[1]["label"], None, False),
                      ("Fence gate", "ok", True)]
    assert work["parts_used"][0]["quantity"] == 2
    assert work["data_downloaded"] == {"done": True, "from": "2026-10-01T00:00:00Z",
                                       "to": "2026-10-22T00:00:00Z"}
    # The other station is untouched
    assert work_of(r.json(), stations[1]["id"])["version"] == 0


@pytest.mark.req("VIS-7")
async def test_a_save_writes_its_event_in_the_same_transaction_with_ids_only(ops):
    visit, request, stations = await started(ops)
    sid = stations[0]["id"]
    action = {"id": new_id(), "action": "clean", "old_serial": "V-23001",
              "note": "SECRET NOTE"}
    r = await put(ops, "tech1", visit["id"], sid, 0, sensor_actions=[action],
                  notes="PRIVATE", config_versions=[{"id": new_id(), "files": [new_id()]}])
    assert r.status_code == 200, r.text
    [event] = await ops.outbox("visit.work_updated")
    assert event.key == request["id"] and event.data["visit_id"] == visit["id"]
    assert event.data["station_id"] == sid and event.data["version"] == 1
    assert event.data["sensor_actions"] == [{"id": action["id"], "action": "clean"}]
    assert len(event.data["config_versions"]) == 1
    assert "SECRET" not in str(event.data) and "PRIVATE" not in str(event.data)
    assert event.actor.user_id == TECH1
    assert event.aggregate_version > visit["version"]


@pytest.mark.req("VIS-7")
async def test_the_same_save_again_is_a_success_that_changes_nothing(ops):
    visit, _, stations = await started(ops)
    sid = stations[0]["id"]
    body = {"notes": "Once", "parts_used": [{"id": new_id(), "description": "Fuse"}]}
    first = await put(ops, "tech1", visit["id"], sid, 0, **body)
    again = await put(ops, "tech1", visit["id"], sid, 0, **body)  # the answer was lost
    assert (first.status_code, again.status_code) == (200, 200)
    assert work_of(again.json(), sid)["version"] == 1
    assert len(await ops.outbox("visit.work_updated")) == 1


@pytest.mark.req("VIS-7")
async def test_a_save_from_an_older_version_is_refused_and_nothing_is_merged(ops):
    visit, _, stations = await started(ops)
    sid = stations[0]["id"]
    assert (await put(ops, "tech1", visit["id"], sid, 0, notes="One")).status_code == 200
    stale = await put(ops, "tech1", visit["id"], sid, 0, notes="Two")
    assert stale.status_code == 409 and stale.json()["code"] == "work_changed"
    assert work_of(await read(ops, "tech1", visit["id"]), sid)["notes"] == "One"
    fresh = await put(ops, "tech1", visit["id"], sid, 1, notes="Two")
    assert fresh.status_code == 200 and work_of(fresh.json(), sid)["version"] == 2


@pytest.mark.req("VIS-7")
async def test_two_owners_save_their_own_stations_without_colliding(ops):
    request, stations = await a_request(ops, staff=("tech1", "tech2"))
    made = await plan(
        ops, "tech1", request, stations, staff=(TECH1, TECH2),
    )
    assert made.status_code == 201
    visit = made.json()
    patch = await ops.http.patch(
        f"/api/v1/visits/{visit['id']}", headers=ops.bearer("tech1"),
        json={"stations": [{"station_id": stations[0]["id"], "owner_staff_id": TECH1},
                           {"station_id": stations[1]["id"], "owner_staff_id": TECH2}]},
    )
    assert patch.status_code == 200, patch.text
    assert (await move(ops, "tech1", visit["id"], "start")).status_code == 200
    one = await put(ops, "tech1", visit["id"], stations[0]["id"], 0, notes="From tech1")
    two = await put(ops, "tech2", visit["id"], stations[1]["id"], 0, notes="From tech2")
    assert (one.status_code, two.status_code) == (200, 200)
    got = await read(ops, "admin", visit["id"])
    assert work_of(got, stations[0]["id"])["notes"] == "From tech1"
    assert work_of(got, stations[1]["id"])["notes"] == "From tech2"


# --- Who and when -------------------------------------------------------------------------------


@pytest.mark.req("VIS-7")
@pytest.mark.req("NFR-6")
async def test_only_the_owner_or_an_admin_saves(ops):
    request, stations = await a_request(ops, staff=("tech1", "tech2"))
    visit = (await plan(ops, "tech1", request, stations, staff=(TECH1, TECH2))).json()
    await move(ops, "tech1", visit["id"], "start")
    sid = stations[0]["id"]  # owned by tech1
    other = await put(ops, "tech2", visit["id"], sid, 0, notes="Not mine")
    assert other.status_code == 403 and other.json()["code"] == "not_owner"
    assert (await put(ops, "viewer", visit["id"], sid, 0, notes="x")).status_code == 403
    assert (await put(ops, "client_a1", visit["id"], sid, 0, notes="x")).status_code == 403
    assert (await put(ops, "admin", visit["id"], sid, 0, notes="Admin")).status_code == 200


@pytest.mark.req("VIS-7")
async def test_a_station_that_is_not_on_the_visit_or_a_visit_that_is_not_there_is_404(ops):
    visit, _, stations = await started(ops)
    assert (await put(ops, "tech1", visit["id"], new_id(), 0)).status_code == 404
    assert (await put(ops, "tech1", new_id(), stations[0]["id"], 0)).status_code == 404


@pytest.mark.req("VIS-7")
async def test_a_planned_or_cancelled_visit_takes_no_record(ops):
    visit, _, stations = await scheduled(ops)
    planned = await put(ops, "tech1", visit["id"], stations[0]["id"], 0, notes="Early")
    assert planned.status_code == 409 and planned.json()["code"] == "not_started"
    assert (await move(ops, "tech1", visit["id"], "cancel")).status_code == 200
    gone = await put(ops, "tech1", visit["id"], stations[0]["id"], 0, notes="Late")
    assert gone.status_code == 409 and gone.json()["code"] == "visit_cancelled"


@pytest.mark.req("VIS-7")
async def test_an_ended_visit_still_takes_edits_until_it_is_locked(ops):
    visit, _, stations = await started(ops)
    sid = stations[0]["id"]
    assert (await put(ops, "tech1", visit["id"], sid, 0, notes="During")).status_code == 200
    ended = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert ended.status_code == 200, ended.text
    after = await put(ops, "tech1", visit["id"], sid, 1, notes="After the end")
    assert after.status_code == 200 and work_of(after.json(), sid)["version"] == 2

    await ops.db["site_visits"].update_one({"_id": visit["id"]}, {"$set": {"locked": True}})
    locked = await put(ops, "admin", visit["id"], sid, 2, notes="Too late")
    assert locked.status_code == 409 and locked.json()["code"] == "locked"
    assert work_of(await read(ops, "admin", visit["id"]), sid)["notes"] == "After the end"


# --- What is checked ----------------------------------------------------------------------------


@pytest.mark.req("VIS-7")
async def test_the_record_is_checked(ops):
    await template(ops)
    visit, _, stations = await started(ops)
    sid = stations[0]["id"]
    row = work_of(visit, sid)["checklist"][0]["item_id"]
    cases: list[tuple[dict[str, Any], str]] = [
        ({"checklist": [{"item_id": "nope", "result": "ok"}]}, "unknown_item"),
        ({"checklist": [{"item_id": row, "result": "great"}]}, "validation_failed"),
        ({"sensor_actions": [{"id": new_id(), "action": "replace", "parameter": "AT"}]},
         "serial_required"),
        ({"parts_used": [{"id": "not-a-uuid", "description": "x"}]}, "validation_failed"),
        ({"notes": "x" * 4001}, "validation_failed"),
        ({"unknown_field": 1}, "validation_failed"),
    ]
    for body, code in cases:
        r = await put(ops, "tech1", visit["id"], sid, 0, **body)
        assert r.status_code == 422, (body, r.text)
        assert r.json()["code"] == code, (body, r.json())
    assert work_of(await read(ops, "tech1", visit["id"]), sid)["version"] == 0  # nothing stuck


@pytest.mark.req("VIS-7")
async def test_a_calibration_date_in_an_action_is_stored(ops):
    visit, _, stations = await started(ops)
    sid = stations[0]["id"]
    action = {
        "id": new_id(), "action": "calibrate", "parameter": "AT", "old_serial": "V-23001",
        "calibration": {"method": "field_check", "result": "pass",
                        "reference_instrument": {"model": "Fluke", "certificate_due": "2027-01-31"},
                        "readings": [{"reference": 20.0, "before": 20.4, "after": 20.1,
                                      "unit": "C"}]},
    }
    r = await put(ops, "tech1", visit["id"], sid, 0, sensor_actions=[action])
    assert r.status_code == 200, r.text
    saved = work_of(r.json(), sid)["sensor_actions"][0]
    assert saved["calibration"]["reference_instrument"]["certificate_due"] == "2027-01-31"


# --- Who sees it (rule 6) -----------------------------------------------------------------------


@pytest.mark.req("VIS-11")
@pytest.mark.req("NFR-6")
async def test_a_client_never_sees_a_work_record_and_staff_do(ops):
    visit, _, stations = await started(ops)
    sid = stations[0]["id"]
    await put(ops, "tech1", visit["id"], sid, 0, notes="Staff eyes only")
    client = await read(ops, "client_a1", visit["id"])
    assert all(s["work"] is None for s in client["stations"])
    assert "Staff eyes only" not in str(client)
    for who in ("tech2", "viewer", "admin"):
        got = await read(ops, who, visit["id"])
        assert work_of(got, sid)["notes"] == "Staff eyes only"
    assert visit["org_id"] == ORG_A
    other_org = await ops.http.get(f"/api/v1/visits/{visit['id']}",
                                   headers=ops.bearer("client_b1"))
    assert other_org.status_code == 404
    assert SEED_USERS["client_b1"].id not in str(client)
