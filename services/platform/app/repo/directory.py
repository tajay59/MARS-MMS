"""`user_directory`: the people the notification module may tell, copied from auth's `user.*`
events and snapshot (TRD §5.5). Guarded by `aggregate_version`, so events and the backfill can
arrive in any order (§8.6). It holds names, roles and status, never a password or token."""

from __future__ import annotations

from typing import Any

from mms_common.snapshot import upsert_if_newer
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.notifications import Audience

Db = AsyncDatabase[dict[str, Any]]
Session = AsyncClientSession | None
STAFF_ROLES = ["technician", "admin", "viewer"]


def col(db: Db) -> Any:
    return db["user_directory"]


async def upsert(db: Db, data: dict[str, Any], version: int, session: Session = None) -> bool:
    doc = {
        "_id": data["user_id"], "email": data["email"], "name": data["name"],
        "roles": list(data["roles"]), "org_id": data.get("org_id"), "status": data["status"],
        "aggregate_version": version,
    }
    return await upsert_if_newer(col(db), doc, session=session)


async def remove(db: Db, user_id: str, session: Session = None) -> None:
    await col(db).delete_one({"_id": user_id}, session=session)


async def get(db: Db, user_id: str, session: Session = None) -> dict[str, Any] | None:
    found: dict[str, Any] | None = await col(db).find_one({"_id": user_id}, session=session)
    return found


async def audience(db: Db, org_id: str | None, session: Session = None) -> Audience:
    """Active admins, active staff of every kind, and the organization's active clients."""
    staff = [
        d async for d in col(db).find(
            {"status": "active", "roles": {"$in": STAFF_ROLES}}, {"roles": 1}, session=session
        )
    ]
    clients: list[str] = []
    if org_id:
        clients = [
            d["_id"] async for d in col(db).find(
                {"status": "active", "roles": "client", "org_id": org_id}, {"_id": 1},
                session=session,
            )
        ]
    return Audience(
        admins=[d["_id"] for d in staff if "admin" in d["roles"]],
        staff=[d["_id"] for d in staff],
        org_clients=clients,
    )
