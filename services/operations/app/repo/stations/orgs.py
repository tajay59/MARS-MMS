"""`organizations`: operations' copy of each organization's name, short name, external ID,
country and status, from
auth's `org.*` events and snapshot (TRD §3.2 "Consumes", §8.6). auth owns the record; this
copy only names a station's owner and checks it is active."""

from __future__ import annotations

from typing import Any

from mms_common.snapshot import upsert_if_newer

from app.repo.stations.common import Db, Session


def col(db: Db) -> Any:
    return db["organizations"]


def name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


async def upsert(db: Db, data: dict[str, Any], version: int, session: Session = None) -> bool:
    """Write the org if `version` is newer than the copy. Returns True when written."""
    doc = {
        "_id": data["org_id"], "name": data["name"], "name_key": name_key(data["name"]),
        "short_name": data.get("short_name"), "external_id": data.get("external_id"),
        "country": data["country"], "status": data["status"], "aggregate_version": version,
    }
    return await upsert_if_newer(col(db), doc, session=session)


async def get(db: Db, org_id: str, session: Session = None) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one({"_id": org_id}, session=session)
    return doc


async def active_by_key(db: Db) -> dict[str, dict[str, Any]]:
    return {d["name_key"]: d async for d in col(db).find({"status": "active"})}


async def active_by_external_id(db: Db) -> dict[str, dict[str, Any]]:
    """Active organizations by their ID in the system the data came from (decision W5-8)."""
    query = {"status": "active", "external_id": {"$type": "string"}}
    return {d["external_id"]: d async for d in col(db).find(query)}


async def count(db: Db) -> int:
    return int(await col(db).count_documents({}))
