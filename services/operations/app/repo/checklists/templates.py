"""The `checklist_templates` collection. A template is a family of immutable versions: each row is
one version, and the newest has `is_current`. Staff read; only admins write (the route checks)."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session


def col(db: Db) -> Any:
    return db["checklist_templates"]


async def current(db: Db, family_id: str, session: Session = None) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one(
        {"family_id": family_id, "is_current": True}, session=session
    )
    return doc


async def at_version(
    db: Db, family_id: str, version: int, session: Session = None
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one(
        {"family_id": family_id, "version": version}, session=session
    )
    return doc


async def list_current(db: Db, *, active_only: bool) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"is_current": True}
    if active_only:
        query["active"] = True
    cursor = col(db).find(query).sort([("station_type", 1), ("name", 1), ("_id", 1)])
    return [d async for d in cursor]


async def active_for_scope(
    db: Db, key: str, session: Session = None, *, excluding_family: str | None = None
) -> dict[str, Any] | None:
    query: dict[str, Any] = {"scope_key": key, "is_current": True, "active": True}
    if excluding_family:
        query["family_id"] = {"$ne": excluding_family}
    doc: dict[str, Any] | None = await col(db).find_one(query, session=session)
    return doc


async def active_for_scopes(db: Db, keys: list[str]) -> dict[str, dict[str, Any]]:
    cursor = col(db).find({"scope_key": {"$in": keys}, "is_current": True, "active": True})
    return {d["scope_key"]: d async for d in cursor}


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def retire(db: Db, row_id: str, session: AsyncClientSession) -> None:
    """The row stops being the current version. Its content is never touched."""
    await col(db).update_one({"_id": row_id}, {"$set": {"is_current": False}}, session=session)
