"""Summary reports on a real MongoDB and object store (PRD SUM-1 to SUM-3, CAL-4; TRD 3.4;
decisions W19-8 to W19-10): ask, follow, draw or export, download, and what a client cannot see."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS

from app.domain import summary as rules
from app.jobs import summary as job
from app.repo import summary as data_repo
from tests.conftest import PDF, STATION_1, STATION_2

T = datetime(2026, 10, 5, 12, tzinfo=UTC)
FIRST = {"from": "2026-10-01", "to": "2026-10-31"}


async def seed(report) -> None:
    db = report.db
    await db["station_facts"].insert_many([
        {"_id": STATION_1, "org_id": ORG_A, "country": "Jamaica", "status": "operational",
         "code": "=KIN-001", "name": "Kingston", "aggregate_version": 1},
        {"_id": STATION_2, "org_id": ORG_B, "country": "Barbados", "status": "offline",
         "code": "BB-BGI-001", "name": "Bridgetown", "aggregate_version": 1},
    ])
    await db["request_facts"].insert_many([
        {"_id": "r1", "ref": "MR-2026-0001", "org_id": ORG_A, "station_ids": [STATION_1],
         "category": "fault", "priority": "normal", "status": "closed", "submitted_at": T,
         "approved_at": T + timedelta(hours=7), "assigned_at": T + timedelta(days=1),
         "first_visit_at": T + timedelta(days=3), "closed_at": T + timedelta(days=9),
         "reopen_count": 0, "aggregate_version": 1},
        {"_id": "r2", "ref": "MR-2026-0002", "org_id": ORG_B, "station_ids": [STATION_2],
         "category": "calibration", "priority": "high", "status": "in_progress",
         "submitted_at": T + timedelta(days=1), "reopen_count": 0, "aggregate_version": 1},
    ])
    await db["visit_facts"].insert_many([
        {"_id": "v1", "ref": "VR-2026-0001-01", "request_id": "r1", "org_id": ORG_A,
         "status": "ended", "station_ids": [STATION_1], "ended_at": T + timedelta(days=3)},
        {"_id": "v2", "ref": "VR-2026-0002-01", "request_id": "r2", "org_id": ORG_B,
         "status": "ended", "station_ids": [STATION_2], "ended_at": T + timedelta(days=4)},
    ])
    await db["unit_facts"].insert_many([
        {"_id": "u1", "serial": "SN-A", "model_id": "m1", "status": "installed", "station_id": STATION_1,
         "due_at": report.clock.now() - timedelta(days=2)},
        {"_id": "u2", "serial": "SN-B", "model_id": "m1", "status": "installed", "station_id": STATION_2,
         "due_at": report.clock.now() + timedelta(days=5)},
    ])
    await db["model_facts"].insert_many([
        {"_id": "m1", "kind": "sensor", "manufacturer": "Vaisala", "model": "HMP155",
         "parameters": ["AT"], "interval_days": 365, "aggregate_version": 1},
    ])
    await db["installation_facts"].insert_many([
        {"_id": "i1", "unit_id": "u1", "serial": "SN-A", "model_id": "m1", "station_id": STATION_1,
         "parameter": "AT", "installed_at": T},
        {"_id": "i2", "unit_id": "u2", "serial": "SN-B", "model_id": "m1", "station_id": STATION_2,
         "parameter": "AT", "installed_at": T, "removed_at": T + timedelta(days=20)},
        {"_id": "i3", "unit_id": "u2", "serial": "SN-C", "model_id": "m1", "station_id": STATION_2,
         "parameter": "RH", "installed_at": T + timedelta(days=21)},
    ])
    await db["config_facts"].insert_many([
        {"_id": "cfg1", "station_id": STATION_1, "number": 2, "file_count": 3, "visit_id": "v1",
         "created_at": T + timedelta(days=3), "aggregate_version": 1},
        {"_id": "cfg2", "station_id": STATION_2, "number": 1, "file_count": 1, "visit_id": None,
         "created_at": T + timedelta(days=3), "aggregate_version": 1},
    ])
    await db["calibration_facts"].insert_many([
        {"_id": "c1", "sensor_unit_id": "u1", "station_id": STATION_1, "org_id": ORG_A,
         "at": T + timedelta(days=2), "result": "pass", "method": "lab", "voided": False},
        {"_id": "c2", "sensor_unit_id": "u2", "station_id": STATION_2, "org_id": ORG_B,
         "at": T + timedelta(days=2), "result": "fail", "method": "field_check", "voided": False},
    ])


async def ask(report, who: str, **body):
    return await report.http.post("/api/v1/reports/summary", headers=report.bearer(who), json=body)


async def run(report, started: dict, who: str = "admin") -> dict:
    await job.render_summary(report.svc, started["id"])
    got = await report.http.get(f"/api/v1/reports/summary/jobs/{started['id']}",
                                headers=report.bearer(who))
    body: dict = got.json()
    return body


async def download(report, finished: dict) -> bytes:
    return (await report.store.get(finished["download_url"])).content


@pytest.mark.req("SUM-1")
async def test_staff_see_every_built_type_and_a_client_three(report):
    async def names(who):
        r = await report.http.get("/api/v1/reports/summary/types", headers=report.bearer(who))
        assert r.status_code == 200, r.text
        return {t["type"] for t in r.json()}

    everything = {k.value for k in rules.Kind}
    for who in ("admin", "tech1", "viewer"):
        assert await names(who) == everything
    assert await names("client_a1") == {"station_history", "client_activity", "station_asset"}


@pytest.mark.req("SUM-1")
async def test_asking_makes_a_queued_job_once_even_when_asked_twice(report):
    await seed(report)
    first = await ask(report, "admin", type="request_turnaround", format="pdf", **FIRST)
    assert first.status_code == 202, first.text
    body = first.json()
    assert body["status"] == "queued" and body["download_url"] is None
    assert (body["period_from"], body["period_to"]) == ("2026-10-01", "2026-10-31")
    assert report.jobs.queued == [f"summary:{body['id']}"]
    again = await ask(report, "admin", type="request_turnaround", format="pdf", **FIRST)
    assert again.json()["id"] == body["id"] and len(report.jobs.queued) == 1
    other = await ask(report, "admin", type="request_turnaround", format="csv", **FIRST)
    assert other.json()["id"] != body["id"]
    record = await report.record(body["id"])
    assert record["type"] == "summary" and record["requested_by"] == SEED_USERS["admin"].id


@pytest.mark.req("SUM-2")
async def test_the_worker_draws_a_pdf_the_link_downloads(report):
    await seed(report)
    started = (await ask(report, "admin", type="request_turnaround", **FIRST)).json()
    done = await run(report, started)
    assert done["status"] == "done" and done["pages"] == 1 and done["rows"] == 1
    assert done["file_name"] == "request-turnaround_2026-10-01_2026-10-31.pdf"
    assert (await download(report, done)).startswith(PDF)
    [view] = report.renderer.summaries
    assert view["title"] == "Request turnaround" and view["generated_by"] == SEED_USERS["admin"].name
    assert "2026-10-01 to 2026-10-31" in view["filters"] and "America/Jamaica" in view["filters"]
    assert view["tables"][0]["rows"][0][0] == "MR-2026-0001"


@pytest.mark.req("SUM-2")
async def test_the_csv_is_the_main_table_safe_to_open_in_a_spreadsheet(report):
    await seed(report)
    started = (await ask(report, "admin", type="station_history", format="csv", **FIRST)).json()
    done = await run(report, started)
    assert done["status"] == "done" and done["pages"] is None
    text = (await download(report, done)).decode("utf-8")
    assert text.startswith("﻿When,Station,What,Reference,Detail")
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    # the station code that starts with "=" cannot run as a formula
    assert "'=KIN-001" in {r["Station"] for r in rows}
    assert {r["What"] for r in rows} == {"Request", "Visit", "Calibration"}
    assert rows[0]["When"].endswith("Z")  # times are ISO 8601 UTC in a file
    assert not report.renderer.summaries


@pytest.mark.req("SUM-1")
@pytest.mark.parametrize("kind", [k.value for k in rules.Kind])
async def test_every_type_runs_over_the_same_data(report, kind):
    await seed(report)
    started = (await ask(report, "admin", type=kind, format="csv", due_in_days=30, **FIRST)).json()
    done = await run(report, started)
    assert done["status"] == "done", done
    assert done["rows"] >= 1
    text = (await download(report, done)).decode("utf-8")
    assert text.startswith("﻿")


@pytest.mark.req("SUM-1")
async def test_filters_narrow_by_organization_country_and_station(report):
    await seed(report)

    async def stations(**filters):
        started = (await ask(report, "admin", type="network_status", format="csv", **filters)).json()
        done = await run(report, started)
        text = (await download(report, done)).decode().lstrip("﻿")
        return {r["Code"] for r in csv.DictReader(io.StringIO(text))}

    assert await stations() == {"'=KIN-001", "BB-BGI-001"}
    assert await stations(org_id=ORG_B) == {"BB-BGI-001"}
    assert await stations(country="Jamaica") == {"'=KIN-001"}
    assert await stations(station_ids=[STATION_2]) == {"BB-BGI-001"}


@pytest.mark.req("CAL-4")
async def test_calibration_due_takes_how_far_ahead_to_look(report):
    await seed(report)

    async def serials(days):
        started = (await ask(report, "admin", type="calibration_due", format="csv",
                             due_in_days=days)).json()
        text = (await download(report, await run(report, started))).decode().lstrip("﻿")
        return [r["Serial"] for r in csv.DictReader(io.StringIO(text))]

    assert await serials(1) == ["SN-A"]  # only the overdue one
    assert await serials(30) == ["SN-A", "SN-B"]


@pytest.mark.req("SUM-3")
@pytest.mark.req("NFR-6")
async def test_a_client_runs_two_types_for_their_own_organization_only(report):
    await seed(report)
    started = (await ask(report, "client_a1", type="station_history", format="csv", **FIRST)).json()
    done = await run(report, started, "client_a1")
    assert done["status"] == "done"
    text = (await download(report, done)).decode().lstrip("﻿")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows and {r["Station"] for r in rows} == {"'=KIN-001"}
    assert "BB-BGI-001" not in text and "MR-2026-0002" not in text and "SN-B" not in text
    record = await report.record(started["id"])
    assert record["params"]["org_id"] == ORG_A  # forced from the token
    # another organization's, whatever is asked
    other = await ask(report, "client_a1", type="client_activity", org_id=ORG_B, **FIRST)
    assert other.status_code == 404
    mine = await ask(report, "client_a1", type="client_activity", org_id=ORG_A, **FIRST)
    assert mine.status_code == 202
    their_station = await ask(report, "client_a1", type="station_history",
                              station_ids=[STATION_2], **FIRST)
    assert their_station.status_code == 404
    country_of_others = await ask(report, "client_a1", type="client_activity",
                                  country="Barbados", **FIRST)
    done = await run(report, country_of_others.json(), "client_a1")
    assert done["status"] == "done" and done["rows"] == 0  # nothing of theirs is in Barbados


@pytest.mark.req("SUM-3")
@pytest.mark.parametrize("kind", ["request_turnaround", "calibration_due", "network_status",
                                  "monthly_summary", "annual_summary"])
async def test_a_client_cannot_run_the_staff_types(report, kind):
    response = await ask(report, "client_a1", type=kind, **FIRST)
    assert response.status_code == 403 and response.json()["code"] == "not_for_clients"
    assert report.jobs.queued == []


@pytest.mark.req("SUM-1")
async def test_a_viewer_runs_reports_and_a_period_is_checked(report):
    assert (await ask(report, "viewer", type="network_status")).status_code == 202
    backwards = await ask(report, "admin", type="station_history", **{"from": "2026-10-31",
                                                                     "to": "2026-10-01"})
    assert backwards.status_code == 422 and backwards.json()["code"] == "invalid_period"
    long = await ask(report, "admin", type="station_history", **{"from": "2020-01-01",
                                                                "to": "2026-10-01"})
    assert long.status_code == 422
    missing = await ask(report, "admin", type="station_history")
    assert missing.status_code == 422 and missing.json()["code"] == "invalid_period"
    assert (await ask(report, "admin", type="owners")).status_code == 422
    unknown = await ask(report, "admin", type="network_status",
                        station_ids=["01900000-0000-7000-8000-0000000000ff"])
    assert unknown.status_code == 404


@pytest.mark.req("NFR-6")
async def test_a_summary_belongs_to_the_person_who_asked(report):
    await seed(report)
    mine = (await ask(report, "tech1", type="network_status", format="csv")).json()
    await job.render_summary(report.svc, mine["id"])
    assert (await report.http.get(f"/api/v1/reports/summary/jobs/{mine['id']}",
                                  headers=report.bearer("tech2"))).status_code == 404
    listed = await report.http.get("/api/v1/reports/summary/jobs", headers=report.bearer("tech1"))
    assert [j["id"] for j in listed.json()] == [mine["id"]]
    assert (await report.http.get("/api/v1/reports/summary/jobs",
                                  headers=report.bearer("tech2"))).json() == []
    # a label sheet job is not a summary
    labels = (await report.start()).json()
    assert (await report.http.get(f"/api/v1/reports/summary/jobs/{labels['id']}",
                                  headers=report.bearer("admin"))).status_code == 404


@pytest.mark.req("NFR-2")
async def test_a_failed_draw_and_a_report_that_is_too_long_fail_with_a_reason(report, monkeypatch):
    await seed(report)
    report.renderer.fail = True
    broken = await run(report, (await ask(report, "admin", type="network_status")).json())
    assert broken["status"] == "failed" and broken["error"] == "render_failed"
    report.renderer.fail = False
    monkeypatch.setattr(data_repo, "MAX_ROWS", 1)
    long = await run(report, (await ask(report, "admin", type="station_history", format="csv",
                                        **FIRST)).json())
    assert long["status"] == "failed" and long["error"] == "too_large"


async def test_old_summaries_and_their_files_are_removed_after_the_keep_time(report):
    await seed(report)
    old = (await ask(report, "admin", type="network_status", format="csv")).json()
    await job.render_summary(report.svc, old["id"])
    key = (await report.record(old["id"]))["result"]["key"]
    report.clock.advance(days=report.settings.summary_keep_days + 1)
    fresh = (await ask(report, "admin", type="network_status", format="pdf")).json()
    await job.render_summary(report.svc, fresh["id"])
    assert await job.purge_old(report.svc) == 1
    assert await report.db["report_jobs"].find_one({"_id": old["id"]}) is None
    assert await report.db["report_jobs"].find_one({"_id": fresh["id"]}) is not None
    listed = await report.http.get("/api/v1/reports/summary/jobs", headers=report.bearer("admin"))
    assert [j["id"] for j in listed.json()] == [fresh["id"]]
    assert key.startswith("summaries/")


@pytest.mark.req("SUM-3")
async def test_a_client_sees_their_own_sensors_in_the_station_asset_report(report):
    await seed(report)
    mine = (await ask(report, "client_a1", type="station_asset", format="csv")).json()
    done = await run(report, mine, "client_a1")
    assert done["status"] == "done" and done["rows"] == 1
    text = (await download(report, done)).decode().lstrip("\ufeff")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["Serial"] == "SN-A" and rows[0]["Model"] == "Vaisala HMP155"
    assert "SN-C" not in text and "BB-BGI-001" not in text  # another organization's sensor
    staff = (await ask(report, "admin", type="station_asset", format="csv")).json()
    both = (await download(report, await run(report, staff))).decode()
    assert "SN-A" in both and "SN-C" in both
    assert "SN-B" not in both  # taken out, so no longer installed


@pytest.mark.req("SUM-1")
async def test_configuration_history_and_sensor_reliability_for_staff(report):
    await seed(report)
    configs = await run(report, (await ask(
        report, "admin", type="configuration_history", format="csv", **FIRST)).json())
    text = (await download(report, configs)).decode().lstrip("\ufeff")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert [r["Version"] for r in rows] == ["2", "1"] or {r["Version"] for r in rows} == {"1", "2"}
    assert {r["Visit"] for r in rows} == {"VR-2026-0001-01", ""}
    reliability = await run(report, (await ask(
        report, "viewer", type="sensor_reliability", format="csv", **FIRST)).json(), "viewer")
    text = (await download(report, reliability)).decode().lstrip("\ufeff")
    [row] = list(csv.DictReader(io.StringIO(text)))
    assert row["Model"] == "Vaisala HMP155"
    assert (row["Installed"], row["Removed"], row["Failed calibrations"]) == ("3", "1", "1")
    assert row["Mean days in service"] == "20.0" and row["In service now"] == "2"
    for kind in ("configuration_history", "sensor_reliability"):
        assert (await ask(report, "client_a1", type=kind, **FIRST)).status_code == 403
