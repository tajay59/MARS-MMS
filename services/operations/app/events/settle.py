"""A request's status from its visits, written in the caller's transaction (ADR-17; W10-6).

Shared by the visit routes (a person moved a visit) and the report consumer (a visit report became
final or was reopened, so the request may enter or leave Client Review). Both read the request's
visits inside their transaction, derive the status with `recompute`, and write it with its history
entry and `request.status_changed` through the outbox (rule 2).
"""

from __future__ import annotations

from typing import Any

from mms_common.errors import NotFound
from mms_common.ids import new_id
from mms_common.time import Clock
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.requests.recompute import recompute
from app.domain.requests.state import MILESTONES, Status
from app.events.publish import Emitter
from app.repo.requests import requests as request_repo
from app.repo.visits import visits as visit_repo


async def lock_request(
    db: AsyncDatabase[dict[str, Any]], request_id: str, s: AsyncClientSession
) -> dict[str, Any]:
    """Take the request, and make two visit changes on it queue up.

    The write moves `visit_seq`, not `version` (a request editor's stale-write check must not
    trip over a visit being planned). A second transaction touching the same request waits or
    retries here, so it derives the status from visits that include the first one's change.
    """
    doc: dict[str, Any] | None = await request_repo.col(db).find_one_and_update(
        {"_id": request_id}, {"$inc": {"visit_seq": 1}},
        return_document=ReturnDocument.AFTER, session=s,
    )
    if doc is None:
        raise NotFound()
    return doc


def history_entry(
    *, from_status: str, to: Status, by: str | None, by_name: str | None, now: Any,
    event_id: str, note: str,
) -> dict[str, Any]:
    return {
        "from": from_status, "to": to.value, "by": by, "by_name": by_name, "at": now,
        "note": note, "event_id": event_id,
    }


async def settle_request(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, emitter: Emitter, request: dict[str, Any],
    s: AsyncClientSession, *, by: str | None, by_name: str | None, note: str,
) -> dict[str, Any]:
    """Derive the request's status from its visits and write it when it moved, with the first
    visit's start as a milestone. `by` is None when the system moved it (a report event).
    Entering Client Review starts its clock (`review_started_at`, no reminders sent); leaving it
    stops the clock, so a reopened report halts reminders and auto-close (RPT-6). Returns the
    request as it is."""
    visits = await visit_repo.for_request(db, request["_id"], None, s)
    settled = recompute(request, visits)
    now = clock.now()
    milestones = dict(request.get("milestones", {}))
    changes: dict[str, Any] = {}
    if settled.first_visit_at is not None and "first_visit_at" not in milestones:
        milestones["first_visit_at"] = settled.first_visit_at
        changes["milestones"] = milestones
    before = request["status"]
    if settled.status.value != before:
        changes["status"] = settled.status.value
        changes["milestones"] = milestones
        if settled.status is Status.CLIENT_REVIEW:
            milestones.setdefault(MILESTONES[Status.CLIENT_REVIEW], now)
            changes["review_started_at"] = now
            changes["reminders_sent"] = []
        elif before == Status.CLIENT_REVIEW.value:
            changes["review_started_at"] = None
            changes["reminders_sent"] = []
    if not changes:
        return request
    event_id = new_id()
    history = (
        history_entry(from_status=before, to=settled.status, by=by, by_name=by_name, now=now,
                      event_id=event_id, note=note)
        if "status" in changes else None
    )
    updated = await request_repo.update(
        db, request["_id"], changes, now=now, by=by, session=s, history=history,
    )
    if "status" in changes:
        await emitter.request_status(updated, s, from_status=before, event_id=event_id)
    return updated
