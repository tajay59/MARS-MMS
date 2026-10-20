"""Label sheets (QR-1, QR-6): the request, the job and the stored PDF."""

from __future__ import annotations

import hashlib

import pytest
from mms_common.testing.seed import SEED_USERS

from app.jobs import labels as job
from tests.conftest import PDF, STATION_1, STATION_2, UNKNOWN


@pytest.mark.req("QR-6")
async def test_an_admin_starts_a_sheet_and_the_job_is_queued(report):
    response = await report.start()
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued" and body["type"] == "labels" and body["result"] is None
    assert report.jobs.queued == [body["id"]]
    record = await report.record(body["id"])
    assert record["requested_by"] == SEED_USERS["admin"].id
    assert record["params"]["station_ids"] == [STATION_1, STATION_2]


@pytest.mark.req("QR-6")
@pytest.mark.parametrize("who", ["tech1", "viewer", "client_a1"])
async def test_only_admins_start_sheets(report, who):
    response = await report.start(who=who)
    assert response.status_code == 403
    assert report.jobs.queued == []


@pytest.mark.req("QR-6")
async def test_the_worker_draws_stores_and_the_link_downloads_the_pdf(report):
    started = (await report.start(contact_phone="+1 876 555 0100")).json()
    await job.render_labels(report.svc, started["id"])

    [(sheet, phone)] = report.renderer.calls
    assert [label.code for label in sheet] == ["JM-KIN-001", "JM-MOB-002"]
    # the QR holds the token behind the app's address, nothing else (QR-1)
    assert sheet[0].scan_url == "https://mms.example/s/tok-1"
    assert phone == "+1 876 555 0100"

    done = (await report.job(started["id"])).json()
    assert done["status"] == "done" and done["error"] is None
    result = done["result"]
    assert result["stations"] == 2 and result["pages"] == 1 and result["missing"] == []
    assert result["pdf_sha256"] == hashlib.sha256(PDF).hexdigest()

    downloaded = await report.store.get(result["download_url"])
    assert downloaded.status_code == 200 and downloaded.content == PDF
    assert "inline" in downloaded.headers["content-disposition"]


async def test_unknown_stations_are_reported_not_fatal(report):
    started = (await report.start([STATION_1, UNKNOWN, STATION_1])).json()
    await job.render_labels(report.svc, started["id"])
    result = (await report.job(started["id"])).json()["result"]
    assert result["stations"] == 1 and result["missing"] == [UNKNOWN]
    assert report.stations.calls == [[STATION_1, UNKNOWN]]  # each station once, in order


async def test_a_sheet_with_no_known_station_fails_plainly(report):
    started = (await report.start([UNKNOWN])).json()
    await job.render_labels(report.svc, started["id"])
    body = (await report.job(started["id"])).json()
    assert body["status"] == "failed" and body["error"] == "no_stations"
    assert body["result"] is None


async def test_operations_down_retries_then_fails(report):
    report.stations.down = True
    started = (await report.start()).json()
    for _ in range(report.settings.job_max_attempts - 1):
        with pytest.raises(job.Retry):
            await job.render_labels(report.svc, started["id"])
        assert (await report.job(started["id"])).json()["status"] == "queued"
    await job.render_labels(report.svc, started["id"])  # the last attempt gives up
    body = (await report.job(started["id"])).json()
    assert body["status"] == "failed" and body["error"] == "unavailable"


async def test_operations_back_in_time_finishes_the_job(report):
    report.stations.down = True
    started = (await report.start()).json()
    with pytest.raises(job.Retry):
        await job.render_labels(report.svc, started["id"])
    report.stations.down = False
    await job.render_labels(report.svc, started["id"])
    assert (await report.job(started["id"])).json()["status"] == "done"


async def test_a_render_error_fails_the_job_without_a_retry_storm(report):
    report.renderer.fail = True
    started = (await report.start()).json()
    await job.render_labels(report.svc, started["id"])
    body = (await report.job(started["id"])).json()
    assert body["status"] == "failed" and body["error"] == "render_failed"


async def test_running_a_finished_job_again_changes_nothing(report):
    started = (await report.start()).json()
    await job.render_labels(report.svc, started["id"])
    await job.render_labels(report.svc, started["id"])
    assert len(report.renderer.calls) == 1
    assert (await report.record(started["id"]))["attempts"] == 1


async def test_a_job_left_running_by_a_dead_worker_runs_again(report):
    started = (await report.start()).json()
    await report.db["report_jobs"].update_one(
        {"_id": started["id"]}, {"$set": {"status": "running", "attempts": 1}}
    )
    await job.render_labels(report.svc, started["id"])
    assert (await report.job(started["id"])).json()["status"] == "done"


@pytest.mark.req("QR-6")
async def test_the_default_phone_applies_when_the_request_has_none(report):
    report.settings.label_contact_phone = "+1 876 555 0199"
    started = (await report.start()).json()
    await job.render_labels(report.svc, started["id"])
    assert report.renderer.calls[0][1] == "+1 876 555 0199"
    blank = (await report.start(contact_phone="  ")).json()  # blank: the default too
    await job.render_labels(report.svc, blank["id"])
    assert report.renderer.calls[1][1] == "+1 876 555 0199"


TOO_MANY = [f"01900000-0000-7000-8000-{i:012x}" for i in range(201)]


@pytest.mark.parametrize("body", [
    {"station_ids": []},
    {"station_ids": ["not-an-id"]},
    {"station_ids": TOO_MANY},
    {"station_ids": [STATION_1], "contact_phone": "call me maybe"},
    {"station_ids": [STATION_1], "extra": 1},
])
async def test_bad_requests_are_refused(report, body):
    response = await report.http.post(
        "/api/v1/reports/labels", json=body, headers=report.bearer("admin")
    )
    assert response.status_code == 422
    assert report.jobs.queued == []


async def test_a_job_is_visible_only_to_whoever_asked(report):
    started = (await report.start()).json()
    assert (await report.job(started["id"], "tech1")).status_code == 404
    assert (await report.job(started["id"], "client_a1")).status_code == 403
    assert (await report.job("01900000-0000-7000-8000-0000000000ee")).status_code == 404
    assert (await report.http.get(f"/api/v1/reports/jobs/{started['id']}")).status_code == 401


async def test_responses_are_never_cached(report):
    response = await report.start()
    assert response.headers["cache-control"] == "no-store"
