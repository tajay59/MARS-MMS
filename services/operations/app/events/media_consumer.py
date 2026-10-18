"""Media's verdicts on files (`mms.media.events`, TRD §3.2 "Consumes").

`media.processed` makes a pending document available; `media.failed` marks it failed. The
verdict is also kept in `media_outcomes`, because it can arrive before the document that
points at the file exists (see `repo.documents.touch_outcome`).
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import Handler
from mms_common.events import Actor, Envelope
from mms_common.events import media as media_ev
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.stations.documents import DocStatus
from app.events.publish import Emitter, ev
from app.repo.stations import documents as repo

TOPICS = ["mms.media.events"]
SYSTEM = Actor(roles=["service"], name="media")


def handlers(db: AsyncDatabase[dict[str, Any]], clock: Clock) -> dict[str, Handler]:
    emitter = Emitter(db, clock, SYSTEM, None)

    async def settle(
        media_id: str, outcome: dict[str, Any], changes: dict[str, Any],
        session: AsyncClientSession,
    ) -> None:
        now = clock.now()
        await repo.record_outcome(db, media_id, outcome, now, session)
        doc = await repo.by_media(db, media_id, session)
        if doc is None or doc["status"] != DocStatus.PENDING.value:
            return  # no document yet (it will read the outcome), or it already has its verdict
        updated = await repo.update(db, doc["_id"], changes, now=now, by=None,
                                    expected_version=None, session=session)
        await emitter.document(ev.DocumentUpdated, updated, session, before=doc,
                               changed_fields=sorted(changes))

    async def processed(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        if not isinstance(payload, media_ev.MediaProcessed):  # pragma: no cover
            raise TypeError(type(payload).__name__)
        await settle(
            payload.media_id, {"kind": "processed", "scan_status": payload.scan_status},
            {"status": DocStatus.AVAILABLE.value, "scan_status": payload.scan_status}, session,
        )

    async def failed(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        if not isinstance(payload, media_ev.MediaFailed):  # pragma: no cover
            raise TypeError(type(payload).__name__)
        await settle(
            payload.media_id, {"kind": "failed", "reason": payload.reason},
            {"status": DocStatus.FAILED.value, "error": payload.reason}, session,
        )

    return {"media.processed": processed, "media.failed": failed}
