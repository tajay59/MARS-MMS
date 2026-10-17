"""The audit consumer: group `audit` on every `mms.*.events` topic (TRD §8.1, §12).

Runs through `mms_common.consumer.EventProcessor`, so each event is validated, applied once
(`processed_events` in the same transaction as the append), retried, and dead-lettered to
`mms.dlq.audit` rather than dropped.
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import EventProcessor, SendToDlq
from mms_common.events import Envelope
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.audit import audited, to_record
from app.repo import audit

GROUP = "audit"


def processor(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    send_to_dlq: SendToDlq,
    clock: Clock,
) -> EventProcessor:
    async def record(_: BaseModel, envelope: Envelope, session: AsyncClientSession) -> None:
        if audited(envelope.type):
            await audit.append(db, to_record(envelope, clock.now()), session)

    return EventProcessor(client, db, {}, send_to_dlq, clock, default=record)
