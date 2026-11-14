"""The visit lock and the visit's report status, W17 slice 1 (PRD VIS-12, RPT-6; TRD 3.2, 11.2).

The report service locks an ended visit through `/internal/visits/{id}/lock`, and its
`report.finalized` and `report.reopened` events set the visit's report status, which moves the
request into and out of Client Review (`derive_status`, already built)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.events import Envelope
from mms_common.events import report as report_ev
from mms_common.ids import new_id

from app.events import consumer
from tests.api.test_visit_board import added, two_techs
from tests.api.test_visits import a_request, move, plan, request_now

ENDED = {"additional_visit_required": False}


async def ended_visit(ops) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    visit, request, stations = await two_techs(ops)
    done = await move(ops, "tech1", visit["id"], "end", **ENDED)
    assert done.status_code == 200, done.text
    return done.json(), request, stations


def lock_body(report_id: str, version: int = 1) -> dict[str, Any]:
    return {"report_id": report_id, "report_version": version}


async def lock(ops, visit_id: str, report_id: str, version: int = 1, *, service: str = "report"):
    return await ops.http.post(f"/internal/visits/{visit_id}/lock",
                               json=lock_body(report_id, version), headers=ops.service(service))


async def unlock(ops, visit_id: str, report_id: str, version: int = 1):
    return await ops.http.post(f"/internal/visits/{visit_id}/unlock",
                               json=lock_body(report_id, version), headers=ops.service("report"))


async def stored(ops, visit_id: str) -> dict[str, Any]:
    doc = await ops.db["site_visits"].find_one({"_id": visit_id})
    assert doc is not None
    return doc


# --- The lock ------------------------------------------------------------------------------------


@pytest.mark.req("VIS-12")
async def test_the_report_service_locks_an_ended_visit_and_the_board_refuses_edits(ops):
    visit, _request, stations = await ended_visit(ops)
    report_id = new_id()
    r = await lock(ops, visit["id"], report_id)
    assert r.status_code == 200, r.text
    assert r.json()["locked"] is True and r.json()["visit_id"] == visit["id"]
    doc = await stored(ops, visit["id"])
    assert doc["locked"] is True and doc["locked_for"] == {"report_id": report_id, "version": 1}

    # No one adds to the board of a locked visit, not even an admin (VIS-12)
    for who in ("tech1", "admin"):
        refused = await ops.http.post(
            f"/api/v1/visits/{visit['id']}/stations/{stations[0]['id']}/elements",
            json={"id": new_id(), "kind": "note", "title": "Late"}, headers=ops.bearer(who))
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "locked"


async def test_locking_twice_with_the_same_pair_changes_nothing(ops):
    visit, _request, _stations = await ended_visit(ops)
    report_id = new_id()
    first = (await lock(ops, visit["id"], report_id)).json()
    second = (await lock(ops, visit["id"], report_id)).json()
    assert second == first  # same answer, the visit's version did not move


async def test_another_report_version_cannot_lock_a_locked_visit(ops):
    visit, _request, _stations = await ended_visit(ops)
    report_id = new_id()
    assert (await lock(ops, visit["id"], report_id)).status_code == 200
    for other in (lock(ops, visit["id"], report_id, 2), lock(ops, visit["id"], new_id())):
        r = await other
        assert r.status_code == 409 and r.json()["code"] == "locked_by_another_report"


async def test_a_visit_that_has_not_ended_cannot_be_locked(ops):
    visit, _request, _stations = await two_techs(ops)  # started
    r = await lock(ops, visit["id"], new_id())
    assert r.status_code == 409 and r.json()["code"] == "not_ended"


async def test_a_visit_that_does_not_exist_is_404(ops):
    assert (await lock(ops, new_id(), new_id())).status_code == 404
    assert (await unlock(ops, new_id(), new_id())).status_code == 404


@pytest.mark.req("VIS-12")
async def test_unlocking_opens_the_board_again(ops):
    visit, _request, stations = await ended_visit(ops)
    report_id = new_id()
    await lock(ops, visit["id"], report_id)
    r = await unlock(ops, visit["id"], report_id)
    assert r.status_code == 200 and r.json()["locked"] is False
    doc = await stored(ops, visit["id"])
    assert doc["locked"] is False and doc["locked_for"] is None
    again = await added(ops, "tech1", visit, stations[0], "note", title="Corrected")
    assert again["title"] == "Corrected"


async def test_a_late_unlock_of_an_old_version_leaves_a_newer_lock(ops):
    visit, _request, _stations = await ended_visit(ops)
    report_id = new_id()
    await lock(ops, visit["id"], report_id, 2)
    r = await unlock(ops, visit["id"], report_id, 1)
    assert r.status_code == 200 and r.json()["locked"] is True
    assert (await stored(ops, visit["id"]))["locked"] is True


async def test_only_the_report_service_may_lock(ops):
    visit, _request, _stations = await ended_visit(ops)
    for who in ("platform", "media"):
        assert (await lock(ops, visit["id"], new_id(), service=who)).status_code == 403
    staff = await ops.http.post(f"/internal/visits/{visit['id']}/lock",
                                json=lock_body(new_id()), headers=ops.bearer("admin"))
    assert staff.status_code in (401, 403)


# --- The report's events -------------------------------------------------------------------------


async def deliver(ops, type_: str, data) -> Outcome:
    """Hand the report service's event to operations' consumer, the way Kafka does."""
    dead: list[str] = []

    async def dlq(raw: bytes, reason: str) -> None:
        dead.append(reason)

    processor = consumer.processor(ops.app.state.mongo, ops.app.state.db, dlq, ops.clock)
    envelope = Envelope(
        event_id=new_id(), type=type_, occurred_at=ops.clock.now(), source="report",
        key=data.request_id, aggregate_version=data.version,
        resource={"type": "report", "id": data.report_id}, data=data.model_dump(mode="json"),
    )
    outcome = await processor.process(envelope.model_dump_json().encode())
    assert dead == []
    return outcome


def finalized_event(visit, request, report_id: str, version: int = 1, **over: Any):
    return report_ev.ReportFinalized(
        report_id=report_id, number=visit["ref"], version=version, visit_id=visit["id"],
        request_id=request["id"], org_id=request["org_id"], subject_ref=f"visit:{visit['id']}",
        request_ref=request["ref"], title=request["title"], staff_ids=[visit["lead"]["id"]],
        lead_staff_id=visit["lead"]["id"], finalized_at=over.pop("finalized_at", None)
        or visit["ended_at"], finalized_by=visit["lead"]["id"], pdf_sha256="a" * 64, **over,
    )


def reopened_event(visit, request, report_id: str, version: int = 2, **over: Any):
    return report_ev.ReportReopened(
        report_id=report_id, number=visit["ref"], version=version, visit_id=visit["id"],
        request_id=request["id"], org_id=request["org_id"], previous_version=version - 1,
        reason="Wrong station name", reopened_by=new_id(), request_ref=request["ref"],
        title=request["title"], staff_ids=[visit["lead"]["id"]], lead_staff_id=visit["lead"]["id"],
        **over,
    )


@pytest.mark.req("RPT-4")
async def test_a_final_report_moves_the_request_to_client_review(ops):
    visit, request, _stations = await ended_visit(ops)
    assert (await request_now(ops, request["id"]))["status"] == "in_progress"  # awaiting a report
    report_id = new_id()

    outcome = await deliver(ops, "report.finalized", finalized_event(visit, request, report_id))
    assert outcome is Outcome.APPLIED

    doc = await stored(ops, visit["id"])
    assert doc["report_status"] == "final" and doc["report_version"] == 1
    assert doc["report_id"] == report_id and doc["report_finalized_at"] is not None
    got = await request_now(ops, request["id"])
    assert got["status"] == "client_review"
    last = got["status_history"][-1]
    assert (last["from_status"], last["to_status"]) == ("in_progress", "client_review")
    assert last["by"] is None and visit["ref"] in last["note"]
    stored_request = await ops.db["requests"].find_one({"_id": request["id"]})
    assert stored_request["review_started_at"] is not None
    assert stored_request["reminders_sent"] == []
    assert "review_started_at" in stored_request["milestones"]
    changed = [e for e in await ops.outbox("request.status_changed")
               if e.resource.id == request["id"]][-1]
    assert changed.data["to_status"] == "client_review" and changed.actor.name == "report"


async def test_a_redelivered_final_event_changes_nothing(ops):
    visit, request, _stations = await ended_visit(ops)
    await deliver(ops, "report.finalized", finalized_event(visit, request, new_id()))
    version = (await stored(ops, visit["id"]))["version"]
    changes = len(await ops.outbox("request.status_changed"))
    # A new event id for the same report version: Kafka may deliver the fact twice
    await deliver(ops, "report.finalized", finalized_event(visit, request, new_id()))
    assert (await stored(ops, visit["id"]))["version"] == version
    assert len(await ops.outbox("request.status_changed")) == changes


@pytest.mark.req("RPT-6")
async def test_reopening_in_client_review_returns_the_request_to_in_progress(ops):
    visit, request, _stations = await ended_visit(ops)
    report_id = new_id()
    await deliver(ops, "report.finalized", finalized_event(visit, request, report_id))
    assert (await request_now(ops, request["id"]))["status"] == "client_review"
    await ops.db["requests"].update_one({"_id": request["id"]},
                                        {"$set": {"reminders_sent": [7]}})

    await deliver(ops, "report.reopened", reopened_event(visit, request, report_id, 2))

    doc = await stored(ops, visit["id"])
    assert doc["report_status"] == "draft" and doc["report_version"] == 2
    assert doc["report_finalized_at"] is None
    got = await request_now(ops, request["id"])
    assert got["status"] == "in_progress"
    stored_request = await ops.db["requests"].find_one({"_id": request["id"]})
    assert stored_request["review_started_at"] is None and stored_request["reminders_sent"] == []

    # Finalized again as version 2: a fresh Client Review starts
    ops.clock.advance(minutes=30)
    await deliver(ops, "report.finalized", finalized_event(visit, request, report_id, 2))
    again = await ops.db["requests"].find_one({"_id": request["id"]})
    assert again["status"] == "client_review"
    assert again["review_started_at"] > stored_request["updated_at"] - timedelta(days=1)


async def test_a_late_final_event_for_an_older_version_does_not_undo_a_reopen(ops):
    visit, request, _stations = await ended_visit(ops)
    report_id = new_id()
    await deliver(ops, "report.finalized", finalized_event(visit, request, report_id))
    await deliver(ops, "report.reopened", reopened_event(visit, request, report_id, 2))
    await deliver(ops, "report.finalized", finalized_event(visit, request, report_id, 1))
    assert (await stored(ops, visit["id"]))["report_status"] == "draft"
    assert (await request_now(ops, request["id"]))["status"] == "in_progress"


async def test_a_request_stays_in_progress_until_every_visit_report_is_final(ops):
    request, stations = await a_request(ops)
    ended = []
    for _ in range(2):  # a station holds one live visit at a time (W10-5), so one after the other
        visit = (await plan(ops, "tech1", request, stations)).json()
        await move(ops, "tech1", visit["id"], "start")
        done = await move(ops, "tech1", visit["id"], "end", **ENDED)
        assert done.status_code == 200, done.text
        ended.append(done.json())

    await deliver(ops, "report.finalized", finalized_event(ended[0], request, new_id()))
    assert (await request_now(ops, request["id"]))["status"] == "in_progress"  # one still open

    await deliver(ops, "report.finalized", finalized_event(ended[1], request, new_id()))
    assert (await request_now(ops, request["id"]))["status"] == "client_review"


async def test_a_visit_that_asks_for_another_visit_is_not_sent_to_client_review(ops):
    visit, request, _stations = await two_techs(ops)
    done = await move(ops, "tech1", visit["id"], "end", additional_visit_required=True,
                       follow_up_notes="Come back with a new mast clamp")
    assert done.status_code == 200
    ended = done.json()
    await deliver(ops, "report.finalized", finalized_event(ended, request, new_id()))
    assert (await request_now(ops, request["id"]))["status"] == "assigned"


async def test_events_for_a_visit_this_service_never_had_are_ignored(ops):
    visit, request, _stations = await ended_visit(ops)
    stranger = {**visit, "id": new_id()}
    outcome = await deliver(ops, "report.finalized", finalized_event(stranger, request, new_id()))
    assert outcome is Outcome.APPLIED
    assert (await request_now(ops, request["id"]))["status"] == "in_progress"


async def test_the_other_report_events_are_not_operations_business(ops):
    visit, request, _stations = await ended_visit(ops)
    drafted = report_ev.ReportDrafted(
        report_id=new_id(), number=visit["ref"], version=1, visit_id=visit["id"],
        request_id=request["id"], request_ref=request["ref"], org_id=request["org_id"],
        title=request["title"], staff_ids=[], lead_staff_id=visit["lead"]["id"])
    assert await deliver(ops, "report.drafted", drafted) is Outcome.APPLIED
    assert (await stored(ops, visit["id"]))["report_status"] == "none"
