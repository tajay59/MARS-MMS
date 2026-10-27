"""Operations' consumer group: organizations from auth, file verdicts from media and visit report
status from the report service."""

from __future__ import annotations

from typing import Any

from mms_common.consumer import EventProcessor, SendToDlq
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.events import media_consumer, org_consumer, report_consumer

GROUP = org_consumer.GROUP
TOPICS = [*org_consumer.TOPICS, *media_consumer.TOPICS, *report_consumer.TOPICS]


def processor(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    send_to_dlq: SendToDlq,
    clock: Clock,
) -> EventProcessor:
    handlers = {
        **org_consumer.handlers(db),
        **media_consumer.handlers(db, clock),
        **report_consumer.handlers(db, clock),
    }
    return EventProcessor(client, db, handlers, send_to_dlq, clock)
