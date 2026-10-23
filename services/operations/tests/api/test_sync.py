"""`POST /api/v1/sync` over the real app (PRD OFF-5, OFF-7, OFF-11; TRD §7.2 to §7.4; W14-1 to
W14-5; rules 2 to 6): a visit done offline applies in order, the same batch twice changes nothing,
every conflict code comes back with the device keeping its copy, a failed operation stops its own
visit only, and the lead and the admins are told once."""

from __future__ import annotations

from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from tests.api.test_requests import act, make
from tests.api.test_visit_board import board, listed, two_techs
from tests.api.test_visits import TECH1, a_request, move, plan

DEVICE = "01990000-0000-7000-8000-0000000000d1"


def op(type_: str, visit: dict[str, Any], payload: dict[str, Any] | None = None, *,
       op_id: str | None = None, v: int = 1) -> dict[str, Any]:
    return {"op_id": op_id or new_id(), "v": v, "type": type_, "visit_id": visit["id"],
            "payload": payload or {}}


async def sync(ops, who: str, batch: list[dict[str, Any]], device: str = DEVICE):
    return await ops.http.post("/api/v1/sync", json={"device_id": device, "ops": batch},
                               headers=ops.bearer(who))


async def answers(ops, who: str, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    r = await sync(ops, who, batch)
    assert r.status_code == 200, r.text
    out: list[dict[str, Any]] = r.json()["answers"]
    return out


def statuses(found: list[dict[str, Any]]) -> list[str]:
    return [a["status"] for a in found]


async def planned(ops, *, staff: tuple[str, ...] = ("tech1",)):
    request, stations = await a_request(ops, staff=staff)
    r = await plan(ops, "tech1", request, stations,
                   staff=tuple(SEED_USERS[s].id for s in staff))
    assert r.status_code == 201, r.text
    return r.json(), stations


async def other_visit(ops) -> dict[str, Any]:
    """A second visit on a station of its own, for tech1."""
    station = await ops.station(code="JM-SYN-009", owner_org_id=ORG_A)
    request = await make(ops, "admin", [station["id"]], org_id=ORG_A)
    assigned = await act(ops, "admin", request["id"], "assign", staff_ids=[TECH1])
    assert assigned.status_code == 200, assigned.text
    r = await plan(ops, "tech1", assigned.json(), [station])
    assert r.status_code == 201, r.text
    visit: dict[str, Any] = r.json()
    return visit


def note(
    station: dict[str, Any], element_id: str, title: str = "Rust on the mast"
) -> dict[str, Any]:
    return {"station_id": station["id"], "id": element_id, "kind": "note", "title": title}


@pytest.mark.req("OFF-5")
async def test_a_visit_done_offline_is_applied_in_order(ops):
    visit, [one, _] = await planned(ops)
    element = new_id()
    batch = [
        op("visit.start", visit),
        op("station.arrive", visit, {"station_id": one["id"]}),
        op("element.create", visit, note(one, element)),
        op("element.update", visit, {
            "station_id": one["id"], "element_id": element, "title": "Rust, mast base",
            "items": [], "shared": False, "base_version": 1,
        }),
        op("station.depart", visit, {"station_id": one["id"]}),
        op("visit.end", visit, {"additional_visit_required": False}),
    ]
    found = await answers(ops, "tech1", batch)
    assert statuses(found) == ["applied"] * 6, found

    now = (await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer("tech1"))).json()
    assert now["status"] == "ended"
    [shown] = (await listed(ops, "tech1", visit, one))["items"]
    assert shown["id"] == element and shown["title"] == "Rust, mast base" and shown["version"] == 2
    # The answer carries what the server holds, so the phone can replace its own copy
    assert found[2]["result"]["id"] == element and found[3]["result"]["version"] == 2
    for type_ in ("visit.started", "visit.station_arrived", "visit.element_added",
                  "visit.element_updated", "visit.station_departed", "visit.ended"):
        assert len(await ops.outbox(type_)) == 1, type_


@pytest.mark.req("OFF-7")
async def test_the_same_batch_twice_changes_nothing(ops):
    visit, [one, _] = await planned(ops)
    element = new_id()
    batch = [
        op("visit.start", visit),
        op("station.arrive", visit, {"station_id": one["id"]}),
        op("element.create", visit, note(one, element)),
    ]
    first = await answers(ops, "tech1", batch)
    events = {t: len(await ops.outbox(t)) for t in ("visit.started", "visit.station_arrived",
                                                    "visit.element_added")}
    before = (await listed(ops, "tech1", visit, one))["items"]

    again = await answers(ops, "tech1", batch)
    assert statuses(first) == ["applied"] * 3
    assert statuses(again) == ["duplicate"] * 3
    assert [a["result"] for a in again] == [a["result"] for a in first]
    assert {t: len(await ops.outbox(t)) for t in events} == events
    assert (await listed(ops, "tech1", visit, one))["items"] == before
    assert await ops.db["sync_operations"].count_documents({}) == 3


async def test_an_operation_that_is_already_true_online_is_applied_without_a_second_effect(ops):
    # The phone's answer was lost, then the same work was done on the web: nothing doubles
    visit, [one, _] = await planned(ops)
    started = await move(ops, "tech1", visit["id"], "start")
    assert started.status_code == 200
    found = await answers(ops, "tech1", [op("visit.start", visit)])
    assert statuses(found) == ["applied"]
    assert len(await ops.outbox("visit.started")) == 1


@pytest.mark.req("OFF-11")
async def test_work_for_a_station_someone_else_owns_comes_back_as_not_owner(ops):
    visit, _, [one, two] = await two_techs(ops)  # tech1 owns both and leads; tech2 attends
    mine = new_id()
    batch = [
        op("station.arrive", visit, {"station_id": one["id"]}),
        op("element.create", visit, note(one, mine)),
    ]
    found = await answers(ops, "tech2", batch)
    assert found[0]["status"] == "conflict" and found[0]["code"] == "not_owner"
    # The note would have been allowed (anyone attending adds), but an earlier change for this
    # visit did not apply, so it waits
    assert found[1]["status"] == "skipped" and found[1]["retryable"] is True
    assert (await listed(ops, "tech1", visit, one))["items"] == []
    assert await ops.db["sync_operations"].count_documents({}) == 0  # a conflict is not remembered

    [event] = await ops.outbox("visit.sync_conflict")
    assert event.data["reason"] == "not_owner" and event.data["op_types"] == ["station.arrive"]
    assert event.data["user_id"] == SEED_USERS["tech2"].id
    assert event.data["lead_staff_id"] == TECH1
    assert "title" not in str(event.data["op_types"])

    # Trying again every five minutes does not tell the lead again, and still cannot apply
    again = await answers(ops, "tech2", batch)
    assert again[0]["code"] == "not_owner"
    assert len(await ops.outbox("visit.sync_conflict")) == 1


async def test_a_failed_operation_stops_its_own_visit_and_not_another(ops):
    visit, _, [one, two] = await two_techs(ops)
    second = await other_visit(ops)
    started = await move(ops, "tech1", second["id"], "start")
    assert started.status_code == 200
    batch = [
        op("station.arrive", visit, {"station_id": one["id"]}),  # tech2 does not own it
        op("station.arrive", visit, {"station_id": two["id"]}),
        op("element.create", second, note({"id": second["stations"][0]["station_id"]}, new_id())),
    ]
    found = await answers(ops, "tech2", batch)
    assert found[0]["status"] == "conflict"
    assert found[1]["status"] == "skipped"
    # tech2 does not attend the second visit at all: its own refusal, not the first visit's block
    assert found[2]["status"] == "conflict" and found[2]["code"] == "not_attending"


async def test_a_visit_cancelled_while_offline_applies_after_an_admin_restores_it(ops):
    visit, [one, _] = await planned(ops)
    batch = [op("visit.start", visit), op("station.arrive", visit, {"station_id": one["id"]})]
    cancelled = await move(ops, "tech1", visit["id"], "cancel", reason="Wrong day")
    assert cancelled.status_code == 200, cancelled.text

    found = await answers(ops, "tech1", batch)
    assert found[0]["status"] == "conflict" and found[0]["code"] == "visit_cancelled"
    assert found[1]["status"] == "skipped"
    [event] = await ops.outbox("visit.sync_conflict")
    assert event.data["reason"] == "visit_cancelled"

    restored = await move(ops, "admin", visit["id"], "restore")
    assert restored.status_code == 200, restored.text
    assert statuses(await answers(ops, "tech1", batch)) == ["applied", "applied"]


async def test_a_save_from_an_old_version_comes_back_with_the_servers_copy(ops):
    visit, _, [one, _] = await two_techs(ops)
    element = new_id()
    created = await answers(ops, "tech1", [op("element.create", visit, note(one, element))])
    assert statuses(created) == ["applied"]
    saved = await ops.http.put(
        f"{board(visit, one)}/{element}",
        json={"title": "Changed on the web", "items": [], "shared": False, "base_version": 1},
        headers=ops.bearer("tech1"),
    )
    assert saved.status_code == 200, saved.text

    [found] = await answers(ops, "tech1", [op("element.update", visit, {
        "station_id": one["id"], "element_id": element, "title": "Changed on the phone",
        "items": [], "shared": False, "base_version": 1,
    })])
    assert found["status"] == "conflict" and found["code"] == "element_changed"
    assert found["current"]["title"] == "Changed on the web" and found["current"]["version"] == 2


async def test_a_delete_then_a_late_save_comes_back_as_element_deleted(ops):
    visit, _, [one, _] = await two_techs(ops)
    element = new_id()
    await answers(ops, "tech1", [op("element.create", visit, note(one, element))])
    [gone] = await answers(ops, "tech1", [op("element.delete", visit, {
        "station_id": one["id"], "element_id": element, "base_version": 1})])
    assert gone["status"] == "applied"
    [late] = await answers(ops, "tech1", [op("element.update", visit, {
        "station_id": one["id"], "element_id": element, "title": "Too late",
        "items": [], "shared": False, "base_version": 1})])
    assert late["status"] == "conflict" and late["code"] == "element_deleted"


async def test_ending_a_visit_that_someone_else_ended_is_a_conflict(ops):
    visit, *_ = await two_techs(ops)
    ended = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert ended.status_code == 200
    # tech2's own end, made on the phone, arrives second
    own_end = op("visit.end", visit, {"additional_visit_required": True,
                                      "follow_up_notes": "More work"})
    [found] = await answers(ops, "tech2", [own_end])
    assert found["status"] == "conflict" and found["code"] == "already_ended"


async def test_a_bad_operation_is_its_own_answer(ops):
    visit, _, [one, _] = await two_techs(ops)
    first = new_id()
    batch = [
        op("element.create", visit, note(one, first, title="   ")),  # a title is needed
        op("element.create", visit, note(one, new_id())),
    ]
    found = await answers(ops, "tech1", batch)
    assert found[0]["status"] == "error" and found[0]["code"] == "title_required"
    assert found[0]["retryable"] is False
    assert found[1]["status"] == "skipped"

    odd = await answers(ops, "tech1", [
        op("element.fly", visit),
        op("station.arrive", visit, {"nope": 1}),
    ])
    assert odd[0]["code"] == "unknown_type" and odd[0]["retryable"] is False
    assert odd[1]["status"] == "skipped"
    bad = await answers(ops, "tech1", [op("station.arrive", visit, {"nope": 1})])
    assert bad[0]["status"] == "error" and bad[0]["code"] == "bad_payload"


async def test_payload_versions(ops):
    visit, _ = await planned(ops)
    [newer] = await answers(ops, "tech1", [op("visit.start", visit, v=2)])
    assert newer["code"] == "update_required" and newer["retryable"] is True
    [older] = await answers(ops, "tech1", [op("visit.start", visit, v=0)])
    assert older["code"] == "unsupported_version" and older["retryable"] is False
    got = (await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer("tech1"))).json()
    assert got["status"] == "planned"


async def test_a_visit_that_is_not_there_is_not_found_and_stops_nothing_else(ops):
    ghost = {"id": new_id()}
    visit, _ = await planned(ops)
    found = await answers(ops, "tech1", [op("visit.start", ghost), op("visit.start", visit)])
    assert found[0]["status"] == "error" and found[0]["code"] == "not_found"
    assert found[1]["status"] == "applied"


async def test_someone_elses_operation_id_is_refused(ops):
    visit, _ = await planned(ops, staff=("tech1", "tech2"))
    shared = new_id()
    first = await answers(ops, "tech1", [op("visit.start", visit, op_id=shared)])
    assert statuses(first) == ["applied"]
    [found] = await answers(ops, "tech2", [op("visit.start", visit, op_id=shared)])
    assert found["status"] == "error" and found["code"] == "not_yours"


async def test_a_batch_is_at_most_a_hundred_operations(ops):
    visit, _ = await planned(ops)
    many = [op("visit.start", visit) for _ in range(101)]
    r = await sync(ops, "tech1", many)
    assert r.status_code == 422
    assert (await sync(ops, "tech1", [])).json() == {"answers": []}


@pytest.mark.req("NFR-6")
async def test_viewers_and_clients_do_not_sync(ops):
    visit, _ = await planned(ops)
    for who in ("viewer", "client_a1"):
        r = await sync(ops, who, [op("visit.start", visit)])
        assert r.status_code == 403, who
    r = await ops.http.post("/api/v1/sync", json={"device_id": DEVICE, "ops": []})
    assert r.status_code == 401


@pytest.mark.req("OFF-7")
async def test_a_crash_after_the_transaction_changes_nothing_on_the_retry(ops, monkeypatch):
    # The server dies after an operation committed and before the answer went out: the record was
    # written in that same commit, so the phone's retry gets `duplicate` and nothing runs twice
    visit, _, [one, _] = await two_techs(ops)
    element = new_id()
    batch = [op("element.create", visit, note(one, element)),
             op("element.update", visit, {
                 "station_id": one["id"], "element_id": element, "title": "Rust, mast base",
                 "items": [], "shared": False, "base_version": 1})]

    async def die(*_args, **_kwargs):
        raise RuntimeError("the server was killed")

    with monkeypatch.context() as patched:
        patched.setattr("app.api.sync_routes.set_result", die)
        with pytest.raises(RuntimeError):
            await sync(ops, "tech1", batch)
    assert await ops.db["sync_operations"].count_documents({}) == 1  # the first op committed

    again = await answers(ops, "tech1", batch)
    assert statuses(again) == ["duplicate", "applied"]
    [shown] = (await listed(ops, "tech1", visit, one))["items"]
    assert shown["version"] == 2 and shown["title"] == "Rust, mast base"
    assert len(await ops.outbox("visit.element_added")) == 1
    assert len(await ops.outbox("visit.element_updated")) == 1
