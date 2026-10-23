"""Visit report drafts (TRD 3.4, 11.2; PRD RPT-1, RPT-3; W16-1 to W16-7): made when a visit ends,
read from operations, drawn once the files are ready or after five minutes, previewed on demand,
and told to the people who attended."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.events import Envelope, Resource
from mms_common.ids import new_id
from mms_common.testing.seed import SEED_USERS

from app.events import consumer
from app.jobs import drafts as jobs
from app.jobs.labels import Retry
from app.jobs.render_draft import object_key, render_draft
from tests import visit_facts as vf

ENDED_AT = datetime(2026, 10, 5, 16, 40, tzinfo=UTC)
TECH1, TECH2 = SEED_USERS["tech1"].id, SEED_USERS["tech2"].id


def visit_event(type_: str, version: int, **extra: Any) -> bytes:
    data = {
        "visit_id": vf.VISIT, "ref": "VR-2026-0042-02", "request_id": vf.REQUEST,
        "request_ref": "MR-2026-0042", "org_id": vf.ORG, "title": "Rain gauge not reporting",
        "status": "ended", "planned_start": "2026-10-05T13:00:00Z",
        "planned_end": "2026-10-05T18:00:00Z", "staff_ids": [TECH1, TECH2],
        "lead_staff_id": TECH1, "station_ids": [vf.S1, vf.S2],
        "station_owners": [{"station_id": vf.S1, "owner_staff_id": TECH1},
                           {"station_id": vf.S2, "owner_staff_id": TECH2}], **extra,
    }
    return Envelope(
        event_id=new_id(), type=type_, occurred_at=ENDED_AT, source="operations",
        key=vf.REQUEST, aggregate_version=version, resource=Resource(type="visit", id=vf.VISIT),
        org_id=vf.ORG, data=data,
    ).model_dump_json().encode()


def ended(report, version: int = 6) -> bytes:
    """The visit ended just now, by the test's clock (the five-minute wait counts from it)."""
    return visit_event("visit.ended", version, ended_at=report.clock.now().isoformat(),
                       additional_visit_required=True)


def board_event(type_: str = "visit.element_updated", version: int = 3) -> bytes:
    return visit_event(
        type_, version, status="ended", station_id=vf.S1, element_id=new_id(), kind="note",
        shared=False, element_version=2, **({"changed_fields": ["title"]} if type_.endswith("updated") else {}),
    )


async def processor(report):
    dead: list[str] = []

    async def dlq(raw: bytes, reason: str) -> None:
        dead.append(reason)

    return consumer.processor(report.app.state.mongo, report.app.state.db, dlq, report.clock), dead


async def one(report) -> dict[str, Any]:
    doc = await report.db["reports"].find_one({})
    assert doc is not None
    out: dict[str, Any] = doc
    return out


def with_visit(report, *, ready: bool = True) -> None:
    report.facts.by_visit[vf.VISIT] = vf.facts()
    report.media.states = {m: ("ready" if ready else "processing") for m in vf.ALL_MEDIA}
    if ready:
        for m in (vf.P_BEFORE, vf.P_AFTER, vf.P_NOTE, vf.P_EXTRA):
            report.media.photos[m] = vf.webp()


# --- visit.ended makes the draft ----------------------------------------------------------------


async def test_a_visit_that_ends_makes_one_draft_record_even_if_the_event_comes_twice(report):
    p, dead = await processor(report)
    event = ended(report)
    assert await p.process(event) is Outcome.APPLIED
    assert await p.process(event) is Outcome.DUPLICATE
    assert await p.process(ended(report, 7)) is Outcome.APPLIED  # a second event for the same visit
    docs = [d async for d in report.db["reports"].find({})]
    assert len(docs) == 1 and not dead
    d = docs[0]
    assert d["type"] == "visit" and d["status"] == "draft" and d["version"] == 1
    assert d["number"] == "VR-2026-0042-02" and d["subject_ref"] == f"visit:{vf.VISIT}"
    assert d["staff_ids"] == [TECH1, TECH2] and d["lead_staff_id"] == TECH1
    assert d["facts_stale"] is True and d["content"]["facts"] is None
    assert d["draft_pdf"] is None and d["render"]["state"] == "idle"


async def test_the_visit_read_model_row_is_made_by_the_same_event(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    row = await report.db["visit_facts"].find_one({"_id": vf.VISIT})
    assert row is not None and row["status"] == "ended"


# --- reading the facts ---------------------------------------------------------------------------


async def test_the_tick_reads_the_facts_and_fills_the_narrative_once(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    with_visit(report)
    done = await jobs.tick(report.svc)
    assert done["refreshed"] == 1
    d = await one(report)
    assert d["facts_stale"] is False and d["facts_version"] == 1
    assert d["content"]["facts"]["visit"]["ref"] == "VR-2026-0042-02"
    assert d["content"]["narrative"]["follow_up"] == "Bring a new funnel"
    assert [s["media_id"] for s in d["content"]["media_selection"]][:2] == [vf.P_BEFORE, vf.P_AFTER]
    assert d["awaiting_media"] == []


async def test_a_board_change_reads_the_facts_again_and_keeps_the_narrative(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    with_visit(report)
    await jobs.tick(report.svc)
    await report.db["reports"].update_one(
        {}, {"$set": {"content.narrative.summary": "Typed by a technician"}})
    assert await p.process(board_event()) is Outcome.APPLIED
    assert (await one(report))["facts_stale"] is True
    report.facts.by_visit[vf.VISIT]["visit"]["follow_up_notes"] = "Changed on the board"
    await jobs.tick(report.svc)
    d = await one(report)
    assert d["facts_version"] == 2 and d["facts_stale"] is False
    assert d["content"]["facts"]["visit"]["follow_up_notes"] == "Changed on the board"
    assert d["content"]["narrative"]["summary"] == "Typed by a technician"
    assert d["content"]["narrative"]["follow_up"] == "Bring a new funnel"  # not rewritten


async def test_board_events_are_ignored_for_a_report_that_is_not_a_draft(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    await report.db["reports"].update_one({}, {"$set": {"status": "final", "facts_stale": False}})
    await p.process(board_event())
    d = await one(report)
    assert d["facts_stale"] is False


async def test_an_unreachable_operations_leaves_the_draft_stale_for_the_next_tick(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    with_visit(report)
    report.facts.down = True
    assert (await jobs.tick(report.svc))["refreshed"] == 0
    assert (await one(report))["facts_stale"] is True
    report.facts.down = False
    assert (await jobs.tick(report.svc))["refreshed"] == 1


async def test_an_unknown_visit_is_left_alone(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    assert (await jobs.tick(report.svc))["refreshed"] == 0


# --- when the first PDF is drawn ------------------------------------------------------------------


async def test_the_first_pdf_is_queued_at_once_when_every_file_is_ready(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    with_visit(report, ready=True)
    done = await jobs.tick(report.svc)  # reads the facts and queues in the same round
    d = await one(report)
    assert done["queued"] == 1 and report.jobs.queued == [f"draft:{d['_id']}"]
    assert d["render"]["state"] == "queued"
    assert (await jobs.tick(report.svc))["queued"] == 0  # one queue entry only


async def test_it_waits_for_files_but_only_five_minutes(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    with_visit(report, ready=False)
    await jobs.tick(report.svc)
    d = await one(report)
    assert len(d["awaiting_media"]) == 5
    assert (await jobs.tick(report.svc))["queued"] == 0
    # Two files finish: the others are still waited for
    report.media.states[vf.P_BEFORE] = report.media.states[vf.P_AFTER] = "ready"
    await jobs.tick(report.svc)
    assert len((await one(report))["awaiting_media"]) == 3
    report.clock.advance(minutes=5)
    assert (await jobs.tick(report.svc))["queued"] == 1


async def test_it_queues_as_soon_as_the_last_file_is_processed(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    with_visit(report, ready=False)
    await jobs.tick(report.svc)
    report.media.states = {m: "ready" for m in vf.ALL_MEDIA}
    assert (await jobs.tick(report.svc))["queued"] == 1
    assert (await one(report))["awaiting_media"] == []


# --- the render job ------------------------------------------------------------------------------


async def ready_draft(report) -> dict[str, Any]:
    p, _ = await processor(report)
    await p.process(ended(report))
    with_visit(report)
    assert await jobs.refresh_facts(report.svc, await one(report))
    return await one(report)


def stored(report, key: str) -> bytes:
    body: bytes = report.s3.get_object(Bucket="mms-reports", Key=key)["Body"].read()
    return body


async def test_the_render_stores_the_pdf_records_it_and_says_so_once(report):
    d = await ready_draft(report)
    assert await report.db["reports"].update_one({"_id": d["_id"]}, {"$set": {"render.state": "queued"}})
    await render_draft(report.svc, d["_id"])
    d = await one(report)
    pdf = d["draft_pdf"]
    assert pdf["key"] == object_key(d["_id"], 1, 1) and pdf["pages"] == 1
    assert stored(report, pdf["key"]).startswith(b"%PDF")
    assert d["render"]["state"] == "idle" and d["drafted_at"] is not None
    events = [e async for e in report.db["outbox"].find({"type": "report.drafted"})]
    assert len(events) == 1
    data = events[0]["data"]
    assert data["number"] == "VR-2026-0042-02" and data["staff_ids"] == [TECH1, TECH2]
    assert data["title"] == "Rain gauge not reporting" and data["request_ref"] == "MR-2026-0042"
    assert "stations" not in data and "content" not in data  # ids only: no text travels (rule 1)
    # The picture of a ready photo is in the page; the file that is not a photo is not asked for
    view = report.renderer.visits[0]
    task = view["stations"][0]["tasks"][0]
    assert task["before"][0]["uri"].startswith("data:image/jpeg;base64,")


async def test_a_second_render_replaces_the_first_pdf_without_a_second_notification(report):
    d = await ready_draft(report)
    await report.db["reports"].update_one({"_id": d["_id"]}, {"$set": {"render.state": "queued"}})
    await render_draft(report.svc, d["_id"])
    first_key = (await one(report))["draft_pdf"]["key"]
    await report.db["reports"].update_one(
        {"_id": d["_id"]}, {"$set": {"facts_version": 2, "render.state": "queued"}})
    await render_draft(report.svc, d["_id"])
    d = await one(report)
    assert d["draft_pdf"]["key"] != first_key and d["draft_pdf"]["facts_version"] == 2
    assert await report.db["outbox"].count_documents({"type": "report.drafted"}) == 1
    with pytest.raises(Exception):  # noqa: B017,PT011 - the old object is gone
        stored(report, first_key)


async def test_a_job_that_is_not_queued_does_nothing(report):
    d = await ready_draft(report)
    await render_draft(report.svc, d["_id"])  # state is idle: not claimed
    assert (await one(report))["draft_pdf"] is None
    assert report.renderer.visits == []


async def test_a_photo_that_cannot_be_read_prints_a_grey_box_not_an_error(report):
    d = await ready_draft(report)
    report.media.photos[vf.P_BEFORE] = b"not an image"
    del report.media.photos[vf.P_AFTER]
    await report.db["reports"].update_one({"_id": d["_id"]}, {"$set": {"render.state": "queued"}})
    await render_draft(report.svc, d["_id"])
    assert (await one(report))["draft_pdf"] is not None
    task = report.renderer.visits[0]["stations"][0]["tasks"][0]
    assert task["before"][0]["uri"] is None and task["after"][0]["uri"] is None


async def test_a_failing_render_is_marked_failed_and_the_draft_stays_a_draft(report):
    d = await ready_draft(report)
    report.renderer.fail = True
    await report.db["reports"].update_one({"_id": d["_id"]}, {"$set": {"render.state": "queued"}})
    await render_draft(report.svc, d["_id"])
    d = await one(report)
    assert d["render"] == {**d["render"], "state": "failed", "error": "render_failed"}
    assert d["status"] == "draft" and d["draft_pdf"] is None
    assert await report.db["outbox"].count_documents({"type": "report.drafted"}) == 0


async def test_an_unreachable_media_service_retries_then_fails(report):
    d = await ready_draft(report)
    report.media.down = True
    await report.db["reports"].update_one({"_id": d["_id"]}, {"$set": {"render.state": "queued"}})
    for _ in range(report.settings.job_max_attempts - 1):
        with pytest.raises(Retry):
            await render_draft(report.svc, d["_id"])
        assert (await one(report))["render"]["state"] == "queued"
    await render_draft(report.svc, d["_id"])
    assert (await one(report))["render"]["state"] == "failed"


# --- the routes ------------------------------------------------------------------------------------


async def get(report, path: str, who: str = "tech1"):
    return await report.http.get(path, headers=report.bearer(who))


async def post(report, path: str, who: str = "tech1"):
    return await report.http.post(path, headers=report.bearer(who))


async def test_staff_list_and_read_a_draft_and_a_client_sees_nothing(report):
    d = await ready_draft(report)
    listed = await get(report, f"/api/v1/reports?subject_ref=visit:{vf.VISIT}")
    assert listed.status_code == 200 and [r["id"] for r in listed.json()] == [d["_id"]]
    assert listed.json()[0]["pdf"]["state"] == "none"
    detail = await get(report, f"/api/v1/reports/{d['_id']}", "viewer")
    assert detail.status_code == 200
    assert detail.json()["content"]["facts"]["visit"]["ref"] == "VR-2026-0042-02"
    for who in ("client_a1", "client_b1"):
        assert (await get(report, "/api/v1/reports", who)).json() == []
        assert (await get(report, f"/api/v1/reports/{d['_id']}", who)).status_code == 404
        assert (await get(report, f"/api/v1/reports/{d['_id']}/download", who)).status_code == 404


async def test_a_report_that_does_not_exist_is_404(report):
    assert (await get(report, f"/api/v1/reports/{new_id()}")).status_code == 404
    assert (await post(report, f"/api/v1/reports/{new_id()}/preview")).status_code == 404


async def test_preview_queues_one_render_and_answers_ready_when_the_pdf_is_current(report):
    d = await ready_draft(report)
    first = await post(report, f"/api/v1/reports/{d['_id']}/preview")
    assert first.status_code == 202 and first.json()["state"] == "rendering"
    again = await post(report, f"/api/v1/reports/{d['_id']}/preview", "tech2")
    assert again.json()["state"] == "rendering"
    assert report.jobs.queued == [f"draft:{d['_id']}"]  # asked twice, queued once
    await render_draft(report.svc, d["_id"])
    ready = await post(report, f"/api/v1/reports/{d['_id']}/preview")
    assert ready.json()["state"] == "ready" and ready.json()["pdf"]["current"] is True
    assert report.jobs.queued == [f"draft:{d['_id']}"]
    # The board changes: the PDF is no longer current, and a preview draws it again
    await report.db["reports"].update_one({"_id": d["_id"]}, {"$inc": {"facts_version": 1}})
    assert (await get(report, f"/api/v1/reports/{d['_id']}")).json()["pdf"]["current"] is False
    assert (await post(report, f"/api/v1/reports/{d['_id']}/preview")).json()["state"] == "rendering"
    assert len(report.jobs.queued) == 2


async def test_only_the_people_attending_and_admins_may_ask_for_a_preview(report):
    d = await ready_draft(report)
    await report.db["reports"].update_one({}, {"$set": {"staff_ids": [TECH2]}})
    assert (await post(report, f"/api/v1/reports/{d['_id']}/preview", "tech1")).status_code == 403
    assert (await post(report, f"/api/v1/reports/{d['_id']}/preview", "tech2")).status_code == 202
    assert (await post(report, f"/api/v1/reports/{d['_id']}/preview", "admin")).status_code == 202
    assert (await post(report, f"/api/v1/reports/{d['_id']}/preview", "viewer")).status_code == 403


async def test_a_draft_that_is_not_ready_or_not_a_draft_cannot_be_previewed(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    doc = await one(report)
    early = await post(report, f"/api/v1/reports/{doc['_id']}/preview")
    assert early.status_code == 409 and early.json()["code"] == "draft_not_ready"
    with_visit(report)
    await jobs.tick(report.svc)
    await report.db["reports"].update_one({}, {"$set": {"status": "final"}})
    gone = await post(report, f"/api/v1/reports/{doc['_id']}/preview")
    assert gone.status_code == 409 and gone.json()["code"] == "not_a_draft"


async def test_download_gives_a_link_to_the_pdf_that_a_browser_can_use(report):
    d = await ready_draft(report)
    none = await get(report, f"/api/v1/reports/{d['_id']}/download")
    assert none.status_code == 409 and none.json()["code"] == "no_pdf"
    await report.db["reports"].update_one({}, {"$set": {"render.state": "queued"}})
    await render_draft(report.svc, d["_id"])
    link = await get(report, f"/api/v1/reports/{d['_id']}/download", "viewer")
    assert link.status_code == 200
    body = link.json()
    assert body["filename"] == "VR-2026-0042-02-v1-draft.pdf" and body["current"] is True
    got = await report.store.get(body["url"])
    assert got.status_code == 200 and got.content.startswith(b"%PDF")
    assert "no-store" in link.headers["cache-control"]
