"""Visits, W10 (PRD VIS-1 to VIS-4, VIS-9, VIS-11; ADR-17, ADR-18; rules 2 to 6), over the real app:
scheduling and running a visit, the request's status derived from its visits in the same
transaction, owners, and who may see and do what."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from tests.api.test_requests import act, make

TECH1 = SEED_USERS["tech1"].id
TECH2 = SEED_USERS["tech2"].id
ADMIN = SEED_USERS["admin"].id
CLIENT_A1 = SEED_USERS["client_a1"].id


async def a_request(
    ops, *, stations: int = 2, staff: tuple[str, ...] = ("tech1",)
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """An Assigned request for organization A covering `stations` stations."""
    codes = ["JM-KIN-001", "JM-MBJ-002", "JM-BLU-003"][:stations]
    found = [await ops.station(code=code, owner_org_id=ORG_A) for code in codes]
    request = await make(ops, "admin", [s["id"] for s in found], org_id=ORG_A)
    r = await act(ops, "admin", request["id"], "assign",
                  staff_ids=[SEED_USERS[name].id for name in staff])
    assert r.status_code == 200, r.text
    return r.json(), found


def when(ops, **delta: float) -> str:
    return (ops.clock.now() + timedelta(**delta)).isoformat()


def body(ops, request: dict[str, Any], covers: list[dict[str, Any]], *,
         staff: tuple[str, ...] = (TECH1,), **fields: Any) -> dict[str, Any]:
    return {
        "request_id": request["id"], "planned_start": when(ops, days=1),
        "planned_end": when(ops, days=2), "staff_ids": list(staff),
        "stations": [{"station_id": s["id"]} for s in covers], **fields,
    }


async def plan(ops, who: str, request, covers, **fields: Any):
    return await ops.http.post("/api/v1/visits", json=body(ops, request, covers, **fields),
                               headers=ops.bearer(who))


async def scheduled(ops, who: str = "tech1", **kw: Any) -> tuple[dict[str, Any], dict[str, Any],
                                                                  list[dict[str, Any]]]:
    request, stations = await a_request(ops, **kw)
    r = await plan(ops, who, request, stations)
    assert r.status_code == 201, r.text
    return r.json(), request, stations


async def move(ops, who: str, visit_id: str, verb: str, **json: Any):
    return await ops.http.post(f"/api/v1/visits/{visit_id}/{verb}", json=json,
                               headers=ops.bearer(who))


async def request_now(ops, request_id: str, who: str = "admin") -> dict[str, Any]:
    r = await ops.http.get(f"/api/v1/requests/{request_id}", headers=ops.bearer(who))
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


# --- Scheduling (VIS-1) ------------------------------------------------------------------------


@pytest.mark.req("VIS-1")
async def test_the_assigned_technician_schedules_a_visit_and_the_request_becomes_scheduled(ops):
    request, stations = await a_request(ops)
    r = await plan(ops, "tech1", request, stations, notes="Bring the long ladder")
    assert r.status_code == 201, r.text
    visit = r.json()
    assert visit["status"] == "planned"
    assert visit["ref"] == request["ref"].replace("MR", "VR") + "-01"
    assert visit["lead"] == {"id": TECH1, "name": SEED_USERS["tech1"].name}
    assert [p["id"] for p in visit["staff"]] == [TECH1]
    assert [s["owner"]["id"] for s in visit["stations"]] == [TECH1, TECH1]  # the lead by default
    assert visit["notes"] == "Bring the long ladder"
    assert set(visit["actions"]) == {"reschedule", "cancel", "start"}

    got = await request_now(ops, request["id"])
    assert got["status"] == "scheduled"
    last = got["status_history"][-1]
    assert (last["from_status"], last["to_status"]) == ("assigned", "scheduled")
    assert last["note"] == f"Visit {visit['ref']} planned"
    assert [v["ref"] for v in got["visits"]] == [visit["ref"]]
    assert "schedule_visit" in got["actions"]  # another visit can be planned at the same time


@pytest.mark.req("VIS-1")
async def test_scheduling_writes_its_events_in_the_same_transaction(ops):
    visit, request, stations = await scheduled(ops)
    [event] = await ops.outbox("visit.scheduled")
    assert event.key == request["id"] and event.data["visit_id"] == visit["id"]
    assert event.data["staff_ids"] == [TECH1] and event.data["lead_staff_id"] == TECH1
    assert {o["station_id"] for o in event.data["station_owners"]} == {s["id"] for s in stations}
    assert event.data["title"] == request["title"] and event.data["org_id"] == ORG_A
    assert "notes" not in event.data
    changed = [e for e in await ops.outbox("request.status_changed")
               if e.data["to_status"] == "scheduled"]
    assert len(changed) == 1 and changed[0].data["from_status"] == "assigned"
    assert event.actor.user_id == TECH1


@pytest.mark.req("VIS-1")
async def test_scheduling_is_idempotent_by_id(ops):
    request, stations = await a_request(ops)
    visit_id = new_id()
    first = await plan(ops, "tech1", request, stations, id=visit_id)
    again = await plan(ops, "tech1", request, stations, id=visit_id)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"] == visit_id
    assert len(await ops.outbox("visit.scheduled")) == 1
    other = await plan(ops, "admin", request, stations, id=visit_id)
    assert other.status_code == 409 and other.json()["code"] == "id_taken"


@pytest.mark.req("VIS-1")
async def test_only_the_requests_assigned_staff_or_an_admin_schedule(ops):
    request, stations = await a_request(ops)
    r = await plan(ops, "tech2", request, stations, staff=(TECH2,))
    assert r.status_code == 403 and r.json()["code"] == "not_assigned"
    assert (await plan(ops, "admin", request, stations)).status_code == 201
    assert (await plan(ops, "viewer", request, stations)).status_code == 403
    assert (await plan(ops, "client_a1", request, stations)).status_code == 403


@pytest.mark.req("VIS-1")
async def test_a_visit_needs_an_assigned_request(ops):
    a = await ops.station(code="JM-KIN-001", owner_org_id=ORG_A)
    approved = await make(ops, "admin", [a["id"]], org_id=ORG_A)  # in the queue, nobody on it
    r = await plan(ops, "admin", approved, [a])
    assert r.status_code == 409 and r.json()["code"] == "request_not_schedulable"
    gone = await plan(ops, "admin", {"id": new_id()}, [a])
    assert gone.status_code == 404


@pytest.mark.req("VIS-1")
async def test_the_plan_is_checked(ops):
    request, stations = await a_request(ops)
    cases = [
        ({"planned_end": when(ops, hours=1)}, "bad_window"),
        ({"planned_end": when(ops, days=60)}, "too_long"),
        ({"lead_staff_id": TECH2}, "lead_not_attending"),
        ({"stations": [{"station_id": stations[0]["id"], "owner_staff_id": TECH2}]},
         "owner_not_attending"),
        ({"stations": [{"station_id": new_id()}]}, "station_not_on_request"),
        ({"staff_ids": [CLIENT_A1]}, "not_assignable"),
        ({"staff_ids": [SEED_USERS["disabled"].id]}, "not_assignable"),
    ]
    for override, code in cases:
        payload = {**body(ops, request, stations), **override}
        r = await ops.http.post("/api/v1/visits", json=payload, headers=ops.bearer("admin"))
        assert r.status_code == 422, (code, r.text)
        assert r.json()["code"] == code, (code, r.text)
    assert await ops.outbox("visit.scheduled") == []


@pytest.mark.req("VIS-1")
async def test_the_owner_of_each_station_can_be_chosen_from_the_people_attending(ops):
    request, stations = await a_request(ops)
    s1, s2 = stations
    r = await plan(ops, "tech1", request, stations, staff=(TECH1, TECH2), lead_staff_id=TECH1,
                   stations=[{"station_id": s1["id"]},
                             {"station_id": s2["id"], "owner_staff_id": TECH2}])
    assert r.status_code == 201, r.text
    owners = {s["station_id"]: s["owner"]["id"] for s in r.json()["stations"]}
    assert owners == {s1["id"]: TECH1, s2["id"]: TECH2}


@pytest.mark.req("VIS-1")
async def test_visits_of_one_request_are_numbered_in_order(ops):
    request, stations = await a_request(ops)
    first = await plan(ops, "tech1", request, stations[:1])
    second = await plan(ops, "tech1", request, stations[1:])
    assert first.json()["ref"].endswith("-01") and second.json()["ref"].endswith("-02")


# --- Parallel visits (ADR-17) ------------------------------------------------------------------


@pytest.mark.req("ADR-17")
async def test_two_visits_on_different_stations_run_in_parallel_and_the_status_follows(ops):
    request, (s1, s2) = await a_request(ops)
    one = (await plan(ops, "tech1", request, [s1])).json()
    two = (await plan(ops, "tech1", request, [s2])).json()
    assert (await request_now(ops, request["id"]))["status"] == "scheduled"

    assert (await move(ops, "tech1", one["id"], "start")).status_code == 200
    now = await request_now(ops, request["id"])
    assert now["status"] == "in_progress" and now["milestones"]["first_visit_at"] is not None
    # The second visit starting changes nothing: the request is already in progress
    assert (await move(ops, "tech1", two["id"], "start")).status_code == 200
    assert (await request_now(ops, request["id"]))["status"] == "in_progress"

    r = await move(ops, "tech1", one["id"], "end", additional_visit_required=True,
                   follow_up_notes="Mast needs painting")
    assert r.status_code == 200, r.text
    assert (await request_now(ops, request["id"]))["status"] == "in_progress"  # two is still on
    r = await move(ops, "tech1", two["id"], "end", additional_visit_required=True,
                   follow_up_notes="Battery to replace")
    assert r.status_code == 200
    assert (await request_now(ops, request["id"]))["status"] == "assigned"  # another is needed
    moves = [(e.data["from_status"], e.data["to_status"])
             for e in await ops.outbox("request.status_changed")]
    assert ("assigned", "scheduled") in moves and ("scheduled", "in_progress") in moves
    assert ("in_progress", "assigned") in moves


@pytest.mark.req("ADR-17")
async def test_a_station_cannot_be_in_two_live_visits_of_one_request(ops):
    request, (s1, s2) = await a_request(ops)
    assert (await plan(ops, "tech1", request, [s1])).status_code == 201
    r = await plan(ops, "tech1", request, [s1, s2])
    assert r.status_code == 409 and r.json()["code"] == "station_in_other_visit"
    # Once the first is cancelled the station is free again
    first = (await ops.http.get("/api/v1/visits", params={"request_id": request["id"]},
                                headers=ops.bearer("admin"))).json()["items"][0]
    assert (await move(ops, "tech1", first["id"], "cancel")).status_code == 200
    assert (await plan(ops, "tech1", request, [s1, s2])).status_code == 201


@pytest.mark.req("ADR-17")
async def test_two_visits_planned_at_once_both_count(ops):
    request, (s1, s2) = await a_request(ops)
    results = await asyncio.gather(plan(ops, "tech1", request, [s1]),
                                   plan(ops, "tech1", request, [s2]))
    assert [r.status_code for r in results] == [201, 201]
    assert {r.json()["ref"][-2:] for r in results} == {"01", "02"}
    assert (await request_now(ops, request["id"]))["status"] == "scheduled"
    assert len(await ops.outbox("visit.scheduled")) == 2


# --- Running a visit (VIS-4, VIS-9) ------------------------------------------------------------


@pytest.mark.req("VIS-4")
async def test_a_visit_is_started_arrived_at_departed_from_and_ended(ops):
    visit, request, (s1, s2) = await scheduled(ops)
    sid = s1["id"]
    r = await move(ops, "tech1", visit["id"], "start")
    started = r.json()
    assert r.status_code == 200 and started["status"] == "started"
    assert started["started_at"]
    assert set(started["actions"]) == {"end", "change_owner"}
    assert started["stations"][0]["actions"] == ["arrive"]

    arrived = await move(ops, "tech1", visit["id"], f"stations/{sid}/arrive")
    assert arrived.status_code == 200 and arrived.json()["stations"][0]["arrived_at"]
    assert arrived.json()["stations"][0]["actions"] == ["depart"]
    left = await move(ops, "tech1", visit["id"], f"stations/{sid}/depart")
    assert left.status_code == 200 and left.json()["stations"][0]["departed_at"]
    assert left.json()["stations"][0]["actions"] == []
    assert left.json()["stations"][1]["arrived_at"] is None  # the other station is untouched

    ended = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert ended.status_code == 200 and ended.json()["status"] == "ended"
    assert ended.json()["actions"] == []
    # No visit report yet (Phase 6): the request waits In progress for it
    assert (await request_now(ops, request["id"]))["status"] == "in_progress"
    for type_ in ("visit.started", "visit.station_arrived", "visit.station_departed",
                  "visit.ended"):
        assert len(await ops.outbox(type_)) == 1, type_
    [ended_event] = await ops.outbox("visit.ended")
    assert ended_event.data["additional_visit_required"] is False
    assert ended_event.data["sensor_actions"] == [] and ended_event.data["config_versions"] == []


@pytest.mark.req("VIS-4")
async def test_a_repeated_move_by_the_same_person_changes_nothing(ops):
    visit, request, (s1, _) = await scheduled(ops)
    sid = s1["id"]
    first = (await move(ops, "tech1", visit["id"], "start")).json()
    again = await move(ops, "tech1", visit["id"], "start")
    assert again.status_code == 200 and again.json()["version"] == first["version"]
    await move(ops, "tech1", visit["id"], f"stations/{sid}/arrive")
    await move(ops, "tech1", visit["id"], f"stations/{sid}/arrive")
    await move(ops, "tech1", visit["id"], f"stations/{sid}/depart")
    await move(ops, "tech1", visit["id"], f"stations/{sid}/depart")
    await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    again = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert again.status_code == 200
    for type_ in ("visit.started", "visit.station_arrived", "visit.station_departed",
                  "visit.ended"):
        assert len(await ops.outbox(type_)) == 1, type_
    other = await move(ops, "tech1", visit["id"], "end", additional_visit_required=True,
                       follow_up_notes="More")
    assert other.status_code == 409 and other.json()["code"] == "already_ended"


@pytest.mark.req("VIS-4")
async def test_the_devices_time_is_used_within_limits(ops):
    visit, request, (s1, _) = await scheduled(ops)
    earlier = (ops.clock.now() - timedelta(hours=3)).isoformat()
    r = await move(ops, "tech1", visit["id"], "start", at=earlier)
    assert r.status_code == 200
    assert r.json()["started_at"].startswith(earlier[:16])
    bad = await move(ops, "tech1", visit["id"], f"stations/{s1['id']}/arrive",
                     at=when(ops, hours=1))
    assert bad.status_code == 422 and bad.json()["code"] == "bad_time"


@pytest.mark.req("VIS-4")
async def test_only_the_owner_arrives_at_a_station(ops):
    request, (s1, s2) = await a_request(ops)
    visit = (await plan(ops, "tech1", request, [s1, s2], staff=(TECH1, TECH2), stations=[
        {"station_id": s1["id"]}, {"station_id": s2["id"], "owner_staff_id": TECH2},
    ])).json()
    await move(ops, "tech1", visit["id"], "start")
    r = await move(ops, "tech1", visit["id"], f"stations/{s2['id']}/arrive")  # Tech 2's station
    assert r.status_code == 403 and r.json()["code"] == "not_owner"
    assert (await move(ops, "tech2", visit["id"], f"stations/{s2['id']}/arrive")).status_code == 200
    assert (await move(ops, "admin", visit["id"], f"stations/{s1['id']}/arrive")).status_code == 200
    # Leaving needs arriving first, and a stranger cannot start or end it
    r = await move(ops, "viewer", visit["id"], "end", additional_visit_required=False)
    assert r.status_code == 403


@pytest.mark.req("VIS-4")
async def test_arriving_needs_a_started_visit_and_leaving_needs_arriving(ops):
    visit, request, (s1, _) = await scheduled(ops)
    sid = s1["id"]
    r = await move(ops, "tech1", visit["id"], f"stations/{sid}/arrive")
    assert r.status_code == 409 and r.json()["code"] == "not_started"
    await move(ops, "tech1", visit["id"], "start")
    r = await move(ops, "tech1", visit["id"], f"stations/{sid}/depart")
    assert r.status_code == 409 and r.json()["code"] == "not_arrived"
    assert (await move(ops, "tech1", visit["id"], f"stations/{new_id()}/arrive")).status_code == 404


@pytest.mark.req("VIS-9")
async def test_ending_with_another_visit_needed_returns_the_request_to_assigned(ops):
    visit, request, _ = await scheduled(ops)
    await move(ops, "tech1", visit["id"], "start")
    r = await move(ops, "tech1", visit["id"], "end", additional_visit_required=True)
    assert r.status_code == 422 and r.json()["code"] == "notes_required"
    r = await move(ops, "tech1", visit["id"], "end", additional_visit_required=True,
                   follow_up_notes="  Replace the solar panel  ")
    assert r.status_code == 200
    assert r.json()["additional_visit_required"] is True
    assert r.json()["follow_up_notes"] == "Replace the solar panel"
    assert (await request_now(ops, request["id"]))["status"] == "assigned"


@pytest.mark.req("VIS-9")
async def test_an_override_must_name_a_station_on_the_visit(ops):
    visit, _, _ = await scheduled(ops)
    await move(ops, "tech1", visit["id"], "start")
    r = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False,
                   overrides=[{"station_id": new_id(), "reason": "No signal"}])
    assert r.status_code == 422


# --- Cancelling and restoring (VIS-2) ----------------------------------------------------------


@pytest.mark.req("VIS-2")
async def test_cancelling_the_only_visit_returns_the_request_to_assigned(ops):
    visit, request, _ = await scheduled(ops)
    r = await move(ops, "tech1", visit["id"], "cancel", reason="Storm warning")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await request_now(ops, request["id"]))["status"] == "assigned"
    [event] = await ops.outbox("visit.cancelled")
    assert event.data["reason"] == "Storm warning" and event.data["by_request"] is False
    again = await move(ops, "tech1", visit["id"], "cancel")
    assert again.status_code == 200 and len(await ops.outbox("visit.cancelled")) == 1
    restart = await move(ops, "tech1", visit["id"], "start")
    assert restart.status_code == 409 and restart.json()["code"] == "visit_cancelled"


@pytest.mark.req("VIS-2")
async def test_a_started_visit_cannot_be_cancelled_and_a_stranger_cannot_cancel(ops):
    visit, request, _ = await scheduled(ops)
    assert (await move(ops, "tech2", visit["id"], "cancel")).status_code == 403
    await move(ops, "tech1", visit["id"], "start")
    r = await move(ops, "tech1", visit["id"], "cancel")
    assert r.status_code == 409 and r.json()["code"] == "visit_started"


@pytest.mark.req("VIS-2")
async def test_only_an_admin_restores_a_cancelled_visit(ops):
    visit, request, _ = await scheduled(ops)
    await move(ops, "tech1", visit["id"], "cancel")
    assert (await move(ops, "tech1", visit["id"], "restore")).status_code == 403
    r = await move(ops, "admin", visit["id"], "restore")
    assert r.status_code == 200 and r.json()["status"] == "planned"
    assert (await request_now(ops, request["id"]))["status"] == "scheduled"
    assert len(await ops.outbox("visit.restored")) == 1
    assert (await move(ops, "admin", visit["id"], "restore")).status_code == 200  # a repeat


@pytest.mark.req("VIS-2")
async def test_a_station_taken_in_the_meantime_blocks_a_restore(ops):
    request, (s1, s2) = await a_request(ops)
    first = (await plan(ops, "tech1", request, [s1])).json()
    await move(ops, "tech1", first["id"], "cancel")
    assert (await plan(ops, "tech1", request, [s1])).status_code == 201
    r = await move(ops, "admin", first["id"], "restore")
    assert r.status_code == 409 and r.json()["code"] == "station_in_other_visit"


# --- Changing a visit (VIS-2, J5 steps 5 and 5b) ------------------------------------------------


@pytest.mark.req("VIS-2")
async def test_rescheduling_changes_the_dates_and_says_so(ops):
    visit, request, _ = await scheduled(ops)
    start, end = when(ops, days=3), when(ops, days=4)
    r = await ops.http.patch(f"/api/v1/visits/{visit['id']}",
                             json={"planned_start": start, "planned_end": end},
                             headers=ops.bearer("tech1"))
    assert r.status_code == 200, r.text
    assert r.json()["planned_start"].startswith(start[:16])
    [event] = await ops.outbox("visit.rescheduled")
    assert event.data["changed_fields"] == ["dates"]
    assert (await request_now(ops, request["id"]))["status"] == "scheduled"
    same = await ops.http.patch(f"/api/v1/visits/{visit['id']}",
                                json={"planned_start": start}, headers=ops.bearer("tech1"))
    assert same.status_code == 200 and len(await ops.outbox("visit.rescheduled")) == 1


@pytest.mark.req("VIS-2")
async def test_a_stranger_cannot_reschedule_and_a_stale_version_is_refused(ops):
    visit, _, _ = await scheduled(ops)
    patch = {"notes": "Changed"}
    denied = await ops.http.patch(f"/api/v1/visits/{visit['id']}", json=patch,
                                  headers=ops.bearer("tech2"))
    assert denied.status_code == 403
    ok = await ops.http.patch(f"/api/v1/visits/{visit['id']}", json=patch | {"version": 1},
                              headers=ops.bearer("tech1"))
    assert ok.status_code == 200 and ok.json()["notes"] == "Changed"
    stale = await ops.http.patch(f"/api/v1/visits/{visit['id']}",
                                 json={"notes": "Again", "version": 1},
                                 headers=ops.bearer("tech1"))
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    assert await ops.outbox("visit.rescheduled") == []  # notes alone are not a reschedule


@pytest.mark.req("VIS-1")
async def test_changing_who_attends_and_who_owns_a_planned_station(ops):
    visit, request, (s1, s2) = await scheduled(ops)
    r = await ops.http.patch(
        f"/api/v1/visits/{visit['id']}",
        json={"staff_ids": [TECH1, TECH2],
              "stations": [{"station_id": s1["id"]},
                           {"station_id": s2["id"], "owner_staff_id": TECH2}]},
        headers=ops.bearer("tech1"),
    )
    assert r.status_code == 200, r.text
    assert [p["id"] for p in r.json()["staff"]] == [TECH1, TECH2]
    assert [s["owner"]["name"] for s in r.json()["stations"]] == [
        SEED_USERS["tech1"].name, SEED_USERS["tech2"].name,
    ]
    [moved] = await ops.outbox("visit.station_owner_changed")
    assert (moved.data["from_staff_id"], moved.data["to_staff_id"]) == (TECH1, TECH2)
    [event] = await ops.outbox("visit.rescheduled")
    assert set(event.data["changed_fields"]) == {"staff", "owners"}
    # The person who left the visit hands their station back to the lead
    back = await ops.http.patch(f"/api/v1/visits/{visit['id']}", json={"staff_ids": [TECH1]},
                                headers=ops.bearer("tech1"))
    assert {s["owner"]["id"] for s in back.json()["stations"]} == {TECH1}


@pytest.mark.req("VIS-1")
async def test_once_started_only_the_lead_or_an_admin_changes_an_owner(ops):
    request, (s1, s2) = await a_request(ops)
    visit = (await plan(ops, "tech1", request, [s1, s2], staff=(TECH1, TECH2))).json()
    await move(ops, "tech1", visit["id"], "start")
    url = f"/api/v1/visits/{visit['id']}"
    change = {"stations": [{"station_id": s2["id"], "owner_staff_id": TECH2}]}
    assert (await ops.http.patch(url, json=change, headers=ops.bearer("tech2"))).status_code == 403
    r = await ops.http.patch(url, json=change, headers=ops.bearer("tech1"))
    assert r.status_code == 200, r.text
    assert r.json()["stations"][1]["owner"]["id"] == TECH2
    assert len(await ops.outbox("visit.station_owner_changed")) == 1
    assert await ops.outbox("visit.rescheduled") == []
    dates = await ops.http.patch(url, json={"planned_start": when(ops, days=5)},
                                 headers=ops.bearer("tech1"))
    assert dates.status_code == 409 and dates.json()["code"] == "visit_started"
    missing = await ops.http.patch(url, json={"stations": [{"station_id": s1["id"]}]},
                                   headers=ops.bearer("tech1"))
    assert missing.status_code == 422 and missing.json()["code"] == "owner_required"


@pytest.mark.req("VIS-2")
async def test_an_ended_or_cancelled_visit_cannot_be_changed(ops):
    visit, _, _ = await scheduled(ops)
    await move(ops, "tech1", visit["id"], "cancel")
    r = await ops.http.patch(f"/api/v1/visits/{visit['id']}", json={"notes": "x"},
                             headers=ops.bearer("tech1"))
    assert r.status_code == 409 and r.json()["code"] == "visit_cancelled"


# --- Request side effects (W10-7) --------------------------------------------------------------


@pytest.mark.req("REQ-7")
async def test_a_request_with_a_live_visit_cannot_be_released(ops):
    visit, request, _ = await scheduled(ops)
    r = await act(ops, "tech1", request["id"], "release")
    assert r.status_code == 409 and r.json()["code"] == "has_visits"
    await move(ops, "tech1", visit["id"], "cancel")
    assert (await act(ops, "tech1", request["id"], "release")).status_code == 200


@pytest.mark.req("REQ-11")
async def test_cancelling_a_request_cancels_its_planned_visits_but_not_a_started_one(ops):
    request, (s1, s2) = await a_request(ops)
    started = (await plan(ops, "tech1", request, [s1])).json()
    planned = (await plan(ops, "tech1", request, [s2])).json()
    await move(ops, "tech1", started["id"], "start")
    r = await act(ops, "admin", request["id"], "cancel", reason="Station decommissioned")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    seen = {v["id"]: v["status"] for v in r.json()["visits"]}
    assert seen == {started["id"]: "started", planned["id"]: "cancelled"}
    [event] = await ops.outbox("visit.cancelled")
    assert event.data["by_request"] is True and event.data["reason"] == "Station decommissioned"
    # The request stays cancelled, whatever the started visit does (no derived status)
    await move(ops, "tech1", started["id"], "end", additional_visit_required=False)
    assert (await request_now(ops, request["id"]))["status"] == "cancelled"


# --- Reading (VIS-11, rules 3, 4 and 6) ---------------------------------------------------------


@pytest.mark.req("VIS-11")
async def test_a_client_sees_their_organizations_visits_without_the_notes(ops):
    request, stations = await a_request(ops)
    visit = (await plan(ops, "tech1", request, stations, notes="Gate code is 4471")).json()
    r = await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer("client_a1"))
    assert r.status_code == 200, r.text
    seen = r.json()
    assert seen["notes"] is None and "4471" not in str(seen)
    assert seen["lead"]["name"] == SEED_USERS["tech1"].name and seen["actions"] == []
    assert all(s["actions"] == [] for s in seen["stations"])
    assert "@" not in str(seen)  # names only, never an email address (D4)
    listed = (await ops.http.get("/api/v1/visits", headers=ops.bearer("client_a1"))).json()
    assert [v["id"] for v in listed["items"]] == [visit["id"]]
    on_request = await request_now(ops, request["id"], "client_a1")
    assert [v["id"] for v in on_request["visits"]] == [visit["id"]]
    assert "schedule_visit" not in on_request["actions"]


@pytest.mark.req("VIS-11")
async def test_another_organizations_visit_is_not_found(ops):
    visit, _, _ = await scheduled(ops)
    r = await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer("client_b1"))
    assert r.status_code == 404
    listed = (await ops.http.get("/api/v1/visits", headers=ops.bearer("client_b1"))).json()
    assert listed["items"] == [] and listed["total"] == 0
    clients_own = await ops.http.get("/api/v1/visits/mine", headers=ops.bearer("client_a1"))
    assert clients_own.status_code == 403


@pytest.mark.req("VIS-1")
async def test_my_visits_lists_what_i_attend_that_is_planned_or_under_way(ops):
    request, (s1, s2) = await a_request(ops, staff=("tech1", "tech2"))
    mine = (await plan(ops, "tech1", request, [s1], staff=(TECH1,))).json()
    theirs = (await plan(ops, "tech1", request, [s2], staff=(TECH2,))).json()
    got = (await ops.http.get("/api/v1/visits/mine", headers=ops.bearer("tech1"))).json()
    assert [v["id"] for v in got["items"]] == [mine["id"]]
    await move(ops, "tech1", mine["id"], "cancel")
    assert (await ops.http.get("/api/v1/visits/mine",
                               headers=ops.bearer("tech1"))).json()["items"] == []
    other = (await ops.http.get("/api/v1/visits/mine", headers=ops.bearer("tech2"))).json()
    assert [v["id"] for v in other["items"]] == [theirs["id"]]


@pytest.mark.req("VIS-1")
async def test_visits_are_listed_soonest_first_with_filters(ops):
    request, (s1, s2) = await a_request(ops)
    later = (await plan(ops, "tech1", request, [s2], planned_start=when(ops, days=5),
                        planned_end=when(ops, days=6))).json()
    sooner = (await plan(ops, "tech1", request, [s1])).json()
    page = (await ops.http.get("/api/v1/visits", params={"request_id": request["id"]},
                               headers=ops.bearer("tech1"))).json()
    assert [v["id"] for v in page["items"]] == [sooner["id"], later["id"]] and page["total"] == 2
    one = (await ops.http.get("/api/v1/visits", params={"limit": 1},
                              headers=ops.bearer("tech1"))).json()
    assert len(one["items"]) == 1 and one["next_after"] == one["items"][0]["id"]
    cancelled = (await ops.http.get("/api/v1/visits", params={"status": "cancelled"},
                                    headers=ops.bearer("tech1"))).json()
    assert cancelled["items"] == []
    bad = await ops.http.get("/api/v1/visits", params={"status": "nonsense"},
                             headers=ops.bearer("tech1"))
    assert bad.status_code == 422


@pytest.mark.req("VIS-11")
async def test_the_snapshot_carries_visits_without_notes(ops):
    visit, _, _ = await scheduled(ops)
    r = await ops.http.get("/internal/snapshot/visits", headers=ops.service("report"))
    assert r.status_code == 200, r.text
    [item] = r.json()["items"]
    assert item["visit_id"] == visit["id"] and item["aggregate_version"] == 1
    assert "notes" not in item and item["status"] == "planned"
