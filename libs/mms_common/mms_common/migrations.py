"""Forward-only migrations run on startup under a lock in `_migrations` (TRD §5, §19).

A service keeps them in `app/migrations/NNNN_name.py`, each with `async def up(db)`. They
run in name order, once each. When two instances start together, one takes the lock and the
other waits for it, then finds nothing left to do (TP "Event backbone").
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
import re
from collections.abc import Awaitable, Callable
from datetime import timedelta
from types import ModuleType
from typing import Any, cast

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from mms_common.ids import new_id
from mms_common.logging import get_logger
from mms_common.time import Clock

COLLECTION = "_migrations"
LOCK_ID = "lock"
LOCK_TTL = timedelta(minutes=5)
_NAME = re.compile(r"^\d{4}_[a-z0-9_]+$")

log = get_logger(__name__)

Up = Callable[[AsyncDatabase[dict[str, Any]]], Awaitable[None]]


def discover(package: ModuleType) -> list[tuple[str, Up]]:
    found = []
    for info in pkgutil.iter_modules(package.__path__):
        if _NAME.match(info.name):
            module = importlib.import_module(f"{package.__name__}.{info.name}")
            found.append((info.name, cast(Up, module.up)))
    return sorted(found, key=lambda item: item[0])


async def run(
    db: AsyncDatabase[dict[str, Any]],
    package: ModuleType,
    clock: Clock,
    *,
    wait_s: float = 120.0,
    poll_s: float = 0.5,
) -> list[str]:
    """Apply pending migrations. Returns the names this call applied."""
    col = db[COLLECTION]
    owner = new_id()
    waited = 0.0
    while not await _acquire(db, owner, clock):
        if waited >= wait_s:
            raise TimeoutError("another instance held the migration lock for too long")
        await asyncio.sleep(poll_s)
        waited += poll_s
    applied: list[str] = []
    try:
        done = {doc["_id"] async for doc in col.find({"_id": {"$ne": LOCK_ID}}, {"_id": 1})}
        for name, up in discover(package):
            if name in done:
                continue
            log.info("migration_start", migration=name)
            await up(db)
            await col.insert_one({"_id": name, "applied_at": clock.now()})
            applied.append(name)
    finally:
        await col.delete_one({"_id": LOCK_ID, "owner": owner})
    return applied


async def _acquire(db: AsyncDatabase[dict[str, Any]], owner: str, clock: Clock) -> bool:
    col = db[COLLECTION]
    now = clock.now()
    try:
        await col.insert_one({"_id": LOCK_ID, "owner": owner, "expires_at": now + LOCK_TTL})
        return True
    except DuplicateKeyError:
        # A crashed holder leaves the lock behind; take it over once it has expired.
        taken = await col.find_one_and_update(
            {"_id": LOCK_ID, "expires_at": {"$lt": now}},
            {"$set": {"owner": owner, "expires_at": now + LOCK_TTL}},
        )
        return taken is not None
