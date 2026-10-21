"""Assigning, claiming, releasing and the queue, W9 (PRD REQ-7; AFD J4, J5; rules 2 to 5),
over the real app."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS

from tests.api.test_requests import act, make, two_orgs

TECH1 = SEED_USERS["tech1"].id
TECH2 = SEED_USERS["tech2"].id
ADMIN = SEED_USERS["admin"].id


async def approved(ops, station_id: str, **fields: Any) -> dict[str, Any]:
    """An admin-made request: it starts Approved, so it is in the queue."""
    return await make(ops, "admin", [station_id], org_id=ORG_A, **fields)


async def assign(ops, who: str, request_id: str, *staff: str, **json: Any):
    return await act(ops, who, request_id, "assign", staff_ids=list(staff), **json)


# --- Assigning (REQ-7, J4 step 4) --------------------------------------------------------------


@pytest.mark.req("REQ-7")
async def test_an_admin_assigns_two_people_and_the_request_becomes_assigned(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    assert set(request["actions"]) == {"claim", "assign", "cancel", "edit"}
    r = await assign(ops, "admin", request["id"], TECH1, TECH2)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["status"] == "assigned"
    assert [p["id"] for p in got["assigned_staff"]] == [TECH1, TECH2]
    assert got["assigned_staff"][0]["name"] == SEED_USERS["tech1"].name
    assert got["milestones"]["assigned_at"] is not None
    last = got["status_history"][-1]
    assert (last["from_status"], last["to_status"]) == ("approved", "assigned")
    assert last["note"] == f"Assigned to {SEED_USERS['tech1'].name}, {SEED_USERS['tech2'].name}"
    assert set(got["actions"]) == {"assign", "release", "cancel", "edit"}


@pytest.mark.req("REQ-7")
async def test_assigning_writes_the_events_in_the_same_transaction(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    await assign(ops, "admin", request["id"], TECH1)
    [event] = await ops.outbox("request.assigned")
    assert event.data["staff_ids"] == [TECH1] and event.data["claimed"] is False
    assert event.data["by_id"] == ADMIN and event.data["title"] == request["title"]
    assert event.data["created_by"] == ADMIN and event.key == request["id"]
    changed = [e for e in await ops.outbox("request.status_changed")
               if e.data["to_status"] == "assigned"]
    assert len(changed) == 1 and changed[0].data["from_status"] == "approved"


@pytest.mark.req("REQ-7")
async def test_a_client_sees_who_is_assigned_by_name_only(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    await assign(ops, "admin", request["id"], TECH1)
    seen = (await ops.http.get(f"/api/v1/requests/{request['id']}",
                               headers=ops.bearer("client_a1"))).json()
    assert seen["assigned_staff"] == [{"id": TECH1, "name": SEED_USERS["tech1"].name}]
    assert set(seen["actions"]) == {"cancel", "edit"}
    assert "@" not in str(seen)


@pytest.mark.req("REQ-7")
@pytest.mark.parametrize("who", ["tech1", "viewer", "client_a1"])
async def test_only_an_admin_assigns(ops, who):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    assert (await assign(ops, who, request["id"], TECH1)).status_code == 403


@pytest.mark.req("REQ-7")
@pytest.mark.parametrize("person", ["viewer", "client_a1", "disabled"])
async def test_a_viewer_a_client_or_a_disabled_person_cannot_be_assigned(ops, person):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    r = await assign(ops, "admin", request["id"], SEED_USERS[person].id)
    assert r.status_code == 422 and r.json()["code"] == "not_assignable"
    assert (await ops.http.get(f"/api/v1/requests/{request['id']}",
                               headers=ops.bearer("admin"))).json()["status"] == "approved"


async def test_nobody_known_is_not_assignable(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    r = await assign(ops, "admin", request["id"], new_id())
    assert r.status_code == 422 and r.json()["code"] == "not_assignable"


async def test_assigning_asks_auth_and_says_so_when_auth_is_down(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    ops.staff.down = True
    r = await assign(ops, "admin", request["id"], TECH1)
    assert r.status_code == 503
    ops.staff.down = False
    assert (await assign(ops, "admin", request["id"], TECH1)).status_code == 200
    assert ops.staff.asked == [[TECH1]]


@pytest.mark.req("REQ-7")
async def test_a_request_that_is_not_approved_cannot_be_assigned(ops):
    a, _ = await two_orgs(ops)
    submitted = await make(ops, "client_a1", [a["id"]])
    r = await assign(ops, "admin", submitted["id"], TECH1)
    assert r.status_code == 409 and r.json()["code"] == "bad_transition"


async def test_an_admin_must_pick_someone_and_no_more_than_ten(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    assert (await assign(ops, "admin", request["id"])).status_code == 422
    r = await assign(ops, "admin", request["id"], *[new_id() for _ in range(11)])
    assert r.status_code == 422


@pytest.mark.req("REQ-7")
async def test_an_admin_changes_the_staff_of_an_assigned_request(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    first = (await assign(ops, "admin", request["id"], TECH1)).json()
    r = await assign(ops, "admin", request["id"], TECH2, version=first["version"])
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["status"] == "assigned" and [p["id"] for p in got["assigned_staff"]] == [TECH2]
    assert len(got["status_history"]) == len(first["status_history"])  # no status moved
    [event] = await ops.outbox("request.staff_changed")
    assert (event.data["added"], event.data["removed"]) == ([TECH2], [TECH1])
    assert len(await ops.outbox("request.status_changed")) == 2  # created + assigned
    assert len(await ops.outbox("request.assigned")) == 1


async def test_a_stale_version_on_a_staff_change_is_refused(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    first = (await assign(ops, "admin", request["id"], TECH1)).json()
    await assign(ops, "admin", request["id"], TECH2, version=first["version"])
    r = await assign(ops, "admin", request["id"], TECH1, TECH2, version=first["version"])
    assert r.status_code == 409


async def test_assigning_the_same_people_again_is_refused(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    await assign(ops, "admin", request["id"], TECH1)
    r = await assign(ops, "admin", request["id"], TECH1)
    assert r.status_code == 409 and r.json()["code"] == "no_change"


# --- Claiming (REQ-7, J5 step 2) ---------------------------------------------------------------


@pytest.mark.req("REQ-7")
async def test_a_technician_claims_a_request_from_the_queue(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    r = await act(ops, "tech1", request["id"], "claim")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["status"] == "assigned"
    assert got["assigned_staff"] == [{"id": TECH1, "name": SEED_USERS["tech1"].name}]
    assert got["status_history"][-1]["note"] == f"Claimed by {SEED_USERS['tech1'].name}"
    assert got["actions"] == ["release"]
    [event] = await ops.outbox("request.assigned")
    assert event.data["claimed"] is True and event.data["staff_ids"] == [TECH1]
    assert event.actor.user_id == TECH1


@pytest.mark.req("REQ-7")
async def test_an_admin_can_claim_too(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    got = (await act(ops, "admin", request["id"], "claim")).json()
    assert [p["id"] for p in got["assigned_staff"]] == [ADMIN]


@pytest.mark.req("REQ-7")
async def test_the_second_person_to_claim_is_told_who_has_it(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    assert (await act(ops, "tech1", request["id"], "claim")).status_code == 200
    r = await act(ops, "tech2", request["id"], "claim")
    assert r.status_code == 409 and r.json()["code"] == "already_assigned"
    assert r.json()["claimed_by"] == [SEED_USERS["tech1"].name]
    assert len(await ops.outbox("request.assigned")) == 1


@pytest.mark.req("REQ-7")
async def test_two_claims_at_the_same_moment_have_one_winner(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    one, two = await asyncio.gather(
        act(ops, "tech1", request["id"], "claim"), act(ops, "tech2", request["id"], "claim")
    )
    assert sorted([one.status_code, two.status_code]) == [200, 409]
    loser = one if one.status_code == 409 else two
    assert loser.json()["code"] == "already_assigned" and loser.json()["claimed_by"]
    assert len(await ops.outbox("request.assigned")) == 1


@pytest.mark.req("REQ-7")
@pytest.mark.parametrize("who", ["viewer", "client_a1"])
async def test_a_viewer_or_a_client_cannot_claim(ops, who):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    assert (await act(ops, who, request["id"], "claim")).status_code == 403


async def test_only_an_approved_request_can_be_claimed(ops):
    a, _ = await two_orgs(ops)
    submitted = await make(ops, "client_a1", [a["id"]])
    r = await act(ops, "tech1", submitted["id"], "claim")
    assert r.status_code == 409 and r.json()["code"] == "bad_transition"


async def test_claiming_a_request_that_does_not_exist_is_404(ops):
    assert (await act(ops, "tech1", new_id(), "claim")).status_code == 404


# --- Releasing ---------------------------------------------------------------------------------


@pytest.mark.req("REQ-7")
async def test_a_technician_who_claimed_by_mistake_puts_it_back_in_the_queue(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    await act(ops, "tech1", request["id"], "claim")
    r = await act(ops, "tech1", request["id"], "release")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["status"] == "approved" and got["assigned_staff"] == []
    assert got["milestones"]["assigned_at"] is None
    assert got["status_history"][-1]["note"] == f"Released by {SEED_USERS['tech1'].name}"
    [event] = await ops.outbox("request.released")
    assert event.data["released_ids"] == [TECH1] and event.data["by_id"] == TECH1
    queue = (await ops.http.get("/api/v1/queue", headers=ops.bearer("tech2"))).json()
    assert [i["id"] for i in queue["items"]] == [request["id"]]
    assert (await act(ops, "tech2", request["id"], "claim")).status_code == 200


@pytest.mark.req("REQ-7")
async def test_one_of_two_releasing_leaves_the_other_on_it(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    await assign(ops, "admin", request["id"], TECH1, TECH2)
    got = (await act(ops, "tech1", request["id"], "release")).json()
    assert got["status"] == "assigned" and [p["id"] for p in got["assigned_staff"]] == [TECH2]
    [event] = await ops.outbox("request.staff_changed")
    assert event.data["removed"] == [TECH1] and event.data["added"] == []
    assert await ops.outbox("request.released") == []


@pytest.mark.req("REQ-7")
async def test_an_admin_unassigns_everyone(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    await assign(ops, "admin", request["id"], TECH1, TECH2)
    got = (await act(ops, "admin", request["id"], "release")).json()
    assert got["status"] == "approved" and got["assigned_staff"] == []
    assert got["status_history"][-1]["note"] == f"Unassigned by {SEED_USERS['admin'].name}"
    [event] = await ops.outbox("request.released")
    assert event.data["released_ids"] == [TECH1, TECH2]


@pytest.mark.req("REQ-7")
async def test_a_technician_cannot_release_someone_elses_claim(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    await act(ops, "tech1", request["id"], "claim")
    assert (await act(ops, "tech2", request["id"], "release")).status_code == 403
    mine = (await ops.http.get(f"/api/v1/requests/{request['id']}",
                               headers=ops.bearer("tech2"))).json()
    assert "release" not in mine["actions"]


async def test_a_request_nobody_holds_cannot_be_released(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    r = await act(ops, "admin", request["id"], "release")
    assert r.status_code == 409 and r.json()["code"] == "bad_transition"


@pytest.mark.req("REQ-11")
async def test_a_client_can_still_cancel_an_assigned_request_and_staff_stay_on_record(ops):
    a, _ = await two_orgs(ops)
    request = await approved(ops, a["id"])
    await act(ops, "tech1", request["id"], "claim")
    r = await act(ops, "client_a1", request["id"], "cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await act(ops, "tech1", request["id"], "release")).status_code == 409


# --- The queue (REQ-7, AFD J4 4b, J5 1) --------------------------------------------------------


@pytest.mark.req("REQ-7")
async def test_the_queue_holds_approved_unassigned_requests_oldest_approval_first(ops):
    a, b = await two_orgs(ops)
    older = await approved(ops, a["id"], title="Older one")
    ops.clock.advance(minutes=30)
    await make(ops, "client_a1", [a["id"]], title="Not approved yet")
    newer = await make(ops, "admin", [b["id"]], org_id=ORG_B, title="Newer one")
    taken = await approved(ops, a["id"], title="Taken")
    await act(ops, "tech1", taken["id"], "claim")
    r = await ops.http.get("/api/v1/queue", headers=ops.bearer("tech1"))
    assert r.status_code == 200
    page = r.json()
    assert [i["id"] for i in page["items"]] == [older["id"], newer["id"]]
    assert page["total"] == 2
    first = page["items"][0]
    assert first["approved_at"] is not None and first["org_name"] == "Organization A"
    assert first["stations"][0]["code"] == "JM-KIN-001"


@pytest.mark.req("REQ-15")
async def test_the_queue_filters_like_the_list(ops):
    a, b = await two_orgs(ops)
    jm = await approved(ops, a["id"], title="Wind cups", priority="urgent", category="fault")
    tt = await make(ops, "admin", [b["id"]], org_id=ORG_B, title="Solar panel",
                    priority="low", category="power")

    async def ids(query: str) -> list[str]:
        r = await ops.http.get(f"/api/v1/queue?{query}", headers=ops.bearer("admin"))
        assert r.status_code == 200
        return [i["id"] for i in r.json()["items"]]

    assert await ids("country=JM") == [jm["id"]]
    assert await ids("country=TT") == [tt["id"]]
    assert await ids("priority=urgent") == [jm["id"]]
    assert await ids("category=power") == [tt["id"]]
    assert await ids("q=solar") == [tt["id"]]
    assert await ids("q=MR-2026-0001") == [jm["id"]]


@pytest.mark.req("REQ-7")
async def test_a_viewer_reads_the_queue_and_a_client_has_none(ops):
    a, _ = await two_orgs(ops)
    await approved(ops, a["id"])
    assert (await ops.http.get("/api/v1/queue", headers=ops.bearer("viewer"))).status_code == 200
    # Rule 4: not 403, so a client can't tell a queue exists
    assert (await ops.http.get("/api/v1/queue", headers=ops.bearer("client_a1"))).status_code == 404
    assert (await ops.http.get("/api/v1/queue")).status_code == 401


async def test_an_empty_queue_is_an_empty_page(ops):
    r = await ops.http.get("/api/v1/queue", headers=ops.bearer("tech1"))
    assert r.json() == {"items": [], "total": 0}


# --- Workload (the Assign dialog) --------------------------------------------------------------


async def test_workload_counts_open_requests_per_person_for_admins_only(ops):
    a, _ = await two_orgs(ops)
    one = await approved(ops, a["id"])
    two = await approved(ops, a["id"])
    await assign(ops, "admin", one["id"], TECH1, TECH2)
    await assign(ops, "admin", two["id"], TECH1)
    cancelled = await approved(ops, a["id"])
    await assign(ops, "admin", cancelled["id"], TECH2)
    await act(ops, "admin", cancelled["id"], "cancel")  # finished work is not workload
    r = await ops.http.get("/api/v1/requests/workload", headers=ops.bearer("admin"))
    assert r.status_code == 200
    assert r.json() == {"open_requests": {TECH1: 2, TECH2: 1}}
    assert (await ops.http.get("/api/v1/requests/workload",
                               headers=ops.bearer("tech1"))).status_code == 403
