"""The audit log for people on a real MongoDB: search, export, History and the integrity check
(AUD-4, AUD-5, AUD-6; W19-1 to W19-5)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from mms_common.events import Actor, Envelope, Resource
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS
from mms_common.time import ManualClock

from app.domain.audit import to_record
from app.domain.audit_view import own_record
from app.jobs import audit_check
from app.repo import audit, audit_checks
from tests.api.notify_support import bearer, env  # noqa: F401 - a fixture, found by name

REQ = "01900000-0000-7000-8000-0000000b0001"
VISIT = "01900000-0000-7000-8000-0000000c0001"
STATION = "01900000-0000-7000-8000-0000000d0001"
BASE = datetime(2026, 10, 21, 9, tzinfo=UTC)


def raw(type_, *, resource, data=None, actor="admin", minutes=0, org=ORG_A, before=None,
        after=None, name=None) -> bytes:
    seed = SEED_USERS[actor]
    return Envelope(
        event_id=new_id(), type=type_, occurred_at=BASE + timedelta(minutes=minutes),
        source="operations", key=resource[1], aggregate_version=1,
        actor=Actor(user_id=seed.id, name=name or seed.name, roles=list(seed.roles),
                    ip="203.0.113.24", user_agent="Chrome", device_id="dev-1"),
        org_id=org, resource=Resource(type=resource[0], id=resource[1]),
        correlation_id="trace-1", audit={"before": before, "after": after}, data=data or {},
    ).model_dump_json().encode()


@pytest_asyncio.fixture
async def trail(env):  # noqa: F811
    app, http, _, _, issuer, clock, _ = env
    events = [
        raw("request.submitted", resource=("request", REQ), actor="client_a1", minutes=0,
            data={"request_id": REQ}),
        raw("request.assigned", resource=("request", REQ), minutes=5, data={"request_id": REQ},
            before={"status": "approved", "assigned_to": None},
            after={"status": "assigned", "assigned_to": "u2"}),
        raw("visit.started", resource=("visit", VISIT), actor="tech1", minutes=10,
            data={"visit_id": VISIT, "request_id": REQ, "station_ids": [STATION]}),
        raw("visit.element_added", resource=("visit", VISIT), actor="tech1", minutes=11,
            data={"visit_id": VISIT, "request_id": REQ, "station_id": STATION}),
        raw("calibration.recorded", resource=("sensor_unit", "u1"), minutes=20,
            data={"station_id": STATION}),
        raw("station.updated", resource=("station", STATION), minutes=30,
            before={"name": "A"}, after={"name": "B"}),
        raw("request.submitted", resource=("request", "other"), actor="client_a1", minutes=40,
            name="=HYPERLINK(1)"),
    ]
    # Straight into the chain: these are shapes the readers must handle, not events to validate
    for e in events:
        await audit.record_own(app.state.audit_mongo, app.state.audit_db,
                               to_record(Envelope.model_validate_json(e), clock.now()))
    return env


async def get(http, issuer, key, url):
    return await http.get(url, headers=bearer(issuer, key))


@pytest.mark.req("AUD-4")
async def test_an_admin_searches_by_every_filter(trail):
    app, http, _, _, issuer, _, _ = trail
    r = await get(http, issuer, "admin", "/api/v1/audit/events")
    body = r.json()
    assert r.status_code == 200 and body["total"] == 7
    assert [i["seq"] for i in body["items"]] == [7, 6, 5, 4, 3, 2, 1]  # newest first
    first = body["items"][-1]
    assert first["actor"]["ip"] == "203.0.113.24" and first["hash"]

    async def found(query):
        out = await get(http, issuer, "admin", f"/api/v1/audit/events?{query}")
        assert out.status_code == 200, out.text
        return [i["seq"] for i in out.json()["items"]]

    assert await found("action=request.assigned") == [2]
    assert await found("resource_type=visit&resource_id=" + VISIT) == [4, 3]
    assert await found(f"actor={SEED_USERS['tech1'].id}") == [4, 3]
    assert await found("actor=tech") == [4, 3]
    assert await found(f"org_id={ORG_A}") == [7, 6, 5, 4, 3, 2, 1]
    assert await found("since=2026-10-21T09:10:00Z&until=2026-10-21T09:25:00Z") == [5, 4, 3]
    assert await found("actor=.*") == []  # a pattern is text, not a pattern


@pytest.mark.req("AUD-4")
async def test_paging_by_cursor_and_the_total(trail):
    _, http, _, _, issuer, _, _ = trail
    one = (await get(http, issuer, "admin", "/api/v1/audit/events?limit=3")).json()
    assert [i["seq"] for i in one["items"]] == [7, 6, 5] and one["next_cursor"] == 5
    two = (await get(http, issuer, "admin",
                     f"/api/v1/audit/events?limit=3&cursor={one['next_cursor']}")).json()
    assert [i["seq"] for i in two["items"]] == [4, 3, 2] and two["next_cursor"] == 2
    last = (await get(http, issuer, "admin", "/api/v1/audit/events?limit=3&cursor=2")).json()
    assert [i["seq"] for i in last["items"]] == [1] and last["next_cursor"] is None
    assert one["total"] == 7 and one["over_export_limit"] is False


@pytest.mark.req("NFR-6")
@pytest.mark.parametrize("who", ["tech1", "viewer", "client_a1"])
async def test_only_admins_read_the_log(trail, who):
    _, http, _, _, issuer, _, _ = trail
    for url in ("/api/v1/audit/events", "/api/v1/audit/events/export.csv"):
        assert (await get(http, issuer, who, url)).status_code == 403
    assert (await http.get("/api/v1/audit/events")).status_code == 401


@pytest.mark.req("AUD-4")
async def test_export_is_csv_safe_streamed_and_recorded_in_the_chain(trail):
    app, http, _, _, issuer, _, _ = trail
    r = await get(http, issuer, "admin", "/api/v1/audit/events/export.csv?actor=client")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    assert r.text.startswith("﻿")
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    assert [x["seq"] for x in rows] == ["1"]  # the client who typed the formula is not "client"
    r = await get(http, issuer, "admin", "/api/v1/audit/events/export.csv?action=request.submitted")
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    assert [x["seq"] for x in rows] == ["1", "7"]  # chain order
    # a name typed by a user cannot run as a formula in a spreadsheet
    assert rows[1]["actor_name"] == "'=HYPERLINK(1)"
    assert rows[0]["action"] == "request.submitted"
    # the exports themselves are in the chain, with who and what was asked
    last = await app.state.audit_db["audit_events"].find_one(sort=[("seq", -1)])
    assert last["action"] == "audit.exported" and last["seq"] == 9
    assert last["actor"]["user_id"] == SEED_USERS["admin"].id
    assert last["metadata"] == {"records": 2, "filters": {"action": "request.submitted"}}
    assert await audit.verify(app.state.audit_db) is None


@pytest.mark.req("AUD-4")
async def test_an_export_that_is_too_large_asks_for_narrower_filters(trail, monkeypatch):
    app, http, _, _, issuer, _, _ = trail
    monkeypatch.setattr("app.api.audit.EXPORT_MAX", 3)
    r = await get(http, issuer, "admin", "/api/v1/audit/events/export.csv")
    assert r.status_code == 422 and r.json()["code"] == "too_many_records"
    assert "Narrow the dates or the filters" in r.json()["detail"]
    # nothing was exported, so nothing was recorded
    exported = await app.state.audit_db["audit_events"].count_documents(
        {"action": "audit.exported"})
    assert exported == 0
    listing = (await get(http, issuer, "admin", "/api/v1/audit/events?limit=1")).json()
    assert listing["total"] == 3 and listing["over_export_limit"] is True


@pytest.mark.req("AUD-6")
@pytest.mark.parametrize("who", ["admin", "tech1", "viewer"])
async def test_staff_and_the_viewer_read_a_requests_history(trail, who):
    _, http, _, _, issuer, _, _ = trail
    r = await get(http, issuer, who, f"/api/v1/audit/resources/request/{REQ}")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    # the request's own records and its visit's, but not the board edit
    assert [i["seq"] for i in items] == [3, 2, 1]
    assert [i["action"] for i in items] == ["visit.started", "request.assigned",
                                            "request.submitted"]
    assigned = items[1]
    assert assigned["summary"] == "assigned the request"
    assert assigned["changed_fields"] == ["assigned_to", "status"]
    assert assigned["actor_name"] == SEED_USERS["admin"].name
    for hidden in ("203.0.113.24", "Chrome", "dev-1", "trace-1", "approved", "u2", "hash"):
        assert hidden not in r.text


@pytest.mark.req("AUD-6")
async def test_a_stations_history_is_the_station_not_its_visits(trail):
    _, http, _, _, issuer, _, _ = trail
    items = (await get(http, issuer, "viewer", f"/api/v1/audit/resources/station/{STATION}")
             ).json()["items"]
    assert [i["action"] for i in items] == ["station.updated", "calibration.recorded"]


@pytest.mark.req("AUD-6")
async def test_a_client_reads_no_history_and_unknown_things_are_refused(trail):
    _, http, _, _, issuer, _, _ = trail
    assert (await get(http, issuer, "client_a1",
                      f"/api/v1/audit/resources/request/{REQ}")).status_code == 403
    assert (await get(http, issuer, "admin",
                      f"/api/v1/audit/resources/user/{REQ}")).status_code == 422
    assert (await get(http, issuer, "admin",
                      "/api/v1/audit/resources/request/not-an-id")).status_code == 422
    empty = await get(http, issuer, "admin",
                      "/api/v1/audit/resources/request/01900000-0000-7000-8000-0000000eeee1")
    assert empty.json() == {"items": [], "next_cursor": None}


async def run_checks(app, clock):
    return await audit_check.run_next(
        db=app.state.db, audit_client=app.state.audit_mongo, audit_db=app.state.audit_db,
        clock=clock)


@pytest.mark.req("AUD-5")
async def test_the_integrity_check_passes_on_a_clean_chain(trail):
    app, http, _, _, issuer, clock, _ = trail
    started = await http.post("/api/v1/audit/verify", headers=bearer(issuer, "admin"))
    assert started.status_code == 202 and started.json()["status"] == "queued"
    check_id = started.json()["id"]
    assert started.json()["requested_by_name"] == SEED_USERS["admin"].name
    assert await run_checks(app, clock) is True
    assert await run_checks(app, clock) is False  # nothing else queued
    done = (await get(http, issuer, "admin", f"/api/v1/audit/checks/{check_id}")).json()
    assert (done["status"], done["checked"], done["total"], done["first_break_seq"]) == (
        "passed", 7, 7, None)
    latest = (await get(http, issuer, "admin", "/api/v1/audit/checks/latest")).json()
    assert latest["id"] == check_id
    # the check is in the chain, and the chain still verifies with it
    last = await app.state.audit_db["audit_events"].find_one(sort=[("seq", -1)])
    assert last["action"] == "audit.verified"
    assert last["metadata"]["result"] == "passed" and last["metadata"]["records"] == 7
    assert await audit.verify(app.state.audit_db) is None
    assert audit_check.chain_ok._value.get() == 1  # the gauge the alerts watch


@pytest.mark.req("AUD-5")
async def test_the_check_names_the_first_broken_record_and_nothing_else(trail):
    app, http, _, _, issuer, clock, _ = trail
    await app.state.audit_db["audit_events"].update_one(
        {"seq": 3}, {"$set": {"action": "visit.cancelled"}})  # an edit in place
    started = await http.post("/api/v1/audit/verify", headers=bearer(issuer, "admin"))
    await run_checks(app, clock)
    done = (await get(http, issuer, "admin",
                      f"/api/v1/audit/checks/{started.json()['id']}")).json()
    assert (done["status"], done["first_break_seq"], done["checked"]) == ("broken", 3, 2)
    assert set(done) == {"id", "kind", "status", "checked", "total", "first_break_seq",
                         "requested_at", "started_at", "finished_at", "requested_by_name"}
    assert audit_check.chain_ok._value.get() == 0


@pytest.mark.req("AUD-5")
async def test_a_deleted_tail_and_a_deleted_middle_are_both_found(trail):
    app, _, _, _, _, _, _ = trail
    db = app.state.audit_db

    async def nothing(_: int) -> None:
        return None

    assert await audit.verify_paged(db, nothing, page=2) is None  # pages of two
    await db["audit_events"].delete_one({"seq": 7})
    assert await audit.verify_paged(db, nothing, page=2) == 7  # the head points past the end
    await db["audit_events"].delete_one({"seq": 4})
    assert await audit.verify_paged(db, nothing, page=2) == 4


@pytest.mark.req("AUD-5")
async def test_a_record_that_arrives_during_a_check_is_not_a_break(trail):
    app, _, _, _, _, _, _ = trail
    db = app.state.audit_db
    added = False

    async def append_once(_: int) -> None:
        nonlocal added
        if not added:
            added = True
            await audit.record_own(app.state.audit_mongo, db, own_record(
                action="audit.exported", at=BASE, actor={}, correlation_id=None,
                metadata={}, event_id=new_id()))

    assert await audit.verify_paged(db, append_once, page=2) is None
    assert await db["audit_events"].count_documents({}) == 8


async def test_only_admins_start_checks_and_read_their_results(trail):
    _, http, _, _, issuer, _, _ = trail
    for who in ("tech1", "viewer", "client_a1"):
        assert (await http.post("/api/v1/audit/verify",
                                headers=bearer(issuer, who))).status_code == 403
        assert (await get(http, issuer, who, "/api/v1/audit/checks/latest")).status_code == 403
    assert (await get(http, issuer, "admin", "/api/v1/audit/checks/latest")).status_code == 404


async def test_a_check_a_dead_worker_left_running_is_taken_again(trail):
    app, _, _, _, _, clock, _ = trail
    db = app.state.db
    await audit_checks.create(db, check_id="c1", kind="manual", now=clock.now(), by=None)
    first = await audit_checks.claim_next(db, clock.now())
    assert first is not None and first["attempts"] == 1
    assert await audit_checks.claim_next(db, clock.now()) is None  # running, not stale
    later = clock.now() + audit_checks.STALE + timedelta(seconds=1)
    again = await audit_checks.claim_next(db, later)
    assert again is not None and again["attempts"] == 2


async def test_the_nightly_check_is_queued_once_a_day_from_its_hour(trail):
    app, _, _, _, _, _, _ = trail
    db = app.state.db
    before = ManualClock(datetime(2026, 10, 21, 8, 59, tzinfo=UTC))  # 03:59 in Jamaica
    after = ManualClock(datetime(2026, 10, 21, 9, 1, tzinfo=UTC))  # 04:01
    assert await audit_check.schedule_nightly(db, before, "America/Jamaica", 4) is False
    assert await audit_check.schedule_nightly(db, after, "America/Jamaica", 4) is True
    assert await audit_check.schedule_nightly(db, after, "America/Jamaica", 4) is False
    next_day = ManualClock(datetime(2026, 10, 22, 9, 1, tzinfo=UTC))
    assert await audit_check.schedule_nightly(db, next_day, "America/Jamaica", 4) is True
    check = await audit_checks.get(db, "nightly-2026-10-21")
    assert check is not None and check["kind"] == "nightly" and check["requested_by"] is None
