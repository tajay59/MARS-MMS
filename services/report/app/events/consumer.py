"""Report's consumer group: the read model from operations' events."""

from __future__ import annotations

from typing import Any

from mms_common.consumer import EventProcessor, SendToDlq
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.events import readmodel_consumer

GROUP = "report"
TOPICS = [*readmodel_consumer.TOPICS]


def processor(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    send_to_dlq: SendToDlq,
    clock: Clock,
) -> EventProcessor:
    return EventProcessor(client, db, readmodel_consumer.handlers(db), send_to_dlq, clock)
