"""The `comments` collection and the files attached to requests. A client reads only comments
on their organization's requests that are not internal (rules 3 and 6, filtered here, so
endpoint code can't forget)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User
from mms_common.errors import NotFound
from pymongo import ASCENDING
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain.stations.documents import FileFacts
from app.repo.requests.requests import col as requests_col
from app.repo.stations.common import Db, Session, update_versioned
from app.repo.stations.media_client import MediaApi


def col(db: Db) -> Any:
    return db["comments"]


def _visible(viewer: User, query: dict[str, Any]) -> dict[str, Any]:
    """Merge the reader's limits into `query`: a client sees their organization's comments
    that are not internal; staff see everything."""
    if viewer.is_client:
        return {**query, "org_id": viewer.org_id, "internal": False}
    return query


async def thread(db: Db, request_id: str, viewer: User) -> list[dict[str, Any]]:
    """Oldest first (UUIDv7 IDs sort by creation time)."""
    cursor = col(db).find(_visible(viewer, {"request_id": request_id})).sort("_id", ASCENDING)
    return [d async for d in cursor]


async def get(
    db: Db, request_id: str, comment_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any] | None:
    """`viewer=None` is an internal read (the author's own edit checks it themselves)."""
    query: dict[str, Any] = {"_id": comment_id, "request_id": request_id}
    if viewer is not None:
        query = _visible(viewer, query)
    doc: dict[str, Any] | None = await col(db).find_one(query, session=session)
    return doc


async def require(
    db: Db, request_id: str, comment_id: str, viewer: User | None = None
) -> dict[str, Any]:
    doc = await get(db, request_id, comment_id, viewer)
    if doc is None:
        raise NotFound()
    return doc


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db, comment_id: str, changes: dict[str, Any], *, now: datetime, by: str,
    expected_version: int | None, session: AsyncClientSession,
) -> dict[str, Any]:
    return await update_versioned(
        col(db), comment_id, changes, now=now, by=by, expected_version=expected_version,
        session=session,
    )


async def counts(db: Db, request_ids: list[str], viewer: User) -> dict[str, int]:
    """Comments per request, as this reader may see them."""
    rows = await col(db).aggregate([
        {"$match": _visible(viewer, {"request_id": {"$in": request_ids}})},
        {"$group": {"_id": "$request_id", "n": {"$sum": 1}}},
    ])
    return {row["_id"]: int(row["n"]) async for row in rows}


async def media_in_use(db: Db, media_id: str, session: Session = None) -> bool:
    """A file belongs to one comment or request, once."""
    if await col(db).find_one({"attachments.media_id": media_id}, {"_id": 1}, session=session):
        return True
    found = await requests_col(db).find_one({"attachments.media_id": media_id}, {"_id": 1},
                                            session=session)
    return found is not None


async def file_facts(media: MediaApi, media_id: str, request_id: str | None) -> FileFacts | None:
    """What media knows about a file, as the rules want it."""
    info = await media.info(media_id, request_id)
    if info is None:
        return None
    return FileFacts(
        owner_ref=info.owner_ref, kind=info.kind, status=info.status,
        uploaded_by=info.uploaded_by, filename=info.filename, size_bytes=info.size_bytes,
        checksum_sha256=info.checksum_sha256, scan_status=info.scan_status,
    )
