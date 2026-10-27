"""Finalizing, reopening and verifying a visit report (TRD 11.2; PRD RPT-4 to RPT-6, RPT-11; W17-5,
W17-7, W17-10, W17-12): the saga step by step, what each failure leaves behind, and the rule that
a final report always has the lead's signature for exactly its content."""

from __future__ import annotations

import hashlib
from datetime import UTC
from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import SEED_USERS

from app.jobs import drafts as draft_jobs
from app.jobs import resume
from app.jobs.finalize import finalize_report, job_id
from app.jobs.labels import Retry
from app.jobs.render_draft import render_draft
from app.repo import reports as repo
from app.repo.storage import StorageError
from tests import visit_facts as vf
from tests.api.test_drafts import one, stored
from tests.api.test_edit_sign import events, patch, read, ready, sign

LEAD = SEED_USERS["tech1"].id
HELPER = SEED_USERS["tech2"].id
GATE_NOTE = "Gate code is 4471"


async def post(report, d, action: str, who: str = "tech1", body: dict[str, Any] | None = None):
    return await report.http.post(
        f"/api/v1/reports/{d['_id']}/{action}", headers=report.bearer(who), json=body or {})


async def signed(report, *, both: bool = False) -> dict[str, Any]:
    """A draft the lead (and the other person, if `both`) has signed."""
    d = await ready(report)
    assert (await sign(report, d, "tech1")).status_code == 201
    if both:
        assert (await sign(report, d, "tech2")).status_code == 201
    return await one(report)


async def final(report) -> dict[str, Any]:
    d = await signed(report, both=True)
    assert (await post(report, d, "finalize")).status_code == 202
    await finalize_report(report.svc, d["_id"])
    return await one(report)


async def invariant(report) -> None:
    """A final or superseded report has the lead's valid signature for exactly its content, and
    the PDF it names is the one stored (rule 11)."""
    async for r in report.db["reports"].find({"status": {"$in": ["final", "superseded"]}}):
        lead = [s async for s in report.db["signatures"].find({
            "report_id": r["_id"], "report_version": r["version"], "valid": True,
            "signer_id": r["lead_staff_id"], "content_hash": r["content_hash"]})]
        assert lead, f"{r['_id']} is {r['status']} without the lead's signature"
        assert r["final_pdf"]["sha256"] == r["pdf_sha256"]
        assert hashlib.sha256(stored(report, r["pdf_key"])).hexdigest() == r["pdf_sha256"]


# --- starting it ------------------------------------------------------------------------------------


@pytest.mark.req("RPT-5")
async def test_finalize_needs_the_leads_signature_for_this_content(report):
    d = await ready(report)
    none = await post(report, d, "finalize")
    assert none.status_code == 409 and none.json()["code"] == "lead_not_signed"
    await sign(report, d, "tech2")
    assert (await post(report, d, "finalize", "admin")).json()["code"] == "lead_not_signed"
    await sign(report, d, "tech1")
    # An edit clears the signature, and with it the right to finalize
    await patch(report, d, {"narrative": {"summary": "Edited after signing."}})
    d = await one(report)
    assert (await post(report, d, "finalize")).json()["code"] == "lead_not_signed"
    assert (await one(report))["status"] == "draft"


@pytest.mark.req("RPT-5")
async def test_only_the_lead_or_an_admin_starts_it(report):
    d = await signed(report, both=True)
    other = await post(report, d, "finalize", "tech2")
    assert other.status_code == 403 and other.json()["code"] == "not_lead"
    for who in ("viewer", "client_a1"):
        assert (await post(report, d, "finalize", who)).status_code == 403
    admin = await post(report, d, "finalize", "admin")  # an admin who did not attend may
    assert admin.status_code == 202 and admin.json()["status"] == "finalizing"
    assert (await one(report))["finalize_requested_by"] == SEED_USERS["admin"].id


@pytest.mark.req("RPT-5")
async def test_asking_again_while_it_runs_queues_nothing_more_and_edits_are_refused(report):
    d = await signed(report)
    first = await post(report, d, "finalize")
    assert first.status_code == 202 and first.json()["status"] == "finalizing"
    again = await post(report, d, "finalize", "admin")
    assert again.status_code == 202 and again.json()["status"] == "finalizing"
    assert report.jobs.queued.count(job_id(d["_id"])) == 1
    refused = await patch(report, d, {"narrative": {"summary": "too late"}})
    assert refused.status_code == 409 and refused.json()["code"] == "not_a_draft"
    assert (await sign(report, d, "tech2")).json()["code"] == "not_a_draft"
    # Board changes are not read into a report that is finalizing
    await report.db["reports"].update_one({}, {"$set": {"facts_stale": False}})
    await repo.mark_stale(report.db, vf.VISIT, report.clock.now(), None)  # type: ignore[arg-type]
    assert (await one(report))["facts_stale"] is False


async def test_a_report_that_is_not_there_or_not_ready_cannot_be_finalized(report):
    gone = await report.http.post(
        f"/api/v1/reports/{new_id()}/finalize", headers=report.bearer("tech1"), json={})
    assert gone.status_code == 404
    d = await ready(report)
    await report.db["reports"].update_one({}, {"$set": {"content_hash": None}})
    r = await post(report, d, "finalize")
    assert r.status_code == 409 and r.json()["code"] == "draft_not_ready"


# --- the saga ------------------------------------------------------------------------------------------


@pytest.mark.req("RPT-5")
async def test_the_saga_locks_the_visit_draws_the_pdf_and_makes_the_report_final(report):
    d = await signed(report, both=True)
    await post(report, d, "finalize")
    await finalize_report(report.svc, d["_id"])
    done = await one(report)
    assert done["status"] == "final" and done["finalized_by"] == LEAD
    assert done["finalized_at"].replace(tzinfo=UTC) == report.clock.now() and done["finalize_error"] is None
    # The visit is locked for this report version
    assert report.locks.held == {vf.VISIT: (d["_id"], 1)}
    # The PDF is under a key of its own, and the report names its hash
    pdf = done["final_pdf"]
    assert pdf["key"] == f"visits/{d['_id']}/final-v1.pdf" and done["pdf_key"] == pdf["key"]
    assert hashlib.sha256(stored(report, pdf["key"])).hexdigest() == done["pdf_sha256"]
    # The page it drew is the final one: no watermark, the hash, both signatures
    page = report.renderer.visits[-1]
    assert page["draft"] is False and page["status_word"] == "Final"
    assert page["hash"] == d["content_hash"][:16]
    assert [s["name"] for s in page["signatures"]] == ["Test Person", "Test Person"]
    assert {s["role"] for s in page["signatures"]} == {"Lead", "Attending"}
    # One event, with the PDF's hash, by the person who finalized
    (event,) = await events(report, "report.finalized")
    assert event["data"]["pdf_sha256"] == done["pdf_sha256"] and event["data"]["version"] == 1
    assert event["data"]["finalized_by"] == LEAD and event["actor"]["user_id"] == LEAD
    assert event["data"]["staff_ids"] == [LEAD, HELPER] and event["key"] == vf.REQUEST
    assert "iVBOR" not in str(event) and "Test Person" not in str(event)
    await invariant(report)


async def test_the_job_is_safe_to_run_again(report):
    d = await signed(report)
    await post(report, d, "finalize")
    await finalize_report(report.svc, d["_id"])
    await finalize_report(report.svc, d["_id"])
    assert len(await events(report, "report.finalized")) == 1
    assert (await one(report))["status"] == "final"
    await finalize_report(report.svc, new_id())  # a report that is not there: nothing happens


@pytest.mark.req("RPT-5")
async def test_a_final_report_is_downloaded_as_the_final_pdf(report):
    done = await final(report)
    link = await report.http.get(
        f"/api/v1/reports/{done['_id']}/download", headers=report.bearer("viewer"))
    body = link.json()
    assert body["filename"] == "VR-2026-0042-02-v1.pdf" and body["current"] is True
    got = await report.store.get(body["url"])
    assert got.status_code == 200 and got.content.startswith(b"%PDF")
    record = (await read(report, done)).json()
    assert record["status"] == "final" and record["pdf"]["state"] == "ready"
    assert record["pdf_sha256"] == done["pdf_sha256"] and record["finalized_by"] == LEAD
    assert [s["valid"] for s in record["signatures"]] == [True, True]


async def test_a_staff_only_change_on_the_board_does_not_stop_it(report):
    d = await signed(report)
    await post(report, d, "finalize")
    report.facts.by_visit[vf.VISIT]["stations"][0]["elements"].append(
        vf.element("note", "Access", description=GATE_NOTE, shared=False))
    await finalize_report(report.svc, d["_id"])
    assert (await one(report))["status"] == "final"
    assert GATE_NOTE not in str(report.renderer.visits[-1])


# --- what a failure leaves behind -------------------------------------------------------------------


@pytest.mark.req("RPT-5")
async def test_a_visit_that_cannot_be_locked_leaves_a_draft_with_its_signatures(report):
    d = await signed(report)
    await post(report, d, "finalize")
    report.locks.refuse = "locked_by_another_report"
    await finalize_report(report.svc, d["_id"])
    back = await one(report)
    assert back["status"] == "draft" and back["finalize_error"] == "lock_failed"
    assert back["unlock_pending"] is None  # the unlock was done, there was nothing to open
    assert (await read(report, d)).json()["signatures"][0]["valid"] is True
    (event,) = await events(report, "report.finalize_failed")
    assert event["data"]["reason"] == "lock_failed" and event["data"]["signer_ids"] == [LEAD]
    assert event["data"]["lead_staff_id"] == LEAD and event["data"]["attempts"] == 1
    # Fixed, the lead tries again
    report.locks.refuse = None
    assert (await post(report, back, "finalize")).status_code == 202
    await finalize_report(report.svc, d["_id"])
    assert (await one(report))["status"] == "final" and (await one(report))["finalize_error"] is None
    await invariant(report)


@pytest.mark.req("RPT-5")
async def test_a_fact_that_changed_after_signing_clears_the_signatures_and_unlocks(report):
    d = await signed(report, both=True)
    await post(report, d, "finalize")
    report.facts.by_visit[vf.VISIT]["stations"][0]["elements"][0]["title"] = "Replaced the funnel"
    await finalize_report(report.svc, d["_id"])
    back = await one(report)
    assert back["status"] == "draft" and back["finalize_error"] == "facts_changed"
    assert back["facts_stale"] is True and report.locks.held == {}
    record = (await read(report, d)).json()
    assert [s["valid"] for s in record["signatures"]] == [False, False]
    assert {s["cleared_by"] for s in record["signatures"]} == {"facts"}
    (cleared,) = await events(report, "report.signatures_cleared")
    assert cleared["data"]["count"] == 2 and cleared["data"]["reason"] == "facts"
    (failed,) = await events(report, "report.finalize_failed")
    assert failed["data"]["reason"] == "facts_changed" and sorted(failed["data"]["signer_ids"]) == [
        LEAD, HELPER]
    # The cron reads the new facts; the lead signs the new page and finalizes
    assert (await draft_jobs.tick(report.svc))["refreshed"] == 1
    new = await one(report)
    assert new["content_version"] == d["content_version"] + 1
    assert (await sign(report, new, "tech1")).status_code == 201
    assert (await post(report, await one(report), "finalize")).status_code == 202
    await finalize_report(report.svc, d["_id"])
    assert (await one(report))["status"] == "final"
    await invariant(report)


@pytest.mark.req("RPT-5")
async def test_a_pdf_that_cannot_be_drawn_is_tried_three_times_then_the_report_is_a_draft(report):
    d = await signed(report)
    await post(report, d, "finalize")
    report.renderer.fail = True
    for attempt, wait in ((1, 30), (2, 60)):
        with pytest.raises(Retry) as caught:
            await finalize_report(report.svc, d["_id"])
        assert caught.value.defer_s == wait
        assert (await one(report))["status"] == "finalizing"
        assert (await one(report))["finalize_attempts"] == attempt
    await finalize_report(report.svc, d["_id"])  # the third and last try
    back = await one(report)
    assert back["status"] == "draft" and back["finalize_error"] == "render_failed"
    assert back["finalize_attempts"] == 3 and report.locks.held == {}
    assert (await read(report, d)).json()["signatures"][0]["valid"] is True
    (event,) = await events(report, "report.finalize_failed")
    assert event["data"]["reason"] == "render_failed" and event["data"]["attempts"] == 3
    # Nothing was made final, and the lead can try again once it is fixed
    assert await events(report, "report.finalized") == []
    report.renderer.fail = False
    await post(report, back, "finalize")
    await finalize_report(report.svc, d["_id"])
    assert (await one(report))["status"] == "final"
    await invariant(report)


async def test_a_store_that_fails_once_is_tried_again(report, monkeypatch):
    d = await signed(report)
    await post(report, d, "finalize")
    real = report.svc.storage.put
    calls = {"n": 0}

    async def flaky(*args: Any, **kwargs: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise StorageError("down")
        await real(*args, **kwargs)

    monkeypatch.setattr(report.svc.storage, "put", flaky)
    with pytest.raises(Retry):
        await finalize_report(report.svc, d["_id"])
    await finalize_report(report.svc, d["_id"])
    assert (await one(report))["status"] == "final" and calls["n"] == 2
    await invariant(report)


async def test_operations_down_is_tried_again_then_gives_up_with_the_visit_open(report):
    d = await signed(report)
    await post(report, d, "finalize")
    report.locks.down = True
    for _ in range(2):
        with pytest.raises(Retry):
            await finalize_report(report.svc, d["_id"])
    await finalize_report(report.svc, d["_id"])
    back = await one(report)
    assert back["status"] == "draft" and back["finalize_error"] == "lock_failed"
    # The unlock could not be told either: it is owed, and the cron does it when operations is back
    assert back["unlock_pending"] == {"report_id": d["_id"], "version": 1}
    report.locks.down = False
    assert (await resume.tick(report.svc))["unlocked"] == 1
    assert (await one(report))["unlock_pending"] is None


# --- crashes and the cron ----------------------------------------------------------------------------


@pytest.mark.req("RPT-5")
async def test_a_report_left_finalizing_is_taken_up_again_and_finishes(report):
    d = await signed(report)
    await post(report, d, "finalize")
    # The worker locked the visit and died
    await repo.claim_finalizing(report.db, d["_id"], report.clock.now())
    await report.locks.lock(vf.VISIT, d["_id"], 1)
    report.jobs.queued.clear()
    assert (await resume.tick(report.svc))["resumed"] == 0  # not yet
    report.clock.advance(minutes=report.settings.finalizing_timeout_s // 60 + 1)
    assert (await resume.tick(report.svc))["resumed"] == 1
    assert report.jobs.queued == [job_id(d["_id"])]
    await finalize_report(report.svc, d["_id"])  # the lock is taken again without complaint
    assert (await one(report))["status"] == "final"
    assert len(await events(report, "report.finalized")) == 1
    await invariant(report)


@pytest.mark.req("RPT-5")
@pytest.mark.parametrize("fault", ["lock", "lock_down", "facts_down", "facts_gone", "changed",
                                   "render", "store"])
async def test_no_failure_leaves_a_final_report_without_the_leads_signature(
    report, monkeypatch, fault
):
    d = await signed(report, both=True)
    await post(report, d, "finalize")
    if fault == "lock":
        report.locks.refuse = "not_ended"
    elif fault == "lock_down":
        report.locks.down = True
    elif fault == "facts_down":
        report.facts.down = True
    elif fault == "facts_gone":
        del report.facts.by_visit[vf.VISIT]
    elif fault == "changed":
        report.facts.by_visit[vf.VISIT]["visit"]["follow_up_notes"] = "A different follow-up"
    elif fault == "render":
        report.renderer.fail = True
    else:
        async def broken(*args: Any, **kwargs: Any) -> None:
            raise StorageError("down")

        monkeypatch.setattr(report.svc.storage, "put", broken)
    for _ in range(report.settings.finalize_retries):
        try:
            await finalize_report(report.svc, d["_id"])
        except Retry:
            continue
    after = await one(report)
    assert after["status"] == "draft" and after["finalize_error"]
    assert await events(report, "report.finalized") == []
    await invariant(report)
    # The lead's signature is exactly as valid as the content: valid unless the facts changed
    expected = fault != "changed"
    lead = await report.db["signatures"].find_one({"signer_id": LEAD})
    assert lead["valid"] is expected


# --- reopening ----------------------------------------------------------------------------------------------


async def reopen(report, d, reason: str = "The tree trimming recommendation lacked a priority.",
                 who: str = "admin"):
    return await post(report, d, "reopen", who, {"reason": reason})


@pytest.mark.req("RPT-6")
async def test_an_admin_reopens_a_final_report_as_the_next_version(report):
    done = await final(report)
    await report.db["request_facts"].insert_one({"_id": vf.REQUEST, "status": "client_review"})
    r = await reopen(report, done)
    assert r.status_code == 201
    new = r.json()
    assert new["version"] == 2 and new["status"] == "draft" and new["id"] != done["_id"]
    assert new["number"] == done["number"] and new["supersedes_id"] == done["_id"]
    assert new["signatures"] == [] and new["content_version"] == 1
    assert new["content"]["narrative"] == done["content"]["narrative"]
    assert new["content"]["media_selection"] == done["content"]["media_selection"]
    old = await report.db["reports"].find_one({"_id": done["_id"]})
    assert old["status"] == "superseded" and old["pdf_sha256"] == done["pdf_sha256"]
    # The boards open again: the lock was released for the old version
    assert report.locks.held == {}
    assert ("unlock", vf.VISIT, done["_id"], 1) in report.locks.calls
    (event,) = await events(report, "report.reopened")
    assert event["data"]["report_id"] == new["id"] and event["data"]["version"] == 2
    assert event["data"]["previous_version"] == 1 and event["data"]["request_status"] == "client_review"
    assert event["data"]["reason"].startswith("The tree trimming")
    assert event["data"]["reopened_by"] == SEED_USERS["admin"].id
    assert event["data"]["staff_ids"] == [LEAD, HELPER]
    await invariant(report)


@pytest.mark.req("RPT-6")
async def test_the_corrected_version_is_read_again_signed_and_finalized(report):
    done = await final(report)
    new = (await reopen(report, done)).json()
    record = await repo.get(report.db, new["id"])
    assert record["facts_stale"] is True
    assert (await draft_jobs.tick(report.svc))["refreshed"] == 1
    # No `report.drafted` for a version that is a correction: the people already know the report
    await repo.request_render(report.db, new["id"], report.clock.now())
    await render_draft(report.svc, new["id"])
    assert await events(report, "report.drafted") == []
    current = await repo.get(report.db, new["id"])
    assert (await patch(
        report, current, {"narrative": {"summary": "Priority added."}})).status_code == 200
    current = await repo.get(report.db, new["id"])
    assert (await sign(report, current, "tech1")).status_code == 201
    assert (await post(report, current, "finalize")).status_code == 202
    await finalize_report(report.svc, new["id"])
    v2 = await repo.get(report.db, new["id"])
    assert v2["status"] == "final" and v2["version"] == 2
    assert report.locks.held == {vf.VISIT: (new["id"], 2)}
    assert v2["pdf_sha256"] != done["pdf_sha256"]
    assert len(await events(report, "report.finalized")) == 2
    await invariant(report)


@pytest.mark.req("RPT-6")
async def test_only_an_admin_reopens_and_only_a_final_report_with_a_reason(report):
    d = await signed(report)
    assert (await reopen(report, d)).json()["code"] == "not_final"
    done = await final_after(report, d)
    for who in ("tech1", "tech2", "viewer", "client_a1"):
        assert (await reopen(report, done, who=who)).status_code == 403
    for bad in ("", "no", "x" * 501):
        r = await reopen(report, done, bad)
        assert r.status_code == 422 and r.json()["code"] == "bad_reason"
    assert (await one(report))["status"] == "final"
    gone = await report.http.post(
        f"/api/v1/reports/{new_id()}/reopen", headers=report.bearer("admin"),
        json={"reason": "This report is not there"})
    assert gone.status_code == 404


async def final_after(report, d) -> dict[str, Any]:
    assert (await post(report, d, "finalize")).status_code == 202
    await finalize_report(report.svc, d["_id"])
    return await one(report)


@pytest.mark.req("RPT-6")
async def test_a_report_is_reopened_once(report):
    done = await final(report)
    assert (await reopen(report, done)).status_code == 201
    again = await reopen(report, done)
    assert again.status_code == 409 and again.json()["code"] == "already_reopened"
    assert await report.db["reports"].count_documents({}) == 2


async def test_two_reopens_at_once_make_one_new_version(report):
    import asyncio

    done = await final(report)
    first, second = await asyncio.gather(reopen(report, done), reopen(report, done))
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    assert await report.db["reports"].count_documents({"version": 2}) == 1


async def test_a_visit_that_cannot_be_unlocked_is_unlocked_later_by_the_cron(report):
    done = await final(report)
    report.locks.down = True
    r = await reopen(report, done)
    assert r.status_code == 201 and report.locks.held  # still locked, and owed
    created = await repo.get(report.db, r.json()["id"])
    assert created["unlock_pending"] == {"report_id": done["_id"], "version": 1}
    assert (await resume.tick(report.svc))["unlocked"] == 1 and report.locks.held
    report.locks.down = False
    assert (await resume.tick(report.svc))["unlocked"] == 1
    assert report.locks.held == {}
    assert (await repo.get(report.db, r.json()["id"]))["unlock_pending"] is None
    assert (await resume.tick(report.svc))["unlocked"] == 0


# --- what a client sees --------------------------------------------------------------------------------------


@pytest.mark.req("RPT-5")
async def test_a_client_sees_the_final_version_only(report):
    done = await final(report)
    await report.db["reports"].update_many(
        {}, {"$set": {"org_id": SEED_USERS["client_a1"].org_id}})
    listed = (await report.http.get("/api/v1/reports", headers=report.bearer("client_a1"))).json()
    assert [r["id"] for r in listed] == [done["_id"]]
    assert listed[0]["status"] == "final" and listed[0]["pdf_sha256"] == done["pdf_sha256"]
    link = await report.http.get(
        f"/api/v1/reports/{done['_id']}/download", headers=report.bearer("client_a1"))
    assert link.status_code == 200 and link.json()["filename"] == "VR-2026-0042-02-v1.pdf"
    other = report.bearer("client_b1")
    assert (await report.http.get(f"/api/v1/reports/{done['_id']}", headers=other)).status_code == 404
    # Reopened: the old version and the new draft are both gone from the client's view
    new = (await reopen(report, done)).json()
    assert (await report.http.get("/api/v1/reports", headers=report.bearer("client_a1"))).json() == []
    for report_id in (done["_id"], new["id"]):
        for path in ("", "/download"):
            r = await report.http.get(
                f"/api/v1/reports/{report_id}{path}", headers=report.bearer("client_a1"))
            assert r.status_code == 404
    # Staff still read and download the superseded version
    old = await report.http.get(
        f"/api/v1/reports/{done['_id']}/download", headers=report.bearer("tech1"))
    assert old.status_code == 200 and old.json()["filename"] == "VR-2026-0042-02-v1.pdf"


@pytest.mark.req("RPT-6")
async def test_a_final_or_superseded_report_is_immutable_through_every_route(report):
    done = await final(report)
    new = (await reopen(report, done)).json()
    before = {d["_id"]: d async for d in report.db["reports"].find({"status": {
        "$in": ["final", "superseded"]}})}
    old = await repo.get(report.db, done["_id"])
    assert old["status"] == "superseded"
    r1 = await patch(report, old, {"narrative": {"summary": "no"}})
    r2 = await sign(report, old, "tech2")
    r3 = await post(report, old, "preview")
    r4 = await post(report, old, "finalize")
    r5 = await reopen(report, old)
    assert [r.status_code for r in (r1, r2, r3, r4, r5)] == [409] * 5
    # And a final one
    await post(report, await repo.get(report.db, new["id"]), "preview")  # a draft: fine
    v2 = await repo.get(report.db, new["id"])
    await sign(report, v2, "tech1")
    await post(report, await repo.get(report.db, new["id"]), "finalize")
    await finalize_report(report.svc, new["id"])
    final_v2 = await repo.get(report.db, new["id"])
    assert final_v2["status"] == "final"
    for r in (await patch(report, final_v2, {"narrative": {"summary": "no"}}),
              await sign(report, final_v2, "tech2"), await post(report, final_v2, "preview"),
              await post(report, final_v2, "finalize")):
        assert r.status_code == 409
    after = {d["_id"]: d async for d in report.db["reports"].find({"_id": done["_id"]})}
    assert after[done["_id"]]["content"] == before[done["_id"]]["content"]
    assert after[done["_id"]]["pdf_sha256"] == before[done["_id"]]["pdf_sha256"]
    # A board change does not touch a final report
    stale_at = (await repo.get(report.db, new["id"]))["facts_stale_at"]
    report.clock.advance(minutes=5)
    await repo.mark_stale(report.db, vf.VISIT, report.clock.now(), None)  # type: ignore[arg-type]
    assert (await repo.get(report.db, new["id"]))["facts_stale_at"] == stale_at
    await invariant(report)


# --- verify ------------------------------------------------------------------------------------------------------


@pytest.mark.req("RPT-11")
async def test_a_pdf_can_be_checked_by_its_code_or_by_the_file(report):
    done = await final(report)
    pdf = stored(report, done["pdf_key"])
    code = done["pdf_sha256"]
    for body in ({"sha256": code}, {"sha256": code.upper()}):
        r = await report.http.post("/api/v1/reports/verify", json=body)  # no sign-in
        assert r.status_code == 200
        assert r.json() == {"match": True, "number": "VR-2026-0042-02", "version": 1,
                            "status": "final", "finalized_at": r.json()["finalized_at"]}
    by_file = await report.http.post(
        "/api/v1/reports/verify", content=pdf, headers={"Content-Type": "application/pdf"})
    assert by_file.json()["match"] is True
    # A changed file, and a code nobody issued
    other = await report.http.post(
        "/api/v1/reports/verify", content=pdf + b" ", headers={"Content-Type": "application/pdf"})
    assert other.json() == {"match": False, "number": None, "version": None, "status": None,
                            "finalized_at": None}
    assert (await report.http.post(
        "/api/v1/reports/verify", json={"sha256": "0" * 64})).json()["match"] is False
    # After a reopen it still names the old version, and says it was superseded
    await reopen(report, done)
    assert (await report.http.post(
        "/api/v1/reports/verify", json={"sha256": code})).json()["status"] == "superseded"


@pytest.mark.req("RPT-11")
async def test_verify_refuses_a_bad_code_a_huge_file_and_a_draft(report):
    d = await signed(report)
    for bad in ({"sha256": "abc"}, {}, {"sha256": "g" * 64}, {"sha256": "0" * 64, "x": 1}):
        r = await report.http.post("/api/v1/reports/verify", json=bad)
        assert r.status_code == 422
    report.svc.settings.verify_max_bytes = 100
    big = await report.http.post(
        "/api/v1/reports/verify", content=b"x" * 101, headers={"Content-Type": "application/pdf"})
    assert big.status_code == 413 and big.json()["code"] == "too_large"
    # A draft's PDF is not a report anyone holds
    await repo.request_render(report.db, d["_id"], report.clock.now())
    await render_draft(report.svc, d["_id"])
    sha = (await one(report))["draft_pdf"]["sha256"]
    assert (await report.http.post("/api/v1/reports/verify", json={"sha256": sha})).json()["match"] is False


async def test_verify_never_stores_the_file(report):
    before = await report.db["reports"].count_documents({})
    await report.http.post(
        "/api/v1/reports/verify", content=b"%PDF-1.7 anything",
        headers={"Content-Type": "application/pdf"})
    assert await report.db["reports"].count_documents({}) == before
