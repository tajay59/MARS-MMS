"""Revoked QR tokens (QR-7). A regenerated label leaves its old token here, so scanning an old
label says "no longer valid" instead of "not found" (AFD §5.3). The station's current token
lives on the station itself."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session


def col(db: Db) -> Any:
    return db["qr_revoked"]


async def revoke(
    db: Db, token: str, *, station_id: str, now: datetime, by: str, session: AsyncClientSession
) -> None:
    await col(db).insert_one(
        {"_id": token, "station_id": station_id, "revoked_at": now, "revoked_by": by},
        session=session,
    )


async def revoked_station(db: Db, token: str, session: Session = None) -> str | None:
    """The station a revoked token belonged to, or None if the token was never revoked."""
    doc = await col(db).find_one({"_id": token}, {"station_id": 1}, session=session)
    return None if doc is None else str(doc["station_id"])
