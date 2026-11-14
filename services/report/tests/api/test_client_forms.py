"""A client's online-form report as a PDF (PRD CRP-3, CRP-4; TRD 3.4; decision W18-10): made from
`client_report.submitted`, drawn in the worker from facts read from operations, final at once,
and handed back to operations with `report.generated`."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.events import Envelope, Resource
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS

from app.domain import client_form
from app.events import consumer
from app.jobs import render_client_form as job
from app.jobs.labels import Retry
from tests import visit_facts as vf

CLIENT_REPORT = "01900000-0000-7000-8000-00000000f101"
CLIENT = SEED_USERS["client_a1"]
REQUEST = vf.REQUEST
PICTURE, MISSING = vf.P_BEFORE, vf.P_AFTER


def submitted(report, *, report_id: str = CLIENT_REPORT, kind: str = "form", attempt: int = 1,
              request_id: str = REQUEST, ref: str = "MR-2026-0042") -> bytes:
    data = {
        "request_id": request_id, "ref": ref, "org_id": ORG_A, "station_ids": [vf.S1, vf.S2],
        "category": "inspection", "priority": "normal", "status": "in_progress",
        "title": "Rain gauge not reporting", "created_by": CLIENT.id, "assigned_staff_ids": [],
        "client_report_id": report_id, "kind": kind, "report_title": "Q3 gauge check",
        "submitted_by_id": CLIENT.id, "submitted_by_name": CLIENT.name, "attempt": attempt,
    }
    return Envelope(
        event_id=new_id(), type="client_report.submitted", occurred_at=report.clock.now(),
        source="operations", key=request_id, aggregate_version=2,
        resource=Resource(type="client_report", id=report_id), org_id=ORG_A, data=data,
    ).model_dump_json().encode()


def facts(report, report_id: str = CLIENT_REPORT, **over: Any) -> dict[str, Any]:
    return {
        "facts_version": 1, "client_report_id": report_id, "attempt": 1,
        "request": {"id": REQUEST, "ref": "MR-2026-0042", "title": "Rain gauge not reporting"},
        "org_id": ORG_A, "org_name": "Organization A", "title": "Q3 gauge check",
        "report_date": "2026-09-30", "submitted_by_name": CLIENT.name,
        "submitted_at": report.clock.now().isoformat(),
        "stations": [
            {"station_id": vf.S1, "code": "TST-001", "name": "Test Harbour", "country": "JM",
             "time_zone": "America/Jamaica"},
            {"station_id": vf.S2, "code": "TST-002", "name": "Test Hill", "country": "JM",
             "time_zone": None},
        ],
        "summary": "Readings were steady apart from a gap.",
        "observations": [{"station_id": vf.S1, "text": "Cups are worn."}],
        "data_quality_notes": "No data on the 4th.",
        "images": [{"media_id": PICTURE, "name": "gauge.jpg"},
                   {"media_id": MISSING, "name": "mast.jpg"}], **over,
    }


async def feed(report, raw: bytes) -> Outcome:
    dead: list[str] = []

    async def dlq(payload: bytes, reason: str) -> None:
        dead.append(reason)

    processor = consumer.processor(report.app.state.mongo, report.app.state.db, dlq, report.clock)
    outcome = await processor.process(raw)
    assert dead == []
    return outcome


async def forms(report) -> list[dict[str, Any]]:
    return [d async for d in report.db["reports"].find({"type": "client_form"}).sort("_id", 1)]


async def one(report) -> dict[str, Any]:
    (doc,) = await forms(report)
    return doc


async def made(report, **over: Any) -> dict[str, Any]:
    report.facts.by_client_report[CLIENT_REPORT] = facts(report, **over)
    report.media.photos[PICTURE] = vf.webp()
    await feed(report, submitted(report))
    return await one(report)


async def drawn(report) -> dict[str, Any]:
    doc = await made(report)
    assert await job.tick(report.svc) == {"queued": 1}
    assert report.jobs.queued == [job.job_id(doc["_id"])]
    await job.render_client_form(report.svc, doc["_id"])
    return await one(report)


# --- The record (CRP-3) --------------------------------------------------------------------------


@pytest.mark.req("CRP-3")
async def test_a_submitted_form_makes_one_numbered_report(report):
    doc = await made(report)
    assert doc["number"] == "CR-2026-0042-01" and doc["version"] == 1
    assert doc["status"] == "rendering" and doc["org_id"] == ORG_A and doc["request_id"] == REQUEST
    assert doc["subject_ref"] == f"client_report:{CLIENT_REPORT}" and doc["attempt"] == 1
    assert await feed(report, submitted(report)) is not None  # a repeat of the event
    assert len(await forms(report)) == 1


@pytest.mark.req("CRP-3")
async def test_the_second_report_on_a_request_has_the_next_number(report):
    await made(report)
    other = "01900000-0000-7000-8000-00000000f102"
    await feed(report, submitted(report, report_id=other))
    assert [d["number"] for d in await forms(report)] == ["CR-2026-0042-01", "CR-2026-0042-02"]
    elsewhere = "01900000-0000-7000-8000-00000000f103"
    await feed(report, submitted(report, report_id=elsewhere, request_id=new_id(),
                                 ref="MR-2026-0099"))
    assert (await forms(report))[-1]["number"] == "CR-2026-0099-01"


@pytest.mark.req("CRP-1")
async def test_a_pdf_report_is_not_drawn_here(report):
    await feed(report, submitted(report, kind="pdf"))
    assert await forms(report) == []


# --- Drawing -------------------------------------------------------------------------------------


@pytest.mark.req("CRP-3")
async def test_the_worker_draws_the_page_and_the_report_is_final(report):
    doc = await drawn(report)
    assert doc["status"] == "final" and doc["finalized_by"] == CLIENT.id
    pdf = doc["final_pdf"]
    assert pdf["key"] == f"client-forms/{doc['_id']}/final-1.pdf" and pdf["pages"] == 1
    stored = report.s3.get_object(Bucket="mms-reports", Key=pdf["key"])["Body"].read()
    assert hashlib.sha256(stored).hexdigest() == pdf["sha256"] == doc["pdf_sha256"]
    assert doc["content_hash"] == client_form.content_hash(facts(report))

    (view,) = report.renderer.forms
    assert view["number"] == "CR-2026-0042-01" and view["org_name"] == "Organization A"
    assert view["title"] == "Q3 gauge check" and view["report_date"] == "30 Sep 2026"
    assert view["stations"][0]["observation"] == "Cups are worn."
    assert view["stations"][1]["observation"] == ""
    assert view["hash"] == doc["content_hash"][:16]
    assert [i["name"] for i in view["images"]] == ["gauge.jpg", "mast.jpg"]
    assert view["images"][0]["uri"].startswith("data:image/jpeg;base64,")
    assert view["images"][1]["uri"] is None  # not there: the page says so, the report still prints

    (event,) = [e async for e in report.db["outbox"].find({"type": "report.generated"})]
    assert event["data"]["outcome"] == "ready" and event["data"]["attempt"] == 1
    assert event["data"]["client_report_id"] == CLIENT_REPORT
    assert event["data"]["report_id"] == doc["_id"] and event["data"]["pdf_sha256"] == pdf["sha256"]
    assert event["key"] == REQUEST and event["org_id"] == ORG_A
    assert "Cups are worn" not in str(event)  # no text in an event


@pytest.mark.req("CRP-3")
async def test_drawing_twice_changes_nothing(report):
    doc = await drawn(report)
    await job.render_client_form(report.svc, doc["_id"])  # finished: not claimed again
    assert len(report.renderer.forms) == 1
    assert await report.db["outbox"].count_documents({"type": "report.generated"}) == 1
    assert await job.tick(report.svc) == {"queued": 0}


@pytest.mark.req("CRP-3")
async def test_the_tick_queues_a_form_once_and_again_only_when_its_worker_is_gone(report):
    doc = await made(report)
    assert await job.tick(report.svc) == {"queued": 1}
    assert await job.tick(report.svc) == {"queued": 0}  # queued already
    report.clock.advance(minutes=20)  # the queue lost it, or the worker died
    assert await job.tick(report.svc) == {"queued": 1}
    assert report.jobs.queued == [job.job_id(doc["_id"])] * 2


async def fail_for_good(report, doc: dict[str, Any]) -> None:
    """Operations does not answer on any of the three tries; the last one gives up."""
    await job.tick(report.svc)
    report.facts.down = True
    for _ in range(2):
        with pytest.raises(Retry):
            await job.render_client_form(report.svc, doc["_id"])
        assert (await one(report))["render"]["state"] == "queued"
    await job.render_client_form(report.svc, doc["_id"])
    report.facts.down = False


@pytest.mark.req("CRP-3")
async def test_an_unreachable_operations_is_tried_again_then_the_report_fails(report):
    doc = await made(report)
    await fail_for_good(report, doc)
    failed = await one(report)
    assert failed["status"] == "render_failed" and failed["render"]["error"] == "render_failed"
    (event,) = [e async for e in report.db["outbox"].find({"type": "report.generated"})]
    assert event["data"]["outcome"] == "failed" and event["data"]["pdf_sha256"] is None
    assert failed["final_pdf"] is None and report.renderer.forms == []


@pytest.mark.req("CRP-3")
async def test_a_renderer_that_fails_is_a_failed_try(report):
    doc = await made(report)
    await job.tick(report.svc)
    report.renderer.fail = True
    with pytest.raises(Retry):
        await job.render_client_form(report.svc, doc["_id"])
    report.renderer.fail = False
    await job.render_client_form(report.svc, doc["_id"])  # it works on the next try
    assert (await one(report))["status"] == "final"


@pytest.mark.req("CRP-3")
async def test_a_report_operations_does_not_know_fails_at_once(report):
    await feed(report, submitted(report))
    (doc,) = await forms(report)
    await job.tick(report.svc)
    await job.render_client_form(report.svc, doc["_id"])
    failed = await one(report)
    assert failed["status"] == "render_failed" and failed["render"]["error"] == "unknown_report"


@pytest.mark.req("CRP-3")
async def test_the_client_may_try_again_after_a_failure(report):
    doc = await made(report)
    await fail_for_good(report, doc)
    assert (await one(report))["status"] == "render_failed"

    await feed(report, submitted(report))  # the same attempt again: nothing moves
    assert (await one(report))["status"] == "render_failed"
    await feed(report, submitted(report, attempt=2))
    again = await one(report)
    assert again["status"] == "rendering" and again["attempt"] == 2
    assert again["number"] == doc["number"] and len(await forms(report)) == 1
    await job.tick(report.svc)
    await job.render_client_form(report.svc, doc["_id"])
    done = await one(report)
    assert done["status"] == "final" and done["final_pdf"]["key"].endswith("final-2.pdf")
    events = [e["data"]["outcome"] async for e in report.db["outbox"].find(
        {"type": "report.generated"}).sort("created_at", 1)]
    assert events == ["failed", "ready"]


# --- Reading it (rules 4 and 6) ------------------------------------------------------------------


@pytest.mark.req("CRP-5")
async def test_the_client_and_staff_read_the_final_report_and_nobody_else(report):
    doc = await made(report)
    listing = await report.http.get("/api/v1/reports", params={"type": "client_form"},
                                    headers=report.bearer("client_a1"))
    assert listing.json() == []  # still being drawn: a client sees final reports only
    await job.tick(report.svc)
    await job.render_client_form(report.svc, doc["_id"])

    for who in ("client_a1", "client_a2", "tech1", "admin", "viewer"):
        got = await report.http.get(f"/api/v1/reports/{doc['_id']}", headers=report.bearer(who))
        assert got.status_code == 200, who
        body = got.json()
        assert body["type"] == "client_form" and body["status"] == "final"
        assert body["content"]["form"]["summary"] == "Readings were steady apart from a gap."
        link = await report.http.get(f"/api/v1/reports/{doc['_id']}/download",
                                     headers=report.bearer(who))
        assert link.json()["filename"] == "CR-2026-0042-01-v1.pdf"
        pdf = await report.store.get(link.json()["url"])
        assert pdf.content.startswith(b"%PDF")
    listed = await report.http.get("/api/v1/reports", params={"type": "client_form"},
                                   headers=report.bearer("client_a1"))
    assert [i["id"] for i in listed.json()] == [doc["_id"]]
    assert listed.json()[0]["pdf"]["state"] == "ready"
    assert (await report.http.get(f"/api/v1/reports/{doc['_id']}",
                                  headers=report.bearer("client_b1"))).status_code == 404
    assert ORG_B != ORG_A


@pytest.mark.req("CRP-4")
async def test_a_client_report_is_found_by_verify_and_never_reopened(report):
    doc = await drawn(report)
    sha = doc["pdf_sha256"]
    verified = await report.http.post("/api/v1/reports/verify", json={"sha256": sha})
    assert verified.json()["match"] is True and verified.json()["number"] == "CR-2026-0042-01"

    reopen = await report.http.post(f"/api/v1/reports/{doc['_id']}/reopen",
                                    json={"reason": "Wrong station"}, headers=report.bearer("admin"))
    assert reopen.status_code == 409 and reopen.json()["code"] == "not_reopenable"
    for path, body, who in (
        ("content", None, "tech1"), ("sign", None, "tech1"), ("finalize", None, "tech1"),
    ):
        method = "patch" if path == "content" else "post"
        response = await getattr(report.http, method)(
            f"/api/v1/reports/{doc['_id']}/{path}", json=body or {}, headers=report.bearer(who))
        assert response.status_code >= 400, path
    stored = await one(report)
    assert stored["status"] == "final" and stored["pdf_sha256"] == sha

