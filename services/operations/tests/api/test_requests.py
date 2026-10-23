"""Maintenance requests, W8 (PRD REQ-1, REQ-2, REQ-4 to REQ-6, REQ-8, REQ-11, REQ-15, REQ-16;
rules 2 to 5): create, list, read, edit, approve, deny and cancel, over the real app."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS

from tests.conftest import ORG_C


def body(station_ids: list[str], /, **fields: Any) -> dict[str, Any]:
    return {
        "title": "Wind sensor stuck", "description": "The cups do not turn.",
        "category": "fault", "priority": "high", "station_ids": station_ids, **fields,
    }


async def make(ops, who: str, station_ids: list[str], **fields: Any) -> dict[str, Any]:
    response = await ops.http.post(
        "/api/v1/requests", json=body(station_ids, **fields), headers=ops.bearer(who)
    )
    assert response.status_code in (200, 201), response.text
    data: dict[str, Any] = response.json()
    return data


async def act(ops, who: str, request_id: str, verb: str, **json: Any):
    return await ops.http.post(
        f"/api/v1/requests/{request_id}/{verb}", json=json, headers=ops.bearer(who)
    )


async def two_orgs(ops) -> tuple[dict[str, Any], dict[str, Any]]:
    a = await ops.station(code="JM-KIN-001", owner_org_id=ORG_A)
    b = await ops.station(code="TT-POS-001", owner_org_id=ORG_B, country="TT",
                          time_zone="America/Port_of_Spain")
    return a, b


# --- Creating (REQ-1, REQ-2, REQ-4) -----------------------------------------------------------


@pytest.mark.req("REQ-1")
@pytest.mark.req("REQ-4")
async def test_a_client_submits_a_request_for_their_own_stations(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    assert created["status"] == "submitted"
    assert created["ref"] == "MR-2026-0001"
    assert created["org_id"] == ORG_A and created["org_name"] == "Organization A"
    assert created["stations"] == [
        {"id": a["id"], "code": "JM-KIN-001", "name": "Kingston Harbour", "country": "JM"}
    ]
    assert created["requested_by"] == {"id": SEED_USERS["client_a1"].id,
                                       "name": SEED_USERS["client_a1"].name}
    assert [(h["from_status"], h["to_status"]) for h in created["status_history"]] \
        == [(None, "submitted")]
    assert created["milestones"]["submitted_at"] is not None
    assert created["milestones"]["approved_at"] is None
    assert set(created["actions"]) == {"cancel", "edit"}
    second = await make(ops, "client_a1", [a["id"]])
    assert second["ref"] == "MR-2026-0002"


@pytest.mark.req("REQ-4")
async def test_the_number_starts_again_each_year(ops):
    a, _ = await two_orgs(ops)
    assert (await make(ops, "client_a1", [a["id"]]))["ref"] == "MR-2026-0001"
    ops.clock.advance(days=100)  # into 2027
    assert (await make(ops, "client_a1", [a["id"]]))["ref"] == "MR-2027-0001"


@pytest.mark.req("REQ-1")
async def test_a_request_can_cover_several_stations(ops):
    a, _ = await two_orgs(ops)
    a2 = await ops.station(code="JM-KIN-002", owner_org_id=ORG_A)
    created = await make(ops, "client_a1", [a["id"], a2["id"], a["id"]])  # a repeat is dropped
    assert [s["code"] for s in created["stations"]] == ["JM-KIN-001", "JM-KIN-002"]


@pytest.mark.req("REQ-2")
async def test_an_admin_creates_for_an_organization_and_it_starts_approved(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "admin", [a["id"]], org_id=ORG_A)
    assert created["status"] == "approved"
    assert created["milestones"]["approved_at"] is not None
    assert [(h["from_status"], h["to_status"]) for h in created["status_history"]] \
        == [(None, "approved")]
    submitted = (await ops.outbox("request.submitted"))[0]
    assert submitted.data["by_admin"] is True


async def test_an_admin_must_name_an_active_organization_that_owns_every_station(ops):
    a, b = await two_orgs(ops)
    post = lambda **f: ops.http.post(  # noqa: E731
        "/api/v1/requests", json=body([a["id"]], **f), headers=ops.bearer("admin")
    )
    assert (await post()).status_code == 422  # no organization
    assert (await post(org_id=ORG_C)).status_code == 422  # inactive
    response = await ops.http.post(
        "/api/v1/requests", json=body([a["id"], b["id"]], org_id=ORG_A),
        headers=ops.bearer("admin"),
    )
    assert response.status_code == 422  # b is organization B's
    assert response.json()["code"] == "unknown_station"


@pytest.mark.req("NFR-6")
async def test_a_client_cannot_use_another_organizations_station_or_organization(ops):
    a, b = await two_orgs(ops)
    response = await ops.http.post("/api/v1/requests", json=body([b["id"]]),
                                   headers=ops.bearer("client_a1"))
    assert response.status_code == 422
    assert "TT-POS-001" not in response.text  # nothing about it leaks
    unknown = await ops.http.post("/api/v1/requests", json=body([new_id()]),
                                  headers=ops.bearer("client_a1"))
    assert unknown.status_code == 422 and unknown.json()["code"] == response.json()["code"]
    other_org = await ops.http.post("/api/v1/requests", json=body([a["id"]], org_id=ORG_B),
                                    headers=ops.bearer("client_a1"))
    assert other_org.status_code == 422


async def test_technicians_and_viewers_cannot_create_requests(ops):
    a, _ = await two_orgs(ops)
    for who in ("tech1", "viewer"):
        response = await ops.http.post("/api/v1/requests", json=body([a["id"]]),
                                       headers=ops.bearer(who))
        assert response.status_code == 403, who


@pytest.mark.parametrize("change", [
    {"title": "  "}, {"title": "x" * 201}, {"description": ""}, {"category": "weather"},
    {"priority": "now"}, {"station_ids": []}, {"unknown": 1},
])
async def test_bad_input_is_refused(ops, change):
    a, _ = await two_orgs(ops)
    response = await ops.http.post("/api/v1/requests", json=body([a["id"]], **change),
                                   headers=ops.bearer("client_a1"))
    assert response.status_code == 422


@pytest.mark.req("REQ-1")
async def test_sending_the_same_id_again_returns_the_same_request(ops):
    """Rule 9: the device makes the ID, so a retry on a poor connection can't duplicate."""
    a, _ = await two_orgs(ops)
    request_id = new_id()
    first = await ops.http.post("/api/v1/requests", json=body([a["id"]], id=request_id),
                                headers=ops.bearer("client_a1"))
    again = await ops.http.post("/api/v1/requests", json=body([a["id"]], id=request_id),
                                headers=ops.bearer("client_a1"))
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"] == request_id
    assert first.json()["ref"] == again.json()["ref"]
    assert await ops.db["requests"].count_documents({}) == 1
    assert len(await ops.outbox("request.submitted")) == 1
    other = await ops.http.post("/api/v1/requests", json=body([a["id"]], id=request_id),
                                headers=ops.bearer("admin"))
    assert other.status_code == 409 or other.status_code == 422


async def test_two_sends_of_the_same_id_at_once_make_one_request(ops):
    a, _ = await two_orgs(ops)
    request_id = new_id()
    send = lambda: ops.http.post(  # noqa: E731
        "/api/v1/requests", json=body([a["id"]], id=request_id), headers=ops.bearer("client_a1")
    )
    first, second = await asyncio.gather(send(), send())
    assert sorted([first.status_code, second.status_code]) == [200, 201]
    assert await ops.db["requests"].count_documents({}) == 1
    assert (await ops.db["counters"].find_one({"_id": "MR-2026"}))["seq"] == 1


@pytest.mark.req("AUD-1")
async def test_creating_writes_both_events_in_the_same_transaction(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    submitted = await ops.outbox("request.submitted")
    changed = await ops.outbox("request.status_changed")
    assert len(submitted) == len(changed) == 1
    assert submitted[0].key == created["id"] and submitted[0].org_id == ORG_A
    assert submitted[0].aggregate_version == 1
    assert submitted[0].data == {
        "request_id": created["id"], "ref": created["ref"], "org_id": ORG_A,
        "station_ids": [a["id"]], "category": "fault", "priority": "high",
        "status": "submitted", "by_admin": False, "title": "Wind sensor stuck",
        "created_by": SEED_USERS["client_a1"].id, "assigned_staff_ids": [],
        "milestones": {"submitted_at": "2026-10-18T12:00:00Z"}, "reopen_count": 0,
    }
    assert changed[0].data["from_status"] is None and changed[0].data["to_status"] == "submitted"
    # the status history points at the event that made it
    assert created["status_history"][0] is not None
    stored = await ops.db["requests"].find_one({"_id": created["id"]})
    assert stored["status_history"][0]["event_id"] == changed[0].event_id


# --- Reading and listing (REQ-8, REQ-15) ------------------------------------------------------


@pytest.mark.req("REQ-8")
@pytest.mark.req("NFR-6")
async def test_a_client_sees_only_their_organizations_requests(ops):
    a, b = await two_orgs(ops)
    mine = await make(ops, "client_a1", [a["id"]])
    theirs = await make(ops, "client_b1", [b["id"]])
    listing = await ops.http.get("/api/v1/requests", headers=ops.bearer("client_a1"))
    assert [r["id"] for r in listing.json()["items"]] == [mine["id"]]
    assert listing.json()["total"] == 1
    assert (await ops.http.get(f"/api/v1/requests/{mine['id']}",
                               headers=ops.bearer("client_a1"))).status_code == 200
    response = await ops.http.get(f"/api/v1/requests/{theirs['id']}",
                                  headers=ops.bearer("client_a1"))
    assert response.status_code == 404  # rule 4: not 403
    assert theirs["ref"] not in response.text
    # asking for the other organization's list, by filter, finds nothing either
    other = await ops.http.get(f"/api/v1/requests?org_id={ORG_B}", headers=ops.bearer("client_a1"))
    assert other.json()["items"] == [] and other.json()["total"] == 0


async def test_staff_see_every_request_and_viewers_have_no_actions(ops):
    a, b = await two_orgs(ops)
    mine = await make(ops, "client_a1", [a["id"]])
    theirs = await make(ops, "client_b1", [b["id"]])
    for who in ("tech1", "admin", "viewer"):
        listing = await ops.http.get("/api/v1/requests", headers=ops.bearer(who))
        assert {r["id"] for r in listing.json()["items"]} == {mine["id"], theirs["id"]}
    viewer = await ops.http.get(f"/api/v1/requests/{mine['id']}", headers=ops.bearer("viewer"))
    assert viewer.json()["actions"] == []
    technician = await ops.http.get(f"/api/v1/requests/{mine['id']}", headers=ops.bearer("tech1"))
    assert technician.json()["actions"] == []  # a technician claims once it is approved (W9)
    admin = await ops.http.get(f"/api/v1/requests/{mine['id']}", headers=ops.bearer("admin"))
    assert set(admin.json()["actions"]) == {"approve", "deny", "cancel", "edit"}


@pytest.mark.req("REQ-15")
async def test_the_list_filters_and_pages(ops):
    a, b = await two_orgs(ops)
    first = await make(ops, "client_a1", [a["id"]], title="Rain gauge blocked", category="fault",
                       priority="low")
    ops.clock.advance(days=2)
    second = await make(ops, "client_a1", [a["id"]], title="Annual inspection",
                        category="inspection", priority="normal")
    ops.clock.advance(days=2)
    third = await make(ops, "client_b1", [b["id"]], title="Modem offline",
                       category="communications", priority="urgent")
    await act(ops, "admin", second["id"], "approve")

    async def ids(query: str) -> list[str]:
        response = await ops.http.get(f"/api/v1/requests?{query}", headers=ops.bearer("admin"))
        assert response.status_code == 200, response.text
        return [r["id"] for r in response.json()["items"]]

    assert await ids("") == [third["id"], second["id"], first["id"]]  # newest first
    assert await ids("status=approved") == [second["id"]]
    assert await ids("status=approved&status=submitted") == [third["id"], second["id"],
                                                             first["id"]]
    assert await ids(f"org_id={ORG_B}") == [third["id"]]
    assert await ids("country=TT") == [third["id"]]
    assert await ids(f"station_id={a['id']}") == [second["id"], first["id"]]
    assert await ids("category=inspection") == [second["id"]]
    assert await ids("priority=urgent") == [third["id"]]
    assert await ids("q=gauge") == [first["id"]]
    assert await ids(f"q={third['ref']}") == [third["id"]]
    assert await ids("q=.*") == []  # input is text, never an operator (rule 12)
    assert await ids("from=2026-10-20&to=2026-10-20") == [second["id"]]  # both days included
    assert await ids("from=2026-10-20") == [third["id"], second["id"]]
    assert (await ops.http.get("/api/v1/requests?status=nope",
                               headers=ops.bearer("admin"))).status_code == 422

    page = await ops.http.get("/api/v1/requests?limit=2", headers=ops.bearer("admin"))
    assert [r["id"] for r in page.json()["items"]] == [third["id"], second["id"]]
    assert page.json()["total"] == 3 and page.json()["next_after"] == second["id"]
    rest = await ops.http.get(f"/api/v1/requests?limit=2&after={second['id']}",
                              headers=ops.bearer("admin"))
    assert [r["id"] for r in rest.json()["items"]] == [first["id"]]
    assert rest.json()["next_after"] is None


# --- Approving, denying (REQ-6) ---------------------------------------------------------------


@pytest.mark.req("REQ-6")
async def test_an_admin_approves(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    ops.clock.advance(minutes=30)
    response = await act(ops, "admin", created["id"], "approve")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "approved" and data["version"] == 2
    assert [(h["from_status"], h["to_status"]) for h in data["status_history"]] \
        == [(None, "submitted"), ("submitted", "approved")]
    assert data["status_history"][1]["by"]["name"] == SEED_USERS["admin"].name
    assert data["milestones"]["approved_at"] is not None  # REQ-16
    assert set(data["actions"]) == {"cancel", "edit", "claim", "assign"}  # W9
    approved = await ops.outbox("request.approved")
    changed = [e for e in await ops.outbox("request.status_changed") if e.aggregate_version == 2]
    assert len(approved) == 1 and len(changed) == 1
    assert approved[0].aggregate_version == 2
    assert (changed[0].data["from_status"], changed[0].data["to_status"]) \
        == ("submitted", "approved")
    assert approved[0].audit["before"]["status"] == "submitted"
    assert approved[0].audit["after"]["status"] == "approved"


@pytest.mark.req("REQ-6")
async def test_approving_twice_is_refused(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    assert (await act(ops, "admin", created["id"], "approve")).status_code == 200
    again = await act(ops, "admin", created["id"], "approve")
    assert again.status_code == 409 and again.json()["code"] == "bad_transition"
    assert len(await ops.outbox("request.approved")) == 1  # nothing was written


@pytest.mark.req("REQ-6")
async def test_only_an_admin_approves_or_denies(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    for who in ("client_a1", "tech1", "viewer"):
        assert (await act(ops, who, created["id"], "approve")).status_code == 403, who
        assert (await act(ops, who, created["id"], "deny", reason="no")).status_code == 403, who
    assert (await ops.http.get(f"/api/v1/requests/{created['id']}",
                               headers=ops.bearer("admin"))).json()["status"] == "submitted"


@pytest.mark.req("REQ-6")
async def test_a_denial_needs_a_reason_and_the_client_sees_it(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    for reason in ("", "   "):
        assert (await act(ops, "admin", created["id"], "deny", reason=reason)).status_code == 422
    assert (await act(ops, "admin", created["id"], "deny")).status_code == 422
    response = await act(ops, "admin", created["id"], "deny", reason="  Out of scope  ")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "denied"
    seen = await ops.http.get(f"/api/v1/requests/{created['id']}", headers=ops.bearer("client_a1"))
    assert seen.json()["denial_reason"] == "Out of scope"
    assert seen.json()["status_history"][-1]["note"] == "Out of scope"
    assert seen.json()["actions"] == []
    denied = (await ops.outbox("request.denied"))[0]
    assert denied.data["reason"] == "Out of scope"
    # a denied request is done: nothing moves it
    for verb, extra in (("approve", {}), ("cancel", {}), ("deny", {"reason": "again"})):
        assert (await act(ops, "admin", created["id"], verb, **extra)).status_code == 409


async def test_approve_and_deny_at_the_same_moment_only_one_wins(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    approve, deny = await asyncio.gather(
        act(ops, "admin", created["id"], "approve"),
        act(ops, "admin", created["id"], "deny", reason="No"),
    )
    codes = sorted([approve.status_code, deny.status_code])
    assert codes == [200, 409], (approve.text, deny.text)
    loser = approve if approve.status_code == 409 else deny
    assert loser.json()["code"] in ("request_changed", "bad_transition")
    final = (await ops.http.get(f"/api/v1/requests/{created['id']}",
                                headers=ops.bearer("admin"))).json()
    assert len(final["status_history"]) == 2
    # one specific event and one status event, from the winner only
    assert len(await ops.outbox("request.approved")) + len(await ops.outbox("request.denied")) == 1


# --- Cancelling (REQ-11) ----------------------------------------------------------------------


@pytest.mark.req("REQ-11")
async def test_a_client_cancels_their_own_request_up_to_assigned(ops):
    a, _ = await two_orgs(ops)
    for prepare in (None, "approved", "assigned"):
        created = await make(ops, "client_a1", [a["id"]])
        if prepare:
            await ops.db["requests"].update_one({"_id": created["id"]},
                                                {"$set": {"status": prepare}})
        response = await act(ops, "client_a1", created["id"], "cancel")
        assert response.status_code == 200, (prepare, response.text)
        assert response.json()["status"] == "cancelled"
        assert response.json()["actions"] == []
    event = (await ops.outbox("request.cancelled"))[0]
    assert event.data["cancelled_by"] == "client" and event.data["reason"] is None


@pytest.mark.req("REQ-11")
@pytest.mark.req("NFR-6")
async def test_a_client_cannot_cancel_another_organizations_request(ops):
    _, b = await two_orgs(ops)
    theirs = await make(ops, "client_b1", [b["id"]])
    response = await act(ops, "client_a1", theirs["id"], "cancel")
    assert response.status_code == 404
    assert (await ops.http.get(f"/api/v1/requests/{theirs['id']}",
                               headers=ops.bearer("admin"))).json()["status"] == "submitted"


@pytest.mark.req("REQ-11")
async def test_once_work_is_planned_only_an_admin_cancels_and_with_a_reason(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    for status in ("scheduled", "in_progress", "client_review"):
        await ops.db["requests"].update_one({"_id": created["id"]}, {"$set": {"status": status}})
        assert (await act(ops, "client_a1", created["id"], "cancel",
                          reason="changed my mind")).status_code == 403, status
        assert (await act(ops, "admin", created["id"], "cancel")).status_code == 422, status
    response = await act(ops, "admin", created["id"], "cancel", reason="Station removed")
    assert response.status_code == 200, response.text
    assert response.json()["cancel_reason"] == "Station removed"
    assert response.json()["status_history"][-1]["from_status"] == "client_review"
    event = (await ops.outbox("request.cancelled"))[0]
    assert event.data["cancelled_by"] == "admin" and event.data["reason"] == "Station removed"


async def test_technicians_and_viewers_cannot_cancel(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    for who in ("tech1", "viewer"):
        assert (await act(ops, who, created["id"], "cancel")).status_code == 403, who


async def test_a_finished_request_cannot_be_cancelled(ops):
    a, _ = await two_orgs(ops)
    for status in ("closed", "cancelled", "denied"):
        created = await make(ops, "client_a1", [a["id"]])
        await ops.db["requests"].update_one({"_id": created["id"]}, {"$set": {"status": status}})
        for who in ("client_a1", "admin"):
            response = await act(ops, who, created["id"], "cancel", reason="x")
            assert response.status_code == 409, (status, who)


# --- Editing (REQ-11) -------------------------------------------------------------------------


async def patch(ops, who: str, request_id: str, **json: Any):
    return await ops.http.patch(f"/api/v1/requests/{request_id}", json=json,
                                headers=ops.bearer(who))


@pytest.mark.req("REQ-11")
async def test_a_client_edits_their_request_and_the_change_is_recorded(ops):
    a, _ = await two_orgs(ops)
    a2 = await ops.station(code="JM-KIN-002", owner_org_id=ORG_A)
    created = await make(ops, "client_a1", [a["id"]])
    response = await patch(ops, "client_a1", created["id"], version=1, title="  New title ",
                           priority="urgent", station_ids=[a["id"], a2["id"]])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "New title" and data["priority"] == "urgent"
    assert [s["code"] for s in data["stations"]] == ["JM-KIN-001", "JM-KIN-002"]
    assert data["version"] == 2 and data["status"] == "submitted"
    assert data["ref"] == created["ref"]
    event = (await ops.outbox("request.updated"))[0]
    assert event.data["changed_fields"] == ["title", "priority", "station_ids"]
    assert event.audit["before"]["title"] == "Wind sensor stuck"
    assert event.audit["after"]["title"] == "New title"


@pytest.mark.req("REQ-11")
async def test_an_edit_that_changes_nothing_writes_nothing(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    response = await patch(ops, "client_a1", created["id"], version=1, title="Wind sensor stuck")
    assert response.status_code == 200 and response.json()["version"] == 1
    assert await ops.outbox("request.updated") == []
    stale = await patch(ops, "client_a1", created["id"], version=7, title="Wind sensor stuck")
    assert stale.status_code == 409


@pytest.mark.req("REQ-11")
async def test_two_edits_from_the_same_version_conflict(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    assert (await patch(ops, "client_a1", created["id"], version=1, title="One")).status_code == 200
    second = await patch(ops, "client_a1", created["id"], version=1, title="Two")
    assert second.status_code == 409 and second.json()["code"] == "version_conflict"


@pytest.mark.req("REQ-11")
async def test_a_client_cannot_edit_once_work_is_under_way_but_an_admin_can(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    await ops.db["requests"].update_one({"_id": created["id"]}, {"$set": {"status": "in_progress"}})
    refused = await patch(ops, "client_a1", created["id"], version=1, title="Late edit")
    assert refused.status_code == 422 and refused.json()["code"] == "request_locked"
    allowed = await patch(ops, "admin", created["id"], version=1, title="Admin edit")
    assert allowed.status_code == 200 and allowed.json()["title"] == "Admin edit"
    await ops.db["requests"].update_one({"_id": created["id"]}, {"$set": {"status": "closed"}})
    done = await patch(ops, "admin", created["id"], version=2, title="Too late")
    assert done.status_code == 422 and done.json()["code"] == "request_finished"


async def test_edits_are_checked_like_new_requests(ops):
    a, b = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    for change in ({"title": "  "}, {"station_ids": []}, {"station_ids": [b["id"]]},
                   {"title": None}, {"category": "weather"}):
        response = await patch(ops, "client_a1", created["id"], version=1, **change)
        assert response.status_code == 422, change
    # an admin can't move a request to another organization's station either
    assert (await patch(ops, "admin", created["id"], version=1,
                        station_ids=[b["id"]])).status_code == 422


@pytest.mark.req("NFR-6")
async def test_who_may_edit_and_whose(ops):
    a, b = await two_orgs(ops)
    theirs = await make(ops, "client_b1", [b["id"]])
    assert (await patch(ops, "client_a1", theirs["id"], version=1, title="x")).status_code == 404
    mine = await make(ops, "client_a1", [a["id"]])
    for who in ("tech1", "viewer"):
        assert (await patch(ops, who, mine["id"], version=1, title="x")).status_code == 403, who


# --- Backfill ---------------------------------------------------------------------------------


async def test_the_snapshot_serves_requests_like_the_events(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    await act(ops, "admin", created["id"], "approve")
    response = await ops.http.get("/internal/snapshot/requests", headers=ops.service("report"))
    assert response.status_code == 200, response.text
    [item] = response.json()["items"]
    milestones = item.pop("milestones")  # the read model keeps the request's own milestone times
    assert set(milestones) == {"submitted_at", "approved_at"}
    assert item == {
        "request_id": created["id"], "ref": created["ref"], "org_id": ORG_A,
        "station_ids": [a["id"]], "category": "fault", "priority": "high", "status": "approved",
        "title": "Wind sensor stuck", "created_by": SEED_USERS["client_a1"].id,
        "assigned_staff_ids": [], "reopen_count": 0, "aggregate_version": 2,
    }
    assert (await ops.http.get("/internal/snapshot/requests",
                               headers=ops.bearer("admin"))).status_code in (401, 403)


async def test_requests_never_sit_in_a_cache(ops):
    a, _ = await two_orgs(ops)
    created = await make(ops, "client_a1", [a["id"]])
    response = await ops.http.get(f"/api/v1/requests/{created['id']}",
                                  headers=ops.bearer("client_a1"))
    assert response.headers["cache-control"] == "no-store"
