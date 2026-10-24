"""Report's consumer group: the read model and the visit report drafts, from operations' events."""

from __future__ import annotations

from typing import Any

from mms_common.consumer import EventProcessor, Handler, SendToDlq
from mms_common.events import Envelope
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.events import readmodel_consumer, visit_consumer

GROUP = "report"
TOPICS = [*readmodel_consumer.TOPICS]  # visit_consumer reads the same topic


def combine(*groups: dict[str, Handler]) -> dict[str, Handler]:
    """One handler per event type that runs every group's handler for it, in order, in the one
    transaction (`visit.ended` updates the read model and makes the draft report)."""
    merged: dict[str, list[Handler]] = {}
    for group in groups:
        for event_type, handler in group.items():
            merged.setdefault(event_type, []).append(handler)

    def chain(chained: list[Handler]) -> Handler:
        async def run(payload: BaseModel, envelope: Envelope, session: AsyncClientSession) -> None:
            for handler in chained:
                await handler(payload, envelope, session)

        return run

    return {t: chain(hs) for t, hs in merged.items()}


def processor(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    send_to_dlq: SendToDlq,
    clock: Clock,
) -> EventProcessor:
    handlers = combine(readmodel_consumer.handlers(db), visit_consumer.handlers(db, clock))
    return EventProcessor(client, db, handlers, send_to_dlq, clock)
