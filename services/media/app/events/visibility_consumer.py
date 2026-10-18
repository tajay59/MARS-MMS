"""The `media` consumer group on `mms.operations.events` (TRD §3.3 "Consumes", ADR-19).

Every file starts `staff`. The owning service makes it visible to the owner organization only
by emitting `media.visibility_requested` in the same transaction that attaches the file, and
hides it again the same way. Media applies the newest `visibility_version` per file, so events
may arrive in any order.
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import EventProcessor, Handler, SendToDlq
from mms_common.events import Envelope
from mms_common.events import operations as ev
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.media import Visibility
from app.repo import media as repo

GROUP = "media"
TOPICS = ["mms.operations.events"]


def processor(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    send_to_dlq: SendToDlq,
    clock: Clock,
) -> EventProcessor:
    async def visibility_requested(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        if not isinstance(payload, ev.MediaVisibilityRequested):  # pragma: no cover
            raise TypeError(type(payload).__name__)
        known = await repo.existing_ids(db, payload.media_ids, session)
        missing = sorted(set(payload.media_ids) - known)
        if missing:
            # The owner attached a file this service has no record of: fail loudly (retry,
            # then the dead-letter topic) rather than guess.
            raise LookupError(f"unknown media {missing}")
        await repo.apply_visibility(
            db, payload.media_ids, Visibility(payload.visibility), payload.visibility_version,
            clock.now(), session,
        )

    handlers: dict[str, Handler] = {"media.visibility_requested": visibility_requested}
    return EventProcessor(client, db, handlers, send_to_dlq, clock)
