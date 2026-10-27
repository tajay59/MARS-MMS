"""The `signatures` collection (TRD 5.4, 11.3; W17-3, W17-4, W17-6).

A signature is never deleted. One that no longer applies (the report changed after it was signed,
or the report was reopened) is kept with `valid: false`, `cleared_at` and `cleared_by`. Only valid
ones count. The drawn image is stored as bytes and leaves the service only inside a staff reader's
`GET /reports/{id}`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]


def col(db: Db) -> Any:
    return db["signatures"]


async def for_report(
    db: Db, report_id: str, session: AsyncClientSession | None = None
) -> list[dict[str, Any]]:
    """Every signature of every version of this report, oldest first (cleared ones too)."""
    cursor = col(db).find({"report_id": report_id}, session=session).sort("signed_at", 1)
    return [d async for d in cursor]


async def valid(
    db: Db, report_id: str, version: int, session: AsyncClientSession | None = None
) -> list[dict[str, Any]]:
    cursor = col(db).find(
        {"report_id": report_id, "report_version": version, "valid": True}, session=session,
    ).sort("signed_at", 1)
    return [d async for d in cursor]


async def valid_by(
    db: Db, report_id: str, version: int, signer_id: str, session: AsyncClientSession
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one(
        {"report_id": report_id, "report_version": version, "signer_id": signer_id,
         "valid": True}, session=session)
    return doc


async def add(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def clear(
    db: Db, report_id: str, version: int, *, by: str, now: datetime,
    session: AsyncClientSession,
) -> int:
    """Mark the report version's valid signatures as cleared; returns how many were."""
    result = await col(db).update_many(
        {"report_id": report_id, "report_version": version, "valid": True},
        {"$set": {"valid": False, "cleared_at": now, "cleared_by": by}}, session=session,
    )
    return int(result.modified_count)
