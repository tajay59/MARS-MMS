"""Client Review, W18 slice 1 (PRD REQ-12 to REQ-14; TRD 3.2, 11.3; decisions W18-1 to W18-8):
the client's accept and reject, the review clock (reminders and auto-close) under a manual clock,
and the facts the close-out report reads."""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from app.jobs import review_clock
from tests.api.test_requests import act, make
from tests.api.test_visit_lock import (
    deliver,
    ended_visit,
    finalized_event,
    reopened_event,
)
from tests.api.test_visits import move, plan, request_now


def png(width: int = 300, height: int = 120) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\xff" * (width * 3) for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


SIGNATURE = base64.b64encode(png()).decode()


async def in_review(ops) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """An ended visit whose report is final: the request is in Client Review. Returns the visit,
    the request, the report id and the review's start as the page reads it."""
    visit, request, _stations = await ended_visit(ops)
    report_id = new_id()
    await deliver(ops, "report.finalized", finalized_event(visit, request, report_id))
    got = await request_now(ops, request["id"], "client_a1")
    assert got["status"] == "client_review"
    return visit, request, {"id": report_id}, got["review_started_at"]


async def another_in_review(ops) -> tuple[dict[str, Any], str]:
    """A second request of organization A, on a station of its own, in Client Review."""
    found = [await ops.station(code="JM-OTH-101", owner_org_id=ORG_A)]
    request = await make(ops, "admin", [found[0]["id"]], org_id=ORG_A)
    assigned = await act(ops, "admin", request["id"], "assign",
                         staff_ids=[SEED_USERS["tech1"].id])
    assert assigned.status_code == 200, assigned.text
    visit = (await plan(ops, "tech1", assigned.json(), found)).json()
    await move(ops, "tech1", visit["id"], "start")
    done = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert done.status_code == 200, done.text
    await deliver(ops, "report.finalized", finalized_event(done.json(), request, new_id()))
    got = await request_now(ops, request["id"], "client_a1")
    assert got["status"] == "client_review"
    return got, got["review_started_at"]


def accept_body(reviewing: str, **over: Any) -> dict[str, Any]:
    return {"reviewing": reviewing, "typed_name": "Una Client", "image": SIGNATURE,
            "attestation_accepted": True, **over}


async def accept(ops, who: str, request_id: str, reviewing: str, **over: Any):
    return await ops.http.post(f"/api/v1/requests/{request_id}/accept",
                               json=accept_body(reviewing, **over), headers=ops.bearer(who))


async def reject(ops, who: str, request_id: str, reviewing: str, reason: str = "Wrong mast"):
    return await ops.http.post(f"/api/v1/requests/{request_id}/reject",
                               json={"reviewing": reviewing, "reason": reason},
                               headers=ops.bearer(who))


async def stored(ops, request_id: str) -> dict[str, Any]:
    doc = await ops.db["requests"].find_one({"_id": request_id})
    assert doc is not None
    return doc


async def tick(ops) -> dict[str, int]:
    app = ops.app.state  # the app's own client: a session cannot cross clients
    return await review_clock.run(app.mongo, app.db, ops.clock, app.settings)


def changes(events, request_id: str) -> list[tuple[str | None, str]]:
    return [(e.data["from_status"], e.data["to_status"]) for e in events
            if e.resource.id == request_id]


# --- Entering Client Review (REQ-12) ----------------------------------------------------------


@pytest.mark.req("REQ-12")
async def test_entering_client_review_asks_the_client_and_offers_accept_and_reject(ops):
    _visit, request, _report, started = await in_review(ops)
    started_events = await ops.outbox("request.client_review_started")
    assert [e.resource.id for e in started_events] == [request["id"]]
    assert started_events[0].data["status"] == "client_review"

    mine = await request_now(ops, request["id"], "client_a1")
    assert {"accept", "reject"} <= set(mine["actions"])
    assert mine["auto_close_at"] is not None and mine["verification"] is None
    for who in ("admin", "tech1", "viewer"):  # only the client answers (REQ-13)
        theirs = await request_now(ops, request["id"], who)
        assert not {"accept", "reject"} & set(theirs["actions"]), who
    assert started == mine["review_started_at"]


# --- Accepting (REQ-13) -----------------------------------------------------------------------


@pytest.mark.req("REQ-13")
async def test_accepting_closes_the_request_and_keeps_the_signature_apart(ops):
    visit, request, report, started = await in_review(ops)
    r = await accept(ops, "client_a1", request["id"], started, comment="Thank you")
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["status"] == "closed" and done["milestones"]["closed_at"] is not None
    assert done["verification"]["outcome"] == "accepted"
    assert done["verification"]["typed_name"] == "Una Client"
    assert done["verification"]["by"]["id"] == SEED_USERS["client_a1"].id
    assert done["verification"]["comment"] == "Thank you"
    assert done["actions"] == [] and done["auto_close_at"] is None
    assert SIGNATURE not in r.text  # the drawing is never in an answer
    last = done["status_history"][-1]
    assert (last["from_status"], last["to_status"]) == ("client_review", "closed")

    doc = await stored(ops, request["id"])
    held = doc["client_verification"]
    assert held["signature"]["image"] == png() and held["signature"]["typed_name"] == "Una Client"
    assert "completed" in held["signature"]["attestation"]  # the wording shown, as shown
    assert held["reports"] == [{"visit_id": visit["id"], "ref": visit["ref"],
                                "report_id": report["id"], "report_version": 1}]

    closed = await ops.outbox("request.closed")
    assert len(closed) == 1 and closed[0].data["outcome"] == "accepted"
    assert closed[0].data["auto_closed"] is False and closed[0].data["by_id"] == held["by"]
    assert SIGNATURE not in closed[0].model_dump_json()  # rule: images never travel in events
    assert ("client_review", "closed") in changes(await ops.outbox("request.status_changed"),
                                                   request["id"])


async def test_sending_the_same_acceptance_twice_returns_the_first_result(ops):
    _visit, request, _report, started = await in_review(ops)
    first = await accept(ops, "client_a1", request["id"], started)
    again = await accept(ops, "client_a1", request["id"], started)  # the answer was lost
    assert again.status_code == 200 and again.json()["version"] == first.json()["version"]
    assert len(await ops.outbox("request.closed")) == 1


async def test_an_answer_for_an_older_review_is_refused_after_a_corrected_report(ops):
    visit, request, report, started = await in_review(ops)
    await deliver(ops, "report.reopened", reopened_event(visit, request, report["id"], 2))
    ops.clock.advance(minutes=30)
    await deliver(ops, "report.finalized", finalized_event(
        visit, request, report["id"], 2, finalized_at=ops.clock.now()))
    now = await request_now(ops, request["id"], "client_a1")
    assert now["status"] == "client_review"
    assert now["review_started_at"] != started

    stale = await accept(ops, "client_a1", request["id"], started)
    assert stale.status_code == 409 and stale.json()["code"] == "review_changed"
    assert (await stored(ops, request["id"]))["status"] == "client_review"
    fresh = await accept(ops, "client_a1", request["id"], now["review_started_at"])
    assert fresh.status_code == 200 and fresh.json()["status"] == "closed"


async def test_a_request_not_in_review_cannot_be_answered(ops):
    visit, request, _stations = await ended_visit(ops)  # report not final yet: In progress
    for answer in (accept, reject):
        r = await answer(ops, "client_a1", request["id"], ops.clock.now().isoformat())
        assert r.status_code == 409 and r.json()["code"] == "bad_transition", answer.__name__


@pytest.mark.req("NFR-6")
async def test_another_organizations_client_and_staff_cannot_answer(ops):
    _visit, request, _report, started = await in_review(ops)
    assert (await accept(ops, "client_b1", request["id"], started)).status_code == 404
    assert (await reject(ops, "client_b1", request["id"], started)).status_code == 404
    for who in ("admin", "tech1", "viewer"):
        assert (await accept(ops, who, request["id"], started)).status_code == 403, who
        assert (await reject(ops, who, request["id"], started)).status_code == 403, who
    assert (await stored(ops, request["id"]))["status"] == "client_review"


@pytest.mark.parametrize("over, code", [
    ({"image": "not a picture"}, "bad_signature"),
    ({"image": base64.b64encode(b"GIF89a....").decode()}, "bad_signature"),
    ({"image": base64.b64encode(png(1300, 100)).decode()}, "signature_too_large"),
    ({"typed_name": " x "}, "bad_name"),
])
async def test_a_signature_must_be_a_png_with_a_name(ops, over, code):
    _visit, request, _report, started = await in_review(ops)
    r = await accept(ops, "client_a1", request["id"], started, **over)
    assert r.status_code == 422 and r.json()["code"] == code
    assert (await stored(ops, request["id"]))["status"] == "client_review"


async def test_the_attestation_must_be_ticked(ops):
    _visit, request, _report, started = await in_review(ops)
    r = await accept(ops, "client_a1", request["id"], started, attestation_accepted=False)
    assert r.status_code == 422
    assert (await stored(ops, request["id"]))["status"] == "client_review"


# --- Rejecting (REQ-13) -----------------------------------------------------------------------


@pytest.mark.req("REQ-13")
async def test_rejecting_returns_the_request_to_the_same_staff_and_stops_the_clock(ops):
    visit, request, report, started = await in_review(ops)
    staff = [p["id"] for p in (await request_now(ops, request["id"]))["assigned_staff"]]
    await ops.db["requests"].update_one({"_id": request["id"]}, {"$set": {"reminders_sent": [7]}})
    r = await reject(ops, "client_a1", request["id"], started, "The mast is on the wrong side")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "assigned"  # Reopened, then straight back
    assert [p["id"] for p in body["assigned_staff"]] == staff and staff
    assert body["verification"]["outcome"] == "rejected"
    assert body["verification"]["comment"] == "The mast is on the wrong side"
    assert [(h["from_status"], h["to_status"]) for h in body["status_history"]][-2:] \
        == [("client_review", "reopened"), ("reopened", "assigned")]
    assert body["status_history"][-2]["note"] == "The mast is on the wrong side"
    assert body["status_history"][-1]["by"] is None  # the system returned it

    doc = await stored(ops, request["id"])
    assert doc["rework_since"] is not None and doc["reopen_count"] == 1
    assert doc["review_started_at"] is None and doc["reminders_sent"] == []

    reopened = await ops.outbox("request.reopened")
    assert len(reopened) == 1 and reopened[0].data["comment"] == "The mast is on the wrong side"
    assert changes(await ops.outbox("request.status_changed"), request["id"])[-2:] \
        == [("client_review", "reopened"), ("reopened", "assigned")]
    assert await tick(ops) == {"reminded": 0, "closed": 0}  # no review, nothing to remind

    # The staff finish a corrected report: a fresh review begins, with its own clock
    await deliver(ops, "report.reopened", reopened_event(visit, request, report["id"], 2))
    ops.clock.advance(hours=2)
    await deliver(ops, "report.finalized", finalized_event(
        visit, request, report["id"], 2, finalized_at=ops.clock.now()))
    again = await stored(ops, request["id"])
    assert again["status"] == "client_review" and again["review_started_at"] is not None
    assert len(await ops.outbox("request.client_review_started")) == 2


async def test_a_reason_is_needed_to_reject(ops):
    _visit, request, _report, started = await in_review(ops)
    for reason in ("", "no", "   "):
        r = await reject(ops, "client_a1", request["id"], started, reason)
        assert r.status_code == 422, reason
    assert (await stored(ops, request["id"]))["status"] == "client_review"


async def test_sending_the_same_rejection_twice_returns_the_first_result(ops):
    _visit, request, _report, started = await in_review(ops)
    first = await reject(ops, "client_a1", request["id"], started)
    again = await reject(ops, "client_a1", request["id"], started)
    assert again.status_code == 200 and again.json()["version"] == first.json()["version"]
    assert len(await ops.outbox("request.reopened")) == 1
    assert (await stored(ops, request["id"]))["reopen_count"] == 1


# --- The review clock (REQ-14) ----------------------------------------------------------------


@pytest.mark.req("REQ-14")
async def test_the_client_is_reminded_on_days_7_21_and_28(ops):
    _visit, request, _report, _started = await in_review(ops)
    ops.clock.advance(days=6, hours=23)
    assert await tick(ops) == {"reminded": 0, "closed": 0}
    ops.clock.advance(hours=1)
    assert await tick(ops) == {"reminded": 1, "closed": 0}
    assert await tick(ops) == {"reminded": 0, "closed": 0}  # a second pass changes nothing
    ops.clock.advance(days=14)
    assert await tick(ops) == {"reminded": 1, "closed": 0}
    ops.clock.advance(days=7)
    assert await tick(ops) == {"reminded": 1, "closed": 0}
    sent = await ops.outbox("request.review_reminder")
    assert [e.data["day"] for e in sent] == [7.0, 21.0, 28.0]
    assert sent[0].data["auto_close_day"] == 30.0 and sent[0].actor.name == "operations"
    assert (await stored(ops, request["id"]))["reminders_sent"] == [7.0, 21.0, 28.0]
    assert (await request_now(ops, request["id"], "client_a1"))["status"] == "client_review"


@pytest.mark.req("REQ-14")
async def test_after_an_outage_one_reminder_goes_not_three(ops):
    _visit, request, _report, _started = await in_review(ops)
    ops.clock.advance(days=22)
    assert await tick(ops) == {"reminded": 1, "closed": 0}
    sent = await ops.outbox("request.review_reminder")
    assert [e.data["day"] for e in sent] == [21.0]
    assert (await stored(ops, request["id"]))["reminders_sent"] == [7.0, 21.0]


@pytest.mark.req("REQ-14")
async def test_on_day_30_the_request_closes_itself(ops):
    visit, request, report, _started = await in_review(ops)
    ops.clock.advance(days=30)
    assert await tick(ops) == {"reminded": 0, "closed": 1}
    done = await request_now(ops, request["id"], "client_a1")
    assert done["status"] == "closed" and done["milestones"]["closed_at"] is not None
    assert done["verification"]["outcome"] == "auto_closed" and done["verification"]["by"] is None
    last = done["status_history"][-1]
    assert (last["from_status"], last["to_status"], last["by"]) == ("client_review", "closed", None)
    assert "automatically" in last["note"]
    closed = await ops.outbox("request.closed")
    assert len(closed) == 1 and closed[0].data["auto_closed"] is True
    assert closed[0].data["outcome"] == "auto_closed" and closed[0].data["by_id"] is None
    held = (await stored(ops, request["id"]))["client_verification"]
    assert held["signature"] is None and held["reports"][0]["report_id"] == report["id"]
    assert await tick(ops) == {"reminded": 0, "closed": 0}  # and it stays closed
    # A report corrected after closure leaves a Closed request as it is (RPT-6)
    await deliver(ops, "report.reopened", reopened_event(visit, request, report["id"], 2))
    assert (await request_now(ops, request["id"]))["status"] == "closed"


@pytest.mark.req("REQ-14")
async def test_a_reopened_report_stops_the_clock_and_the_thirty_days_start_again(ops):
    visit, request, report, _started = await in_review(ops)
    ops.clock.advance(days=29)
    await tick(ops)
    await deliver(ops, "report.reopened", reopened_event(visit, request, report["id"], 2))
    ops.clock.advance(days=5)
    assert await tick(ops) == {"reminded": 0, "closed": 0}  # not in review: nothing to do
    assert (await request_now(ops, request["id"]))["status"] == "in_progress"

    await deliver(ops, "report.finalized", finalized_event(
        visit, request, report["id"], 2, finalized_at=ops.clock.now()))
    assert (await stored(ops, request["id"]))["reminders_sent"] == []
    ops.clock.advance(days=29)
    first = await tick(ops)
    assert first["closed"] == 0 and first["reminded"] == 1  # day 28 of the new review
    ops.clock.advance(days=1)
    assert await tick(ops) == {"reminded": 0, "closed": 1}


async def test_an_answer_wins_over_the_clock_and_the_clock_over_a_late_answer(ops):
    _visit, request, _report, started = await in_review(ops)
    ops.clock.advance(days=30)
    # The client answers in the same instant the clock would have closed the request
    answered = await accept(ops, "client_a1", request["id"], started)
    assert answered.status_code == 200
    assert await tick(ops) == {"reminded": 0, "closed": 0}
    assert (await ops.outbox("request.closed"))[0].data["outcome"] == "accepted"

    request2, started2 = await another_in_review(ops)
    ops.clock.advance(days=31)
    assert (await tick(ops))["closed"] == 1
    late = await accept(ops, "client_a1", request2["id"], started2)
    assert late.status_code == 409 and late.json()["code"] == "bad_transition"


async def test_one_failing_request_does_not_stop_the_others(ops, monkeypatch):
    _v1, first, _r1, _s1 = await in_review(ops)
    second, _s2 = await another_in_review(ops)
    ops.clock.advance(days=30)
    real = review_clock._one

    async def flaky(client, db, clock, settings, request_id, started):
        if request_id == first["id"]:
            raise RuntimeError("boom")
        return await real(client, db, clock, settings, request_id, started)

    monkeypatch.setattr(review_clock, "_one", flaky)
    assert await tick(ops) == {"reminded": 0, "closed": 1}
    assert (await stored(ops, first["id"]))["status"] == "client_review"
    assert (await stored(ops, second["id"]))["status"] == "closed"
    monkeypatch.setattr(review_clock, "_one", real)
    assert await tick(ops) == {"reminded": 0, "closed": 1}  # next pass picks it up


# --- What the close-out report reads ----------------------------------------------------------


async def post_comment(ops, who: str, request_id: str, body: str, *, internal: bool = False):
    r = await ops.http.post(f"/api/v1/requests/{request_id}/comments",
                            json={"body": body, "internal": internal}, headers=ops.bearer(who))
    assert r.status_code == 201, r.text


@pytest.mark.req("RPT-8")
async def test_the_facts_for_the_closeout_carry_the_decision_and_leave_internal_comments_out(ops):
    visit, request, report, started = await in_review(ops)
    await post_comment(ops, "client_a1", request["id"], "Please check the mast")
    await post_comment(ops, "tech1", request["id"], "Gate code is 1234", internal=True)
    await accept(ops, "client_a1", request["id"], started, comment="Done well")

    r = await ops.http.get(f"/internal/requests/{request['id']}/closeout-facts",
                           headers=ops.service("report"))
    assert r.status_code == 200, r.text
    facts = r.json()
    assert facts["request"]["ref"] == request["ref"] and facts["request"]["status"] == "closed"
    assert facts["request"]["org_name"] == "Organization A"
    assert [v["ref"] for v in facts["visits"]] == [visit["ref"]]
    assert facts["visits"][0]["report_id"] == report["id"]
    assert facts["visits"][0]["report_version"] == 1
    assert [h["to"] for h in facts["timeline"]][-1] == "closed"
    assert [c["body"] for c in facts["comments"]] == ["Please check the mast"]
    assert "1234" not in r.text  # rule 6: internal comments are filtered where they are read
    decision = facts["decision"]
    assert decision["outcome"] == "accepted" and decision["typed_name"] == "Una Client"
    assert decision["signature_png_b64"] == SIGNATURE and decision["comment"] == "Done well"
    assert decision["reports"][0]["report_id"] == report["id"]
    assert facts["stations"] and facts["stations"][0]["time_zone"]


async def test_only_the_report_service_reads_the_closeout_facts(ops):
    _visit, request, _report, _started = await in_review(ops)
    url = f"/internal/requests/{request['id']}/closeout-facts"
    assert (await ops.http.get(url, headers=ops.service("media"))).status_code in (401, 403)
    assert (await ops.http.get(url, headers=ops.bearer("admin"))).status_code in (401, 403)
    assert (await ops.http.get(url)).status_code in (401, 403)
    missing = f"/internal/requests/{new_id()}/closeout-facts"
    assert (await ops.http.get(missing, headers=ops.service("report"))).status_code == 404


async def test_a_decision_that_is_still_open_has_no_decision_in_the_facts(ops):
    _visit, request, _report, _started = await in_review(ops)
    r = await ops.http.get(f"/internal/requests/{request['id']}/closeout-facts",
                           headers=ops.service("report"))
    assert r.json()["decision"] is None
    assert (await request_now(ops, request["id"], "client_a1"))["status"] == "client_review"


@pytest.mark.req("CRP-5")
async def test_the_facts_for_the_closeout_list_submitted_client_reports_only(ops):
    _visit, request, _report, started = await in_review(ops)
    sent = (await ops.http.post("/api/v1/client-reports", headers=ops.bearer("client_a1"),
                                json={"request_id": request["id"], "kind": "form",
                                      "title": "Gauge check"})).json()
    await ops.http.patch(f"/api/v1/client-reports/{sent['id']}", headers=ops.bearer("client_a1"),
                         json={"version": sent["version"], "summary": "Fine"})
    await ops.http.post("/api/v1/client-reports", headers=ops.bearer("client_a1"),
                        json={"request_id": request["id"], "kind": "form", "title": "A draft"})
    await ops.http.post(f"/api/v1/client-reports/{sent['id']}/submit",
                        headers=ops.bearer("client_a1"))
    await accept(ops, "client_a1", request["id"], started)
    facts = (await ops.http.get(f"/internal/requests/{request['id']}/closeout-facts",
                                headers=ops.service("report"))).json()
    assert [(r["title"], r["kind"]) for r in facts["client_reports"]] == [("Gauge check", "form")]
    assert "Fine" not in str(facts["client_reports"])  # titles and dates, never the text
