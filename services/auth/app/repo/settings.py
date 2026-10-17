"""The `settings` collection: one document per organization-wide setting, keyed by name.
Today only `branding` (the brand colours, decision W4-12)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.errors import VersionConflict
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

Db = AsyncDatabase[dict[str, Any]]

BRANDING = "branding"


def col(db: Db) -> Any:
    return db["settings"]


async def get_branding(
    db: Db, session: AsyncClientSession | None = None
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one({"_id": BRANDING}, session=session)
    return doc


async def save_branding(
    db: Db,
    material: dict[str, Any] | None,
    *,
    now: datetime,
    by: str,
    expected_version: int,
    session: AsyncClientSession,
) -> dict[str, Any]:
    """Version 0 means nothing was saved yet. A stale version raises VersionConflict."""
    # MongoDB keeps milliseconds: the answer to the PUT matches every later GET
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    if expected_version == 0:
        doc = {"_id": BRANDING, "material": material, "updated_at": now, "updated_by": by,
               "version": 1}
        try:
            await col(db).insert_one(doc, session=session)
        except DuplicateKeyError as exc:
            raise VersionConflict() from exc
        return doc
    updated: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": BRANDING, "version": expected_version},
        {"$set": {"material": material, "updated_at": now, "updated_by": by},
         "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if updated is None:
        raise VersionConflict()
    return updated
