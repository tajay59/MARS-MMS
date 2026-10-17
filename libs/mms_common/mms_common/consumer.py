"""Consumer rules (TRD §8.5), separate from Kafka so they can be tested without a broker.

1. Validate the envelope and its payload; unknown type or invalid payload -> DLQ at once.
2. In ONE transaction: insert `processed_events {_id: event_id}` (duplicate key = already
   handled), then apply the effect.
3. Retry transient errors (5 times, 1 s -> 30 s backoff), then DLQ. Never skip an event
   without a DLQ record.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from mms_common.events import Envelope, UnknownEvent, validate
from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from mms_common.time import Clock

MAX_ATTEMPTS = 5
BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 30.0

log = get_logger(__name__)

# The effect gets the validated payload, the envelope and the transaction's session.
Handler = Callable[[BaseModel, Envelope, AsyncClientSession], Awaitable[None]]
SendToDlq = Callable[[bytes, str], Awaitable[None]]
"""`send_to_dlq(raw_message, reason)` publishes to `mms.dlq.<consumer-service>`."""


class Outcome(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    DEAD_LETTERED = "dead_lettered"


class EventProcessor:
    """Returns after the message is safely handled, so the caller can commit the offset."""

    def __init__(
        self,
        client: AsyncMongoClient[dict[str, Any]],
        db: AsyncDatabase[dict[str, Any]],
        handlers: dict[str, Handler],
        send_to_dlq: SendToDlq,
        clock: Clock,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        default: Handler | None = None,
    ) -> None:
        """`default` handles every type missing from `handlers` (the audit consumer)."""
        self._client = client
        self._db = db
        self._handlers = handlers
        self._dlq = send_to_dlq
        self._clock = clock
        self._sleep = sleep
        self._default = default

    async def process(self, raw: bytes) -> Outcome:
        try:
            envelope = Envelope.model_validate_json(raw)
            payload = validate(envelope)
        except (ValidationError, UnknownEvent) as exc:
            await self._dlq(raw, f"invalid: {exc}")
            return Outcome.DEAD_LETTERED

        handler = self._handlers.get(envelope.type, self._default)
        if handler is None:
            return Outcome.APPLIED  # this consumer does not care about the event type

        delay = BACKOFF_START_S
        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self._apply(envelope, payload, handler)
            except Exception as exc:  # noqa: BLE001 - any failure is retried, then dead-lettered
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning("event_failed", event_id=envelope.event_id, attempt=attempt)
                if attempt < MAX_ATTEMPTS:
                    await self._sleep(delay)
                    delay = min(delay * 2, BACKOFF_MAX_S)
        await self._dlq(raw, f"failed after {MAX_ATTEMPTS} attempts: {last_error}")
        return Outcome.DEAD_LETTERED

    async def _apply(self, envelope: Envelope, payload: BaseModel, handler: Handler) -> Outcome:
        async def body(session: AsyncClientSession) -> Outcome:
            # An upsert, not an insert: a duplicate-key error would abort the transaction on
            # the server, and the driver would retry it until its timeout.
            marked = await self._db["processed_events"].update_one(
                {"_id": envelope.event_id},
                {"$setOnInsert": {"processed_at": self._clock.now()}},
                upsert=True,
                session=session,
            )
            if marked.upserted_id is None:
                return Outcome.DUPLICATE
            await handler(payload, envelope, session)
            return Outcome.APPLIED

        return await in_transaction(self._client, body)
