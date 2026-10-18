"""The `operations` consumer group on `mms.auth.events` (TRD §3.2 "Consumes", §8.5).

`org.created` and `org.updated` keep operations' copy of each organization (name, country,
status) and refresh the owner name copied onto its stations. The copy is guarded by
`aggregate_version`, so events and the snapshot backfill can arrive in any order (§8.6).
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

from app.repo.stations import orgs, stations

GROUP = "operations"
TOPICS = ["mms.auth.events"]


async def apply_org(
    db: AsyncDatabase[dict[str, Any]],
    data: dict[str, Any],
    version: int,
    session: AsyncClientSession | None = None,
) -> None:
    if await orgs.upsert(db, data, version, session):
        await stations.rename_owner(db, data["org_id"], data["name"], session)


def processor(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    send_to_dlq: SendToDlq,
    clock: Clock,
) -> EventProcessor:
    async def org_changed(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        await apply_org(db, payload.model_dump(), envelope.aggregate_version, session)

    handlers: dict[str, Handler] = {"org.created": org_changed, "org.updated": org_changed}
    return EventProcessor(client, db, handlers, send_to_dlq, clock)
