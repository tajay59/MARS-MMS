"""The `documents`, `config_versions` and `media_outcomes` collections (TRD §5.2).

Org scoping for documents lives in `visible` (rule 3): a client reads a station document
of their organization, and a model document while that model is installed at one of their
stations (BSD B4); both only when current, client-visible and clean.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User
from mms_common.errors import NotFound
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain.stations.documents import DocStatus, Scope
from app.repo.stations.common import Db, Session, update_versioned


def col(db: Db) -> Any:
    return db["documents"]


async def visible(db: Db, viewer: User) -> dict[str, Any]:
    """The filter every document read for `viewer` starts from."""
    if not viewer.is_client:
        return {}
    org = viewer.org_id
    if not org:
        return {"_id": {"$in": []}}
    models = await db["sensor_units"].distinct(
        "model_id", {"current_org_id": org, "status": "installed"}
    )
    return {
        "client_visible": True, "is_current": True, "status": DocStatus.AVAILABLE.value,
        "$or": [
            {"scope": Scope.STATION.value, "org_id": org},
            {"scope": Scope.MODEL.value, "scope_id": {"$in": models}},
        ],
    }


def _both(*queries: dict[str, Any]) -> dict[str, Any]:
    return {"$and": [q for q in queries if q]}


async def get(db: Db, doc_id: str, viewer: User | None = None, session: Session = None) -> Any:
    query: dict[str, Any] = {"_id": doc_id}
    if viewer is not None:
        query = _both(query, await visible(db, viewer))
    return await col(db).find_one(query, session=session)


async def search(
    db: Db, viewer: User, *, scope: str | None, scope_id: str | None, doc_type: str | None,
    current_only: bool, after: str | None, limit: int,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if scope:
        query["scope"] = scope
    if scope_id:
        query["scope_id"] = scope_id
    if doc_type:
        query["doc_type"] = doc_type
    if current_only:
        query["is_current"] = True
    if after:
        query["_id"] = {"$gt": after}
    cursor = col(db).find(_both(query, await visible(db, viewer))).sort("_id", 1).limit(limit)
    return [d async for d in cursor]


async def for_station(db: Db, viewer: User, station_id: str, model_ids: list[str]) -> Any:
    """A station's own documents and those of the models installed there, current versions."""
    base = await visible(db, viewer)
    own = col(db).find(_both({"scope": "station", "scope_id": station_id, "is_current": True},
                             base)).sort("_id", 1)
    # A model's photos belong in its gallery, not in a station's list of documents
    models = col(db).find(_both({"scope": "model", "scope_id": {"$in": model_ids},
                                 "is_current": True, "doc_type": {"$ne": "photo"}},
                                base)).sort("_id", 1)
    return [d async for d in own], [d async for d in models]


async def photos_by_model(db: Db) -> dict[str, list[str]]:
    """The ready photos of each model, oldest first: the first is its cover (staff only)."""
    query = {"scope": Scope.MODEL.value, "doc_type": "photo", "is_current": True,
             "status": DocStatus.AVAILABLE.value}
    found: dict[str, list[str]] = {}
    async for d in col(db).find(query, {"scope_id": 1}).sort("_id", 1):
        found.setdefault(d["scope_id"], []).append(d["_id"])
    return found


async def by_media(db: Db, media_id: str, session: Session = None) -> dict[str, Any] | None:
    found: dict[str, Any] | None = await col(db).find_one(
        {"media_id": media_id}, session=session
    )
    return found


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db, doc_id: str, changes: dict[str, Any], *, now: datetime, by: str | None,
    expected_version: int | None, session: AsyncClientSession,
) -> dict[str, Any]:
    return await update_versioned(
        col(db), doc_id, changes, now=now, by=by, expected_version=expected_version,
        session=session,
    )


# --- media outcomes ---------------------------------------------------------------------------
#
# Media's verdict on a file (`media.processed` / `media.failed`) can arrive before the
# document that points at the file exists, or in the same instant. Both the consumer and the
# document insert write this one row, so the database orders them: whichever commits second
# sees the other's work (two transactions that write different rows would not).


async def touch_outcome(
    db: Db, media_id: str, now: datetime, session: AsyncClientSession
) -> dict[str, Any]:
    """Read the verdict for a file, writing the row so a concurrent consumer conflicts."""
    found: dict[str, Any] | None = await db["media_outcomes"].find_one_and_update(
        {"_id": media_id}, {"$set": {"touched_at": now}, "$setOnInsert": {"outcome": None}},
        upsert=True, return_document=ReturnDocument.AFTER, session=session,
    )
    return found or {}


async def record_outcome(
    db: Db, media_id: str, outcome: dict[str, Any], now: datetime, session: AsyncClientSession
) -> None:
    await db["media_outcomes"].update_one(
        {"_id": media_id}, {"$set": {"outcome": outcome, "touched_at": now}}, upsert=True,
        session=session,
    )


# --- configuration versions -------------------------------------------------------------------


def versions(db: Db) -> Any:
    return db["config_versions"]


async def next_version(
    db: Db, station_id: str, session: AsyncClientSession
) -> int:
    """The station's next configuration version number, taken atomically."""
    doc = await db["stations"].find_one_and_update(
        {"_id": station_id}, {"$inc": {"config_version_seq": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if doc is None:
        raise NotFound()
    number = int(doc["config_version_seq"])
    await db["stations"].update_one(
        {"_id": station_id}, {"$set": {"current_config_version": number}}, session=session
    )
    return number


async def list_versions(db: Db, station_id: str) -> list[dict[str, Any]]:
    cursor = versions(db).find({"station_id": station_id}).sort("version", -1)
    return [d async for d in cursor]


async def get_version(
    db: Db, station_id: str, number: int, session: Session = None
) -> dict[str, Any] | None:
    found: dict[str, Any] | None = await versions(db).find_one(
        {"station_id": station_id, "version": number}, session=session
    )
    return found


async def version_by_id(db: Db, version_id: str, session: Session = None) -> Any:
    return await versions(db).find_one({"_id": version_id}, session=session)


async def version_with_file(db: Db, media_id: str, session: Session = None) -> Any:
    return await versions(db).find_one({"files.media_id": media_id}, session=session)


async def insert_version(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await versions(db).insert_one(doc, session=session)
