"""The `sensor_models` catalogue (SEN-1). Staff only; clients see a model only as part of a
unit installed at their station."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.errors import NotFound
from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session, contains, update_versioned


def col(db: Db) -> Any:
    return db["sensor_models"]


async def search(
    db: Db, *, kind: str | None, parameter: str | None, q: str | None
) -> list[dict[str, Any]]:
    """The whole catalogue matching the filters: it stays small (tens to hundreds)."""
    query: dict[str, Any] = {}
    if kind:
        query["kind"] = kind
    if parameter:
        query["parameters"] = parameter
    if q:
        query["$or"] = [{"manufacturer": contains(q)}, {"model": contains(q)}]
    cursor = col(db).find(query).sort([("manufacturer", 1), ("model", 1)]).limit(1000)
    return [d async for d in cursor]


async def get(db: Db, model_id: str, session: Session = None) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one({"_id": model_id}, session=session)
    return doc


async def require(db: Db, model_id: str, session: Session = None) -> dict[str, Any]:
    doc = await get(db, model_id, session)
    if doc is None:
        raise NotFound()
    return doc


async def by_ids(db: Db, ids: list[str], session: Session = None) -> dict[str, dict[str, Any]]:
    cursor = col(db).find({"_id": {"$in": list(set(ids))}}, session=session)
    return {d["_id"]: d async for d in cursor}


async def by_key(db: Db) -> dict[str, dict[str, Any]]:
    return {d["key"]: d async for d in col(db).find({})}


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db, model_id: str, changes: dict[str, Any], *, now: datetime, by: str,
    expected_version: int, session: AsyncClientSession,
) -> dict[str, Any]:
    return await update_versioned(
        col(db), model_id, changes, now=now, by=by, expected_version=expected_version,
        session=session,
    )
