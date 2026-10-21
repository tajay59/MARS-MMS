"""The notification consumer: group `notification` (TRD §3.5, §8.5).

Three jobs, all in the transaction that also records the event as processed:

- account emails (NOT-3): each auth event that asks for one queues a row in `email_queue`;
- the user directory: every `user.*` event updates the copy of the person;
- in-app notifications and live updates (NOT-1, NOT-5): `domain/notifications.plan` decides who
  is told what; the rows are written here and pushed to Redis once the transaction has committed.

Email for the request events follows in W9 slice 4.
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import EventProcessor, Handler, Outcome, SendToDlq
from mms_common.events import Envelope
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from app import realtime
from app.domain.account_emails import EVENT_TYPES, EmailJob, Kind, job_for
from app.domain.notifications import LIVE_EVENTS, NOTIFY_EVENTS, plan
from app.repo import directory, emails, notifications

GROUP = "notification"
USER_EVENTS = (
    "user.registered", "user.invited", "user.created", "user.approved", "user.rejected",
    "user.updated", "user.disabled",
)
Push = tuple[str, dict[str, Any]]


class NotificationProcessor(EventProcessor):
    """Pushes after the commit, never before: a rolled-back transaction must not have told
    anyone."""

    def __init__(
        self, *args: Any, pending: list[Push], redis: Redis | None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._pending, self._redis = pending, redis

    async def process(self, raw: bytes) -> Outcome:
        self._pending.clear()
        outcome = await super().process(raw)
        if outcome is Outcome.APPLIED and self._redis is not None and self._pending:
            await realtime.publish(self._redis, list(self._pending))
        self._pending.clear()
        return outcome


def processor(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    send_to_dlq: SendToDlq,
    clock: Clock,
    redis: Redis | None = None,
) -> NotificationProcessor:
    pending: list[Push] = []

    async def queue_email(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        job = job_for(envelope.type, payload.model_dump())
        if job is not None:
            await emails.enqueue(db, envelope.event_id, job, clock.now(), session)

    async def update_directory(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        await directory.upsert(db, payload.model_dump(), envelope.aggregate_version, session)

    async def drop_from_directory(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        await directory.remove(db, payload.model_dump()["user_id"], session)

    async def notify(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        now = clock.now()
        who = await directory.audience(db, envelope.org_id, session)
        made = plan(
            envelope.type, payload.model_dump(), envelope.actor.user_id, envelope.actor.name, who
        )
        rows = await notifications.insert_many(db, made.drafts, envelope.event_id, now, session)
        # An email follows the notifications Appendix B says go by email too; the person's
        # choice is looked at when it is sent (NOT-4), so a change takes effect at once
        for draft, row in zip(made.drafts, rows, strict=True):
            if draft.email:
                await emails.enqueue(
                    db, row["_id"],
                    EmailJob(Kind.NOTIFICATION, row["user_id"], notification_id=row["_id"]),
                    now, session,
                )
        # Set, not extended: a retried event starts again from nothing
        pending[:] = [(row["user_id"], realtime.notification_message(row)) for row in rows]
        pending.extend(
            (item.user_id, realtime.entity_message(item.entity_id, item.status, item.kind))
            for item in made.live
        )

    def chain(*steps: Handler) -> Handler:
        async def run(payload: BaseModel, envelope: Envelope, session: AsyncClientSession) -> None:
            for step in steps:
                await step(payload, envelope, session)

        return run

    handlers: dict[str, Handler] = {}
    for event_type in EVENT_TYPES:
        handlers[event_type] = queue_email
    for event_type in USER_EVENTS:
        steps = [update_directory]
        if event_type in EVENT_TYPES:
            steps.append(queue_email)
        if event_type in NOTIFY_EVENTS:
            steps.append(notify)
        handlers[event_type] = chain(*steps)
    handlers["user.purged"] = drop_from_directory
    for event_type in NOTIFY_EVENTS | LIVE_EVENTS:
        handlers.setdefault(event_type, notify)
    return NotificationProcessor(
        client, db, handlers, send_to_dlq, clock, pending=pending, redis=redis
    )
