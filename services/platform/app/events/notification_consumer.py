"""The notification consumer: group `notification` (TRD §3.5, §8.5).

W4 handles account emails only (NOT-3): each event that asks for one queues a row in
`email_queue` in the same transaction as `processed_events`. The sender job sends it. In-app
notifications, WebSocket fan-out and the other email types follow in Phase 3.
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import EventProcessor, Handler, SendToDlq
from mms_common.events import Envelope
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.account_emails import EVENT_TYPES, job_for
from app.repo import emails

GROUP = "notification"


def processor(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    send_to_dlq: SendToDlq,
    clock: Clock,
) -> EventProcessor:
    async def queue_email(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        job = job_for(envelope.type, payload.model_dump())
        if job is not None:
            await emails.enqueue(db, envelope.event_id, job, clock.now(), session)

    handlers: dict[str, Handler] = {event_type: queue_email for event_type in EVENT_TYPES}
    return EventProcessor(client, db, handlers, send_to_dlq, clock)
