"""The `visit_elements` collection: the boards of a visit's stations (TRD §3.2.3, §5.2; BSD).

A client reads only shared elements of their organization's ended visits (rule 3: `org_id` and
`shared` are added here, and the visit's state is checked by the caller with the visit in hand).
Tombstones (`deleted_at`) stay in the collection and are left out of every list.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User, scoped
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session


def col(db: Db) -> Any:
    return db["visit_elements"]


def _viewer_query(viewer: User | None, query: dict[str, Any]) -> dict[str, Any]:
    if viewer is None or not viewer.is_client:
        return query
    return scoped(viewer, {**query, "shared": True})


async def get(
    db: Db, element_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any] | None:
    """Tombstones included: the caller tells a deleted element from one that never was."""
    doc: dict[str, Any] | None = await col(db).find_one(
        _viewer_query(viewer, {"_id": element_id}), session=session)
    return doc


async def for_station(
    db: Db, visit_id: str, station_id: str, viewer: User | None = None, session: Session = None
) -> list[dict[str, Any]]:
    """A station's board, newest first."""
    query = _viewer_query(viewer, {"visit_id": visit_id, "station_id": station_id,
                                   "deleted_at": None})
    cursor = col(db).find(query, session=session).sort([("created_at", -1), ("_id", -1)])
    return [d async for d in cursor]


async def for_visits(
    db: Db, visit_ids: list[str], viewer: User | None = None, session: Session = None
) -> list[dict[str, Any]]:
    """Every live element of these visits (the boards' summaries, the end of a visit)."""
    if not visit_ids:
        return []
    query = _viewer_query(viewer, {"visit_id": {"$in": sorted(set(visit_ids))},
                                   "deleted_at": None})
    return [d async for d in col(db).find(query, session=session)]


async def count_for_station(
    db: Db, visit_id: str, station_id: str, session: AsyncClientSession
) -> int:
    return int(await col(db).count_documents(
        {"visit_id": visit_id, "station_id": station_id, "deleted_at": None}, session=session))


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def save_content(
    db: Db, element_id: str, fields: dict[str, Any], *, base_version: int, now: datetime,
    by: str, device_id: str | None, session: AsyncClientSession,
) -> dict[str, Any] | None:
    """Replace the editable fields if the element is still at `base_version` and alive. None
    when it moved on or was deleted (the caller reads it to say which)."""
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": element_id, "version": base_version, "deleted_at": None},
        {"$set": {**fields, "updated_at": now, "updated_by": by, "device_id": device_id},
         "$inc": {"version": 1, "revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    return doc


async def tombstone(
    db: Db, element_id: str, *, base_version: int, now: datetime, by: str,
    session: AsyncClientSession,
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": element_id, "version": base_version, "deleted_at": None},
        {"$set": {"deleted_at": now, "deleted_by": by, "updated_at": now, "updated_by": by},
         "$inc": {"version": 1, "revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    return doc


async def set_fields(
    db: Db, element_id: str, fields: dict[str, Any], *, now: datetime, by: str,
    session: AsyncClientSession,
) -> dict[str, Any] | None:
    """Fields the server sets (`request_ref`, `config_version_ids`), without moving the content
    version the editor saves against."""
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": element_id, "deleted_at": None},
        {"$set": {**fields, "updated_at": now, "updated_by": by}, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    return doc


# --- Files (W11-27) -----------------------------------------------------------------------------
# One array operation each. They move `revision`, not `version`, so a photo that lands after a long
# upload never makes the editor's next save look stale.


async def add_media(
    db: Db, element_id: str, section: str, entry: dict[str, Any], *, now: datetime, by: str,
    session: AsyncClientSession,
) -> dict[str, Any] | None:
    """Append the entry unless the file is on the element already. None when the element is
    gone or the file is there (the caller reads the element to tell which)."""
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": element_id, "deleted_at": None,
         **{f"media.{s}.media_id": {"$ne": entry["media_id"]} for s in ("main", "before",
                                                                         "after")}},
        {"$push": {f"media.{section}": entry},
         "$set": {"updated_at": now, "updated_by": by}, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    return doc


async def change_media(
    db: Db, element_id: str, section: str, media_id: str, fields: dict[str, Any], *,
    now: datetime, by: str, session: AsyncClientSession,
) -> dict[str, Any] | None:
    sets = {f"media.{section}.$[m].{k}": v for k, v in fields.items()}
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": element_id, "deleted_at": None, f"media.{section}.media_id": media_id},
        {"$set": {**sets, "updated_at": now, "updated_by": by}, "$inc": {"revision": 1}},
        array_filters=[{"m.media_id": media_id}],
        return_document=ReturnDocument.AFTER, session=session,
    )
    return doc


async def remove_media(
    db: Db, element_id: str, section: str, media_id: str, *, now: datetime, by: str,
    session: AsyncClientSession,
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": element_id, "deleted_at": None, f"media.{section}.media_id": media_id},
        {"$pull": {f"media.{section}": {"media_id": media_id}},
         "$set": {"updated_at": now, "updated_by": by}, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    return doc
