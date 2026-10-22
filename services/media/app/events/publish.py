"""Builds media's events (TRD §8.4) and writes them to the outbox in the caller's transaction
(rule 2). The message key is the media ID (TRD §8.1)."""

from __future__ import annotations

from typing import Any

from mms_common import outbox
from mms_common.events import Actor, Envelope, Resource
from mms_common.events import media as ev
from mms_common.ids import new_id
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

SOURCE = "media"
AUDITED = ("owner_ref", "kind", "filename", "size_bytes", "status", "visibility", "scan_status",
           "checksum_sha256", "caption")


def _view(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if doc is None else {k: doc.get(k) for k in AUDITED}


def _base(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "media_id": doc["_id"], "owner_ref": doc["owner_ref"], "kind": doc["kind"],
        "filename": doc["filename"], "size_bytes": doc["size_bytes"],
    }


class Emitter:
    """One per request or job: carries the actor, correlation ID and clock."""

    def __init__(
        self, db: AsyncDatabase[dict[str, Any]], clock: Clock, actor: Actor,
        correlation_id: str | None = None,
    ) -> None:
        self._db, self._clock, self.actor, self._correlation_id = db, clock, actor, correlation_id

    async def _emit(
        self, data: BaseModel, type_: str, doc: dict[str, Any], session: AsyncClientSession,
        before: dict[str, Any] | None,
    ) -> Envelope:
        envelope = Envelope(
            event_id=new_id(), type=type_, occurred_at=self._clock.now(), source=SOURCE,
            key=doc["_id"], aggregate_version=doc["version"], actor=self.actor,
            org_id=doc.get("org_id"), resource=Resource(type="media", id=doc["_id"]),
            correlation_id=self._correlation_id,
            audit={"before": _view(before), "after": _view(doc)},
            data=data.model_dump(mode="json"),
        )
        await outbox.add(self._db["outbox"], envelope, session=session, clock=self._clock)
        return envelope

    async def uploaded(
        self, doc: dict[str, Any], session: AsyncClientSession, before: dict[str, Any] | None
    ) -> Envelope:
        data = ev.MediaUploaded(**_base(doc), uploaded_by=doc["uploaded_by"])
        return await self._emit(data, "media.uploaded", doc, session, before)

    async def processed(
        self, doc: dict[str, Any], session: AsyncClientSession, before: dict[str, Any] | None
    ) -> Envelope:
        data = ev.MediaProcessed(
            **_base(doc), scan_status=doc["scan_status"], checksum_sha256=doc["checksum_sha256"],
            width=doc.get("width"), height=doc.get("height"), duration_s=doc.get("duration_s"),
            captured_at=doc.get("captured_at"),
        )
        return await self._emit(data, "media.processed", doc, session, before)

    async def failed(
        self, doc: dict[str, Any], reason: str, session: AsyncClientSession,
        before: dict[str, Any] | None,
    ) -> Envelope:
        return await self._emit(
            ev.MediaFailed(**_base(doc), reason=reason), "media.failed", doc, session, before
        )

    async def deleted(
        self, doc: dict[str, Any], session: AsyncClientSession, before: dict[str, Any] | None
    ) -> Envelope:
        data = ev.MediaDeleted(**_base(doc))
        return await self._emit(data, "media.deleted", doc, session, before)
