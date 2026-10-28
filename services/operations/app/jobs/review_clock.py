"""The Client Review clock (PRD REQ-14; TRD §3.2 cron; decisions W18-7, W18-8).

Every few minutes, under the Redis lock of `mms_common.cron`, each request that is waiting for the
client is looked at: when a configured reminder day has passed the client is reminded
(`request.review_reminder`), and when the auto-close day has passed the request closes by itself
(`request.closed` with `auto_closed`). Each request is one transaction guarded by its status and
the review it was read in, so a client who answers at the same moment wins or loses cleanly, and
running the job twice changes nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.errors import Conflict
from mms_common.events import Actor
from mms_common.events import operations as ev
from mms_common.ids import new_id
from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.config import Settings
from app.domain.requests import review
from app.domain.requests.state import MILESTONES, Action, Status, Who, transition
from app.events.publish import Emitter
from app.events.settle import history_entry
from app.repo.requests import requests as repo
from app.repo.visits import visits as visit_repo

log = get_logger(__name__)
SYSTEM = Actor(roles=["service"], name="operations")
BATCH = 200


async def run(
    client: AsyncMongoClient[dict[str, Any]], db: AsyncDatabase[dict[str, Any]], clock: Clock,
    settings: Settings,
) -> dict[str, int]:
    """One pass. Returns how many requests were reminded and closed (for the log and tests)."""
    done = {"reminded": 0, "closed": 0}
    waiting = repo.col(db).find(
        {"status": Status.CLIENT_REVIEW.value, "review_started_at": {"$ne": None}},
    ).sort("review_started_at", 1).limit(BATCH)
    async for doc in waiting:
        try:
            outcome = await _one(client, db, clock, settings, doc["_id"], doc["review_started_at"])
        except Conflict:  # answered or reopened while we looked: the next pass sees the new state
            continue
        except Exception:  # noqa: BLE001 - one bad request does not stop the others
            log.exception("review_clock_failed", request_id=doc["_id"])
            continue
        if outcome:
            done[outcome] += 1
    return done


async def _one(
    client: AsyncMongoClient[dict[str, Any]], db: AsyncDatabase[dict[str, Any]], clock: Clock,
    settings: Settings, request_id: str, started: datetime,
) -> str | None:
    emitter = Emitter(db, clock, SYSTEM, None)
    now = clock.now()
    event_id = new_id()

    async def save(s: AsyncClientSession) -> str | None:
        fresh = await repo.get(db, request_id, None, s)
        if (
            fresh is None or fresh["status"] != Status.CLIENT_REVIEW.value
            or not review.same_review(fresh.get("review_started_at"), started)
        ):
            return None  # the client answered, or the review began again
        step = review.due(now, fresh["review_started_at"], fresh.get("reminders_sent", []),
                          settings.reminder_days, settings.auto_close_days)
        if step.action == "remind" and step.day is not None:
            updated = await repo.update(
                db, request_id,
                {"reminders_sent": sorted({*fresh.get("reminders_sent", []), *step.mark})},
                now=now, by=None, session=s,
                expected_status=Status.CLIENT_REVIEW.value,
            )
            await emitter.request(
                ev.RequestReviewReminder, "request.review_reminder", updated, s, before=fresh,
                day=step.day, auto_close_day=settings.auto_close_days,
            )
            return "reminded"
        if step.action == "close":
            to = transition(Status.CLIENT_REVIEW, Action.AUTO_CLOSE, Who.SYSTEM)
            milestones = dict(fresh.get("milestones", {}))
            milestones.setdefault(MILESTONES[Status.CLOSED], now)
            visits = await visit_repo.for_request(db, request_id, None, s)
            record = review.decision(
                "auto_closed", user_id=None, name=None, at=now,
                reviewing=fresh["review_started_at"], reports=review.final_reports(visits),
            )
            updated = await repo.update(
                db, request_id,
                {"status": to.value, "milestones": milestones, "client_verification": record},
                now=now, by=None, session=s, expected_status=Status.CLIENT_REVIEW.value,
                history=history_entry(
                    from_status=Status.CLIENT_REVIEW.value, to=to, by=None, by_name=None, now=now,
                    event_id=event_id,
                    note=f"Closed automatically after {settings.auto_close_days:g} days "
                         "without an answer",
                ),
            )
            await emitter.request(ev.RequestClosed, "request.closed", updated, s, before=fresh,
                                  outcome="auto_closed", auto_closed=True)
            await emitter.request_status(updated, s, from_status=Status.CLIENT_REVIEW.value,
                                         event_id=event_id)
            return "closed"
        return None

    return await in_transaction(client, save)
