"""The dashboards' figures (PRD SUM-4 to SUM-6, CAL-4, CAL-6; TRD 3.4; decision W19-7): one view
per role from the read model, scoped by organization in the repository, kept for a minute."""

from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS

from app.domain import dashboard as dash

ADMIN, TECH1, TECH2 = (SEED_USERS[k].id for k in ("admin", "tech1", "tech2"))


def station(n: int, country: str, status: str, org: str = ORG_A) -> dict:
    return {"_id": f"s{n}", "org_id": org, "country": country, "status": status,
            "code": f"S-{n}", "name": f"Station {n}", "aggregate_version": 1}


def request(n: int, status: str, org: str = ORG_A, assigned: list[str] | None = None) -> dict:
    return {"_id": f"r{n}", "ref": f"MR-2026-{n:04d}", "org_id": org, "station_ids": ["s1"],
            "category": "fault", "priority": "normal", "status": status,
            "assigned_ids": assigned or [], "aggregate_version": 1}


def draft(n: int, lead: str, ended, *, status: str = "draft", org: str = ORG_A, facts=None) -> dict:
    return {"_id": f"d{n}", "type": "visit", "status": status, "subject_ref": f"visit:v{n}",
            "number": f"VR-2026-{n:04d}-01",
            "version": 1, "visit_id": f"v{n}", "request_id": f"r{n}", "org_id": org,
            "lead_staff_id": lead, "ended_at": ended, "content": {"facts": facts}}


async def seed(report) -> None:
    now = report.clock.now()
    db = report.db
    await db["station_facts"].insert_many([
        station(1, "Jamaica", "operational"), station(2, "Jamaica", "degraded"),
        station(3, "Jamaica", "operational", ORG_B), station(4, "Barbados", "offline", ORG_B),
        station(5, "Barbados", "operational", ORG_B),
    ])
    await db["request_facts"].insert_many([
        request(1, "submitted"), request(2, "submitted", ORG_B), request(3, "approved"),
        request(4, "approved", ORG_B), request(5, "assigned", assigned=[TECH1]),
        request(6, "in_progress", assigned=[TECH1, TECH2]),
        request(7, "client_review", assigned=[TECH2]), request(8, "client_review", ORG_B),
        request(9, "closed", assigned=[TECH1]), request(10, "reopened", assigned=[TECH1]),
    ])
    await db["visit_facts"].insert_many([
        {"_id": "va", "org_id": ORG_A, "status": "planned", "staff_ids": [TECH1],
         "planned_start": now + timedelta(days=1)},
        {"_id": "vb", "org_id": ORG_B, "status": "planned", "staff_ids": [TECH2],
         "planned_start": now + timedelta(days=2)},
        {"_id": "vc", "org_id": ORG_A, "status": "planned", "staff_ids": [TECH1],
         "planned_start": now - timedelta(days=1)},  # already past: not upcoming
        {"_id": "vd", "org_id": ORG_A, "status": "ended", "staff_ids": [TECH1],
         "planned_start": now + timedelta(days=1)},
    ])
    await db["unit_facts"].insert_many([
        {"_id": "u1", "status": "installed", "due_at": now - timedelta(days=3)},  # overdue
        {"_id": "u2", "status": "installed", "due_at": now + timedelta(days=10)},  # soon
        {"_id": "u3", "status": "installed", "due_at": now + timedelta(days=90)},  # far off
        {"_id": "u4", "status": "in_stock", "due_at": now - timedelta(days=30)},  # not installed
        {"_id": "u5", "status": "installed", "due_at": None},
        {"_id": "u6", "status": "retired", "due_at": now - timedelta(days=5)},
    ])
    await db["calibration_facts"].insert_many([
        {"_id": "c1", "sensor_unit_id": "u1", "at": now - timedelta(days=2), "result": "fail",
         "voided": False},
        {"_id": "c2", "sensor_unit_id": "u2", "at": now - timedelta(days=4), "result": "fail",
         "voided": False},
        {"_id": "c3", "sensor_unit_id": "u2", "at": now - timedelta(days=1), "result": "pass",
         "voided": False},  # a later pass clears it
        {"_id": "c4", "sensor_unit_id": "u3", "at": now - timedelta(days=1), "result": "fail",
         "voided": True},  # voided: does not count
        {"_id": "c5", "sensor_unit_id": "u6", "at": now - timedelta(days=1), "result": "fail",
         "voided": False},  # retired: no one's follow-up
    ])
    facts = {"stations": [{"code": "JM-KIN-001"}],
             "staff": [{"name": "Devon Clarke", "lead": True}, {"name": "Aisha", "lead": False}]}
    await db["reports"].insert_many([
        draft(1, TECH1, now - timedelta(days=3, hours=2), facts=facts),
        draft(2, TECH2, now - timedelta(days=1)),
        draft(3, TECH1, now - timedelta(days=9), status="finalizing"),
        {**draft(4, TECH1, now, status="final"), "finalized_at": now - timedelta(days=10)},
        {**draft(5, TECH1, now), "type": "closeout", "status": "draft"},
    ])
    await db["reports"].insert_many([
        {**draft(6, TECH1, now), "status": "final", "finalized_at": now - timedelta(days=1)},
        {**draft(7, TECH1, now), "status": "final", "org_id": ORG_B,
         "finalized_at": now - timedelta(hours=1)},
        {**draft(8, TECH1, now), "type": "client_form", "status": "draft", "finalized_at": None},
        {**draft(9, TECH1, now), "type": "client_form", "status": "final",
         "number": "CR-2026-0001-01", "finalized_at": now - timedelta(days=2)},
    ])


async def view(report, who: str, query: str = "") -> dict:
    r = await report.http.get(f"/api/v1/dashboard{query}", headers=report.bearer(who))
    assert r.status_code == 200, r.text
    body: dict = r.json()
    return body


@pytest.mark.req("SUM-4")
async def test_the_admin_view_counts_everything_the_board_shows(report):
    await seed(report)
    body = await view(report, "admin")
    assert body["view"] == "admin"
    assert body["figures"] == {
        "requests_awaiting_approval": 2, "unassigned_queue": 2, "in_client_review": 2,
        "calibrations_overdue": 1, "calibrations_due_soon": 1, "failed_calibrations": 1,
        "reports_awaiting_finalization": 3,  # two drafts and one finalizing; not final, not closeout
        "upcoming_visits": 2,
    }
    by_status = {r["status"]: r["count"] for r in body["requests_by_status"]}
    assert [r["status"] for r in body["requests_by_status"]] == list(dash.OPEN_STATUSES)
    assert by_status == {"submitted": 2, "approved": 2, "assigned": 1, "scheduled": 0,
                         "in_progress": 1, "client_review": 2, "reopened": 1}
    assert body["stations_by_country"] == [
        {"country": "Jamaica", "operational": 2, "degraded": 1, "offline": 0,
         "decommissioned": 0, "total": 3},
        {"country": "Barbados", "operational": 1, "degraded": 0, "offline": 1,
         "decommissioned": 0, "total": 2},
    ]
    waiting = body["reports_awaiting"]
    assert [r["number"] for r in waiting] == ["VR-2026-0003-01", "VR-2026-0001-01",
                                              "VR-2026-0002-01"]  # the oldest first
    assert waiting[1]["lead_name"] == "Devon Clarke" and waiting[1]["station_codes"] == ["JM-KIN-001"]
    assert waiting[1]["age_days"] == 3 and waiting[2]["lead_name"] is None


@pytest.mark.req("SUM-4")
async def test_a_viewer_sees_the_admin_view_and_nothing_to_change(report):
    await seed(report)
    assert (await view(report, "viewer"))["figures"]["unassigned_queue"] == 2
    assert (await view(report, "viewer", "?view=admin"))["view"] == "admin"


@pytest.mark.req("SUM-5")
async def test_the_technician_view_is_about_their_own_work(report):
    await seed(report)
    body = await view(report, "tech1")
    assert body["view"] == "technician"
    assert body["figures"] == {
        "my_assigned": 3,  # assigned, in progress and reopened; not the closed one
        "queue": 2, "my_upcoming_visits": 1,
        "my_reports_to_finalize": 2,  # draft 1 and finalizing 3, both led by tech1
    }
    assert [r["number"] for r in body["reports_to_finalize"]] == ["VR-2026-0003-01",
                                                                 "VR-2026-0001-01"]
    other = await view(report, "tech2")
    assert other["figures"]["my_assigned"] == 1 and other["figures"]["my_reports_to_finalize"] == 1


@pytest.mark.req("SUM-6")
@pytest.mark.req("NFR-6")
async def test_the_client_view_holds_their_organization_and_no_other(report):
    await seed(report)
    body = await view(report, "client_a1")
    assert body["view"] == "client"
    assert body["figures"] == {"open_requests": 6, "awaiting_our_review": 1, "upcoming_visits": 1}
    assert body["stations"] == {"operational": 1, "degraded": 1, "offline": 0, "decommissioned": 0}
    shown = [r["number"] for r in body["recent_reports"]]
    # final reports of this organization, newest first: a visit report, the client's own form
    # report and an older visit report; not the other organization's, and not a draft
    assert shown == ["VR-2026-0006-01", "CR-2026-0001-01", "VR-2026-0004-01"]
    flat = repr(body)
    assert "VR-2026-0007-01" not in flat and "VR-2026-0008-01" not in flat
    # a second organization's client sees its own numbers
    other = await view(report, "client_b1")
    assert other["figures"]["awaiting_our_review"] == 1
    assert other["stations"]["offline"] == 1


@pytest.mark.req("NFR-6")
@pytest.mark.parametrize(("who", "asked", "status"), [
    ("viewer", "technician", 403), ("viewer", "client", 403),
    ("tech1", "admin", 403), ("tech1", "client", 403),
    ("client_a1", "admin", 403), ("client_a1", "technician", 403),
    ("admin", "client", 403),
    ("admin", "technician", 200), ("tech1", "technician", 200), ("client_a1", "client", 200),
])
async def test_a_role_asks_only_for_its_own_views(report, who, asked, status):
    r = await report.http.get(f"/api/v1/dashboard?view={asked}", headers=report.bearer(who))
    assert r.status_code == status, r.text
    if status == 403:
        assert r.json()["code"] == "wrong_view"


async def test_an_unknown_view_and_no_token_are_refused(report):
    bad = await report.http.get("/api/v1/dashboard?view=owner", headers=report.bearer("admin"))
    assert bad.status_code == 422
    assert (await report.http.get("/api/v1/dashboard")).status_code == 401


@pytest.mark.req("NFR-2")
async def test_figures_are_kept_for_a_minute_per_view_and_scope(report):
    await seed(report)
    report.settings.dashboard_cache_s = 60
    redis = report.app.state.redis
    keys = ["dash:admin", f"dash:client:{ORG_A}", f"dash:client:{ORG_B}"]
    try:
        await redis.delete(*keys)
        first = await view(report, "admin")
        await report.db["request_facts"].insert_one(request(11, "submitted"))
        assert (await view(report, "admin"))["figures"] == first["figures"]  # still the old
        # a client of another organization is not served this one's figures
        a = await view(report, "client_a1")
        b = await view(report, "client_b1")
        assert a["figures"] != b["figures"]
        report.settings.dashboard_cache_s = 0
        fresh = await view(report, "admin")
        assert fresh["figures"]["requests_awaiting_approval"] == 3
    finally:
        await redis.delete(*keys)


async def test_a_broken_cache_is_not_a_broken_dashboard(report, monkeypatch):
    await seed(report)
    report.settings.dashboard_cache_s = 60

    async def down(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(report.app.state.redis, "get", down)
    monkeypatch.setattr(report.app.state.redis, "set", down)
    assert (await view(report, "admin"))["figures"]["unassigned_queue"] == 2


async def test_the_migration_marks_old_request_rows_so_the_backfill_rewrites_them(report):
    await report.db["request_facts"].insert_many([
        {"_id": "old", "status": "approved", "aggregate_version": 7},
        {"_id": "new", "status": "approved", "assigned_ids": [], "aggregate_version": 7},
    ])
    migration = importlib.import_module("app.migrations.0006_unit_facts")
    await migration.up(report.db)
    versions = {d["_id"]: d["aggregate_version"]
                async for d in report.db["request_facts"].find()}
    assert versions == {"old": 0, "new": 7}
