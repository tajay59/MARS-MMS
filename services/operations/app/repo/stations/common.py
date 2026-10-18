"""Helpers every stations-module collection shares."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from mms_common.errors import NotFound, VersionConflict
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]
Col = AsyncCollection[dict[str, Any]]
Session = AsyncClientSession | None


def contains(text: str) -> dict[str, Any]:
    """A case-insensitive substring match on typed input (rule 12: no raw operators)."""
    return {"$regex": re.escape(text), "$options": "i"}


def stamp(doc: dict[str, Any], now: datetime, by: str | None) -> dict[str, Any]:
    """Bookkeeping every document carries (TRD §5)."""
    return {
        **doc, "created_at": now, "updated_at": now, "created_by": by, "updated_by": by,
        "version": 1,
    }


async def update_versioned(
    col: Col,
    id_: str,
    changes: dict[str, Any],
    *,
    now: datetime,
    by: str | None,
    expected_version: int | None,
    session: AsyncClientSession,
    unset: list[str] | None = None,
) -> dict[str, Any]:
    """Apply `changes` and bump `version`. `expected_version=None` is an internal change
    made inside a transaction that already read the record."""
    query: dict[str, Any] = {"_id": id_}
    if expected_version is not None:
        query["version"] = expected_version
    update: dict[str, Any] = {
        "$set": {**changes, "updated_at": now, "updated_by": by}, "$inc": {"version": 1},
    }
    if unset:
        update["$unset"] = dict.fromkeys(unset, "")
    doc: dict[str, Any] | None = await col.find_one_and_update(
        query, update, return_document=ReturnDocument.AFTER, session=session
    )
    if doc is None:
        if await col.find_one({"_id": id_}, {"_id": 1}, session=session) is not None:
            raise VersionConflict()
        raise NotFound()
    return doc
