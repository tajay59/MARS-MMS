"""A request's close-out report (PRD RPT-8, RPT-6; TRD 3.4; decisions W18-11, W18-12): made from
`request.closed`, drawn in the worker from facts read from operations, final at once, replaced by
version n + 1 when a visit report is corrected after the request closed."""

from __future__ import annotations

import base64
import hashlib
import io
from datetime import timedelta
from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.events import Envelope, Resource
from mms_common.ids import new_id
from mms_common.mongo import in_transaction
from mms_common.testing.seed import ORG_A, SEED_USERS
from PIL import Image

from app.domain import closeout
from app.events import closeout_consumer, consumer
from app.jobs import render_closeout as job
from app.jobs.labels import Retry
from tests import visit_facts as vf

REQUEST = vf.REQUEST
REPORT_1 = "01900000-0000-7000-8000-00000000f201"


def png_b64() -> str:
    out = io.BytesIO()
    Image.new("RGBA", (300, 100), (20, 28, 60, 255)).save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode()


def closed_event(report, *, outcome: str = "accepted") -> bytes:
    data = {
        "request_id": REQUEST, "ref": "MR-2026-0042", "org_id": ORG_A,
        "station_ids": [vf.S1], "category": "inspection", "priority": "normal",
        "status": "closed", "title": "Rain gauge not reporting", "created_by": None,
        "assigned_staff_ids": [], "outcome": outcome, "auto_closed": outcome == "auto_closed",
        "by_id": None if outcome == "auto_closed" else SEED_USERS["client_a1"].id,
    }
    return Envelope(
        event_id=new_id(), type="request.closed", occurred_at=report.clock.now(),
        source="operations", key=REQUEST, aggregate_version=9,
        resource=Resource(type="request", id=REQUEST), org_id=ORG_A, data=data,
    ).model_dump_json().encode()


def facts(report, *, version: int = 1, outcome: str = "accepted") -> dict[str, Any]:
    at = report.clock.now().isoformat()
    accepted = outcome == "accepted"
    return {
        "facts_version": 2,
        "request": {
            "id": REQUEST, "ref": "MR-2026-0042", "title": "Rain gauge not reporting",
            "description": "It reads zero", "category": "inspection", "priority": "normal",
            "status": "closed", "org_id": ORG_A, "org_name": "Organization A",
            "requester_name": "Una Client", "created_at": "2026-09-01T14:00:00Z",
            "milestones": {"closed_at": at}, "reopen_count": 0,
        },
        "stations": [{"station_id": vf.S1, "code": "TST-001", "name": "Test Harbour",
                      "country": "JM", "time_zone": "America/Jamaica"}],
        "timeline": [
            {"from": None, "to": "submitted", "at": "2026-09-01T14:00:00Z",
             "by_name": "Una Client", "note": None},
            {"from": "client_review", "to": "closed", "at": at,
             "by_name": "Una Client" if accepted else None,
             "note": "Looks right" if accepted else "Closed automatically"},
        ],
        "visits": [{
            "visit_id": vf.VISIT, "ref": "VR-2026-0042-02", "status": "ended",
            "started_at": "2026-09-05T13:00:00Z", "ended_at": "2026-09-05T17:00:00Z",
            "lead_name": "Test Lead", "report_id": REPORT_1, "report_version": version,
            "report_status": "final",
        }],
        "client_reports": [{
            "id": "01900000-0000-7000-8000-00000000f301", "kind": "form",
            "title": "Gauge check", "report_date": "2026-09-30",
            "submitted_by_name": "Una Client", "submitted_at": "2026-09-30T15:00:00Z",
            "report_id": None,
        }],
        "comments": [{"author_name": "Una Client", "author_role": "client",
                      "body": "Please check the mast", "created_at": "2026-09-02T10:00:00Z"}],
        "decision": {
            "outcome": outcome, "by_id": SEED_USERS["client_a1"].id if accepted else None,
            "by_name": "Una Client" if accepted else None, "at": at,
            "reviewing": (report.clock.now() - timedelta(days=30)).isoformat(),
            "comment": "Looks right" if accepted else None,
            "typed_name": "Una Client" if accepted else None,
            "attestation": "I confirm the work is done." if accepted else None,
            "signature_png_b64": png_b64() if accepted else None, "reports": [],
        },
    }


async def feed(report, raw: bytes) -> Outcome:
    dead: list[str] = []

    async def dlq(payload: bytes, reason: str) -> None:
        dead.append(reason)

    processor = consumer.processor(report.app.state.mongo, report.app.state.db, dlq, report.clock)
    outcome = await processor.process(raw)
    assert dead == []
    return outcome


async def closeouts(report) -> list[dict[str, Any]]:
    return [d async for d in report.db["reports"].find({"type": "closeout"}).sort("version", 1)]


async def corrected(report, version: int = 2) -> str:
    """A visit report of the request becomes final as `version` (the hook in the finalize
    transaction)."""
    seen: list[str] = []

    async def save(session):
        seen.append(await closeout_consumer.on_visit_report_final(
            report.svc.db, report.clock, {"request_id": REQUEST, "visit_id": vf.VISIT,
                                          "version": version}, session))

    await in_transaction(report.svc.client, save)
    return seen[0]


async def drawn(report, number: int = 0) -> dict[str, Any]:
    """Queue and draw the close-out at `number` (0 is the first)."""
    await job.tick(report.svc)
    docs = await closeouts(report)
    await job.render_closeout(report.svc, docs[number]["_id"])
    return (await closeouts(report))[number]


async def made(report, **over: Any) -> dict[str, Any]:
    report.facts.by_request[REQUEST] = facts(report, **over)
    await feed(report, closed_event(report, outcome=over.get("outcome", "accepted")))
    (doc,) = await closeouts(report)
    return doc


# --- The record (RPT-8) --------------------------------------------------------------------------


@pytest.mark.req("RPT-8")
async def test_a_closed_request_makes_one_numbered_closeout(report):
    doc = await made(report)
    assert doc["number"] == "CO-2026-0042" and doc["version"] == 1
    assert doc["status"] == "rendering" and doc["org_id"] == ORG_A and doc["request_id"] == REQUEST
    assert doc["subject_ref"] == f"request:{REQUEST}" and doc["supersedes_id"] is None
    await feed(report, closed_event(report))  # a repeat of the event
    assert len(await closeouts(report)) == 1


@pytest.mark.req("RPT-8")
async def test_the_worker_draws_the_closeout_and_it_is_final(report):
    await made(report)
    doc = await drawn(report)
    assert doc["status"] == "final" and doc["version"] == 1
    pdf = doc["final_pdf"]
    assert pdf["key"] == f"closeouts/{doc['_id']}/final.pdf"
    stored = report.s3.get_object(Bucket="mms-reports", Key=pdf["key"])["Body"].read()
    assert hashlib.sha256(stored).hexdigest() == pdf["sha256"] == doc["pdf_sha256"]
    # The record keeps the facts but not the drawing, and its hash stands for the drawing
    kept = doc["content"]["closeout"]
    assert "signature_png_b64" not in kept["decision"]
    assert kept["decision"]["signature_sha256"] == hashlib.sha256(
        base64.b64decode(png_b64())).hexdigest()
    assert doc["content_hash"] == closeout.content_hash(facts(report))

    (view,) = report.renderer.closeouts
    assert view["number"] == "CO-2026-0042" and view["org_name"] == "Organization A"
    assert view["decision"]["accepted"] and view["decision"]["typed_name"] == "Una Client"
    assert view["decision"]["signature"].startswith("data:image/png;base64,")
    assert view["hash"] == doc["content_hash"][:16]
    assert [t["status"] for t in view["timeline"]] == ["Submitted", "Closed"]
    assert view["visits"][0]["version"] == 1
    assert view["visits"][0]["link"] == f"https://mms.example/visit-reports/{REPORT_1}"
    assert [r["title"] for r in view["client_reports"]] == ["Gauge check"]
    assert view["client_reports"][0]["kind"] == "Online form"
    assert view["client_reports"][0]["date"] == "30 Sep 2026"
    assert [c["body"] for c in view["comments"]] == ["Please check the mast"]
    assert view["corrections"] == []

    (event,) = [e async for e in report.db["outbox"].find({"type": "report.closeout_generated"})]
    assert event["data"]["version"] == 1 and event["data"]["corrected"] is False
    assert event["data"]["pdf_sha256"] == pdf["sha256"] and event["key"] == REQUEST
    assert "Please check the mast" not in str(event)  # no text in an event


@pytest.mark.req("REQ-14")
async def test_an_automatic_close_says_so_instead_of_showing_a_signature(report):
    await made(report, outcome="auto_closed")
    await drawn(report)
    (view,) = report.renderer.closeouts
    decision = view["decision"]
    assert decision["automatic"] and decision["signature"] is None
    assert decision["sentence"].startswith("Closed automatically on ")
    assert "after 30 days without a response" in decision["sentence"]


@pytest.mark.req("RPT-8")
async def test_drawing_twice_changes_nothing(report):
    doc = await made(report)
    await drawn(report)
    await job.render_closeout(report.svc, doc["_id"])  # finished: not claimed again
    assert len(report.renderer.closeouts) == 1
    assert await report.db["outbox"].count_documents({"type": "report.closeout_generated"}) == 1
    assert (await job.tick(report.svc))["queued"] == 0


# --- A correction after the request closed (RPT-6, W18-12) ---------------------------------------


@pytest.mark.req("RPT-6")
async def test_a_correction_after_closure_makes_the_next_version(report):
    await made(report)
    first = await drawn(report)
    assert await corrected(report) == "new"
    v1, v2 = await closeouts(report)
    assert v1["status"] == "final" and v2["status"] == "rendering"
    assert v2["version"] == 2 and v2["supersedes_id"] == first["_id"]
    assert v2["number"] == "CO-2026-0042" and v2["expects"] == {vf.VISIT: 2}

    report.facts.by_request[REQUEST] = facts(report, version=2)
    report.clock.advance(minutes=3)
    v2 = await drawn(report, 1)
    v1 = (await closeouts(report))[0]
    assert (v1["status"], v2["status"]) == ("superseded", "final")
    assert v2["final_pdf"]["key"] != v1["final_pdf"]["key"]
    (_, view) = report.renderer.closeouts
    assert view["version"] == 2
    assert [(c["ref"], c["from"], c["to"]) for c in view["corrections"]] == [
        ("VR-2026-0042-02", 1, 2)]
    assert [c["ref"] for c in v2["corrections"]] == ["VR-2026-0042-02"]
    events = [e["data"] async for e in report.db["outbox"].find(
        {"type": "report.closeout_generated"}).sort("created_at", 1)]
    assert [(e["version"], e["corrected"]) for e in events] == [(1, False), (2, True)]


@pytest.mark.req("RPT-6")
async def test_a_second_correction_keeps_the_first_in_the_list(report):
    await made(report)
    await drawn(report)
    await corrected(report)
    report.facts.by_request[REQUEST] = facts(report, version=2)
    await drawn(report, 1)
    await corrected(report, 3)
    report.facts.by_request[REQUEST] = facts(report, version=3)
    third = await drawn(report, 2)
    assert [(c["from"], c["to"]) for c in third["corrections"]] == [(1, 2), (2, 3)]
    assert [d["status"] for d in await closeouts(report)] == ["superseded", "superseded", "final"]


@pytest.mark.req("RPT-6")
async def test_a_correction_that_arrives_before_operations_knows_it_waits(report):
    await made(report)
    await drawn(report)
    await corrected(report)
    (_, v2) = await closeouts(report)
    await job.tick(report.svc)
    # Operations still shows version 1 of the visit report
    with pytest.raises(Retry):
        await job.render_closeout(report.svc, v2["_id"])
    waiting = (await closeouts(report))[1]
    assert waiting["status"] == "rendering" and waiting["render"]["attempts"] == 0
    assert waiting["render"]["state"] == "queued" and len(report.renderer.closeouts) == 1
    report.clock.advance(minutes=6)  # it has waited long enough: draw with what there is
    await job.render_closeout(report.svc, v2["_id"])
    assert (await closeouts(report))[1]["status"] == "final"


@pytest.mark.req("RPT-6")
async def test_a_correction_while_the_closeout_is_still_to_be_drawn_joins_it(report):
    await made(report)
    assert await corrected(report) == "merge"  # no second version: the first is not drawn yet
    (doc,) = await closeouts(report)
    assert doc["expects"] == {vf.VISIT: 2} and doc["inputs_seq"] == 1 and doc["version"] == 1


@pytest.mark.req("RPT-6")
async def test_a_correction_that_joins_during_a_draw_makes_it_be_drawn_again(report):
    doc = await made(report)
    await job.tick(report.svc)
    plain = report.facts

    class Racing:
        """Operations answers, and while it does a correction joins the close-out."""

        async def closeout_facts(self, request_id: str):
            await corrected(report)
            return facts(report, version=2)

    report.svc.facts = Racing()  # type: ignore[assignment]
    await job.render_closeout(report.svc, doc["_id"])
    stuck = (await closeouts(report))[0]
    assert stuck["status"] == "rendering" and stuck["render"]["state"] == "idle"
    assert await report.db["outbox"].count_documents({"type": "report.closeout_generated"}) == 0
    report.svc.facts = plain
    report.facts.by_request[REQUEST] = facts(report, version=2)
    again = await drawn(report)
    assert again["status"] == "final" and again["inputs_seq"] == 1


@pytest.mark.req("RPT-6")
async def test_a_first_version_or_a_request_without_a_closeout_changes_nothing(report):
    assert await corrected(report, 2) == "skip"  # not closed: no close-out yet
    assert await closeouts(report) == []
    await made(report)
    await drawn(report)
    assert await corrected(report, 1) == "skip"  # a visit report's first version
    assert len(await closeouts(report)) == 1


# --- Failing and trying again --------------------------------------------------------------------


@pytest.mark.req("RPT-8")
async def test_a_closeout_that_fails_is_drawn_again_after_a_while(report):
    doc = await made(report)
    await job.tick(report.svc)
    report.renderer.fail = True
    for _ in range(2):
        with pytest.raises(Retry):
            await job.render_closeout(report.svc, doc["_id"])
    await job.render_closeout(report.svc, doc["_id"])  # the third try gives up
    failed = (await closeouts(report))[0]
    assert failed["status"] == "render_failed" and failed["render"]["error"] == "render_failed"
    assert await report.db["outbox"].count_documents({"type": "report.closeout_generated"}) == 0

    report.renderer.fail = False
    assert await job.tick(report.svc) == {"queued": 0, "restarted": 0}  # too soon
    report.clock.advance(hours=2)
    assert (await job.tick(report.svc))["restarted"] == 1
    await job.render_closeout(report.svc, doc["_id"])
    assert (await closeouts(report))[0]["status"] == "final"


@pytest.mark.req("RPT-8")
async def test_operations_not_knowing_the_request_is_a_failed_try(report):
    doc = await made(report)
    report.facts.by_request.clear()
    await job.tick(report.svc)
    for _ in range(2):
        with pytest.raises(Retry):
            await job.render_closeout(report.svc, doc["_id"])
    await job.render_closeout(report.svc, doc["_id"])
    assert (await closeouts(report))[0]["status"] == "render_failed"


# --- Reading it (rules 4 and 6) ------------------------------------------------------------------


async def get(report, report_id: str, who: str):
    return await report.http.get(f"/api/v1/reports/{report_id}", headers=report.bearer(who))


@pytest.mark.req("RPT-8")
async def test_the_client_and_staff_read_the_closeout_and_nobody_else(report):
    doc = await made(report)
    listing = await report.http.get("/api/v1/reports", params={"type": "closeout"},
                                    headers=report.bearer("client_a1"))
    assert listing.json() == []  # still being drawn: a client sees final reports only
    assert (await get(report, doc["_id"], "client_a1")).status_code == 404
    await drawn(report)
    for who in ("client_a1", "tech1", "admin", "viewer"):
        got = await get(report, doc["_id"], who)
        assert got.status_code == 200, who
        body = got.json()
        assert body["type"] == "closeout" and body["status"] == "final"
        assert body["content"]["closeout"]["decision"]["typed_name"] == "Una Client"
        assert "signature_png_b64" not in got.text
        link = await report.http.get(f"/api/v1/reports/{doc['_id']}/download",
                                     headers=report.bearer(who))
        assert link.json()["filename"] == "CO-2026-0042-v1.pdf"
        assert (await report.store.get(link.json()["url"])).content.startswith(b"%PDF")
    assert (await get(report, doc["_id"], "client_b1")).status_code == 404


@pytest.mark.req("RPT-6")
async def test_a_client_still_reads_the_closeout_a_correction_replaced(report):
    doc = await made(report)
    await drawn(report)
    await corrected(report)
    report.facts.by_request[REQUEST] = facts(report, version=2)
    await drawn(report, 1)
    listed = await report.http.get("/api/v1/reports", params={"type": "closeout"},
                                   headers=report.bearer("client_a1"))
    assert [(i["version"], i["status"]) for i in listed.json()] == [(2, "final"), (1, "superseded")]
    old = await get(report, doc["_id"], "client_a1")
    assert old.status_code == 200 and old.json()["status"] == "superseded"
    link = await report.http.get(f"/api/v1/reports/{doc['_id']}/download",
                                 headers=report.bearer("client_a1"))
    assert link.status_code == 200 and link.json()["filename"] == "CO-2026-0042-v1.pdf"


@pytest.mark.req("RPT-11")
async def test_verify_finds_both_versions_and_a_closeout_is_never_reopened(report):
    doc = await made(report)
    first = await drawn(report)
    await corrected(report)
    report.facts.by_request[REQUEST] = facts(report, version=2)
    second = await drawn(report, 1)
    for expected in (first, second):
        verified = await report.http.post("/api/v1/reports/verify",
                                          json={"sha256": expected["pdf_sha256"]})
        assert verified.json()["match"] is True and verified.json()["number"] == "CO-2026-0042"
    assert (await report.http.post("/api/v1/reports/verify",
                                   json={"sha256": first["pdf_sha256"]})).json()["status"] \
        == "superseded"
    reopen = await report.http.post(f"/api/v1/reports/{doc['_id']}/reopen",
                                    json={"reason": "Wrong name"}, headers=report.bearer("admin"))
    assert reopen.status_code == 409


@pytest.mark.req("RPT-6")
async def test_finalizing_a_corrected_visit_report_makes_the_next_closeout_in_the_same_commit(report):
    from app.jobs import drafts as draft_jobs
    from app.jobs.finalize import finalize_report
    from app.jobs.render_draft import render_draft
    from app.repo import reports as repo
    from tests.api.test_edit_sign import patch, sign
    from tests.api.test_finalize import final, post, reopen

    first = await final(report)  # the visit report, version 1, final
    await made(report)
    await drawn(report)  # the request closed and its close-out is drawn

    new = (await reopen(report, first)).json()
    await draft_jobs.tick(report.svc)
    await repo.request_render(report.db, new["id"], report.clock.now())
    await render_draft(report.svc, new["id"])
    current = await repo.get(report.db, new["id"])
    assert (await patch(report, current, {"narrative": {"summary": "Priority added."}})
            ).status_code == 200
    current = await repo.get(report.db, new["id"])
    assert (await sign(report, current, "tech1")).status_code == 201
    assert (await post(report, current, "finalize")).status_code == 202
    await finalize_report(report.svc, new["id"])

    v1, v2 = await closeouts(report)
    assert v1["status"] == "final" and (v2["version"], v2["status"]) == (2, "rendering")
    assert v2["expects"] == {vf.VISIT: 2} and v2["supersedes_id"] == v1["_id"]
