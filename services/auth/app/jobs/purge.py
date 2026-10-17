"""AUTH-5: pending registrations not acted on within 30 days (configurable) are deleted.

Expired refresh, reset and invitation tokens go by their TTL indexes, not by this job.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from mms_common.events import Actor
from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.events.publish import Emitter, ev
from app.repo import users

log = get_logger(__name__)
SYSTEM = Actor(name="system", roles=["service"])


async def purge_pending(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    clock: Clock,
    days: int,
) -> int:
    before = clock.now() - timedelta(days=days)
    emitter = Emitter(db, clock, SYSTEM, correlation_id=None)
    purged = 0
    for doc in await users.stale_pending(db, before):

        async def remove(s: AsyncClientSession, doc: dict[str, Any] = doc) -> bool:
            if not await users.delete_pending(db, doc["_id"], s):
                return False  # approved or rejected meanwhile
            await emitter.emit(
                ev.UserPurged(user_id=doc["_id"]),
                type_="user.purged",
                key=doc["_id"],
                resource=("user", doc["_id"]),
                aggregate_version=doc["version"] + 1,
                org_id=None,
                session=s,
                before={"email": doc["email"], "name": doc["name"], "status": doc["status"]},
            )
            return True

        if await in_transaction(client, remove):
            purged += 1
    if purged:
        log.info("pending_registrations_purged", count=purged)
    return purged
