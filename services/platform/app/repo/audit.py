"""`audit_events` and `audit_state` in the audit database (TRD §5.6, §12).

The audit Mongo user may only find and insert `audit_events` (rule 10). Appends serialize on
the `audit_state` chain head: every append writes it first in its transaction, so two
writers can never take the same `seq`; the loser's transaction is retried on the new head.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

from mms_common.ids import UUID7_PATTERN, new_id
from pymongo import AsyncMongoClient, ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.audit import GENESIS, chain, first_break
from app.domain.audit_view import NOISY_PREFIXES, STATION_PREFIXES, HistoryType

Db = AsyncDatabase[dict[str, Any]]
HEAD = "chain"


async def append(db: Db, record: dict[str, Any], session: AsyncClientSession) -> dict[str, Any]:
    head = await db["audit_state"].find_one_and_update(
        {"_id": HEAD},
        {"$set": {"writer": new_id()}},  # takes the write lock on the head first
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if head is None:
        raise RuntimeError("audit_state has no chain head: run the audit migrations")
    last_seq = int(head.get("last_seq", 0))
    last_hash = head.get("last_hash") or (GENESIS if last_seq == 0 else None)
    if last_hash is None:
        raise RuntimeError(f"audit chain head at seq {last_seq} has no hash")
    linked = chain(record, last_seq + 1, str(last_hash))
    await db["audit_events"].insert_one(linked, session=session)
    await db["audit_state"].update_one(
        {"_id": HEAD},
        {"$set": {"last_seq": linked["seq"], "last_hash": linked["hash"]}},
        session=session,
    )
    return linked


async def verify(db: Db, from_seq: int = 1, to_seq: int | None = None) -> int | None:
    """Recompute the chain over a range (AUD-5). Returns the first broken `seq`, or None."""
    prev_hash = GENESIS
    if from_seq > 1:
        before = await db["audit_events"].find_one({"seq": from_seq - 1})
        if before is None:
            return from_seq - 1
        prev_hash = before["hash"]
    query: dict[str, Any] = {"seq": {"$gte": from_seq}}
    if to_seq is not None:
        query["seq"]["$lte"] = to_seq
    records = [r async for r in db["audit_events"].find(query).sort("seq", 1)]
    broken = first_break(records, from_seq, prev_hash)
    if broken is not None or to_seq is not None:
        return broken
    # The whole tail: the head must point at the last record (catches a deleted tail).
    head = await db["audit_state"].find_one({"_id": HEAD})
    last_seq, last_hash = (records[-1]["seq"], records[-1]["hash"]) if records else (
        from_seq - 1, prev_hash)
    if head is not None and (head["last_seq"], head["last_hash"]) != (last_seq, last_hash):
        return last_seq + 1
    return None


_UUID = re.compile(UUID7_PATTERN)


def match(
    *, actor: str | None = None, action: str | None = None, resource_type: str | None = None,
    resource_id: str | None = None, org_id: str | None = None, since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """A search as a filter (AUD-4). Values only: a person's name is escaped before it is
    matched, and nothing here comes from the request as an operator (rule 12)."""
    flt: dict[str, Any] = {}
    if actor:
        if _UUID.fullmatch(actor):
            flt["actor.user_id"] = actor
        else:
            flt["actor.name"] = {"$regex": re.escape(actor.strip()), "$options": "i"}
    if action:
        flt["action"] = action
    if resource_type:
        flt["resource.type"] = resource_type
    if resource_id:
        flt["resource.id"] = resource_id
    if org_id:
        flt["org_id"] = org_id
    if since or until:
        window: dict[str, datetime] = {}
        if since:
            window["$gte"] = since
        if until:
            window["$lt"] = until
        flt["at"] = window
    return flt


def history_filter(kind: HistoryType, thing_id: str) -> dict[str, Any]:
    """What a page's History tab lists (W19-2): the thing itself, and the events that name it
    in their data (a visit event carries its request), without board and file noise."""
    own = {"resource.type": kind, "resource.id": thing_id}
    if kind == "station":
        prefixes = "|".join(re.escape(p) for p in STATION_PREFIXES)
        return {"$and": [
            {"$or": [own, {"metadata.station_id": thing_id}]},
            {"action": {"$regex": f"^({prefixes})"}},
        ]}
    noisy = "|".join(re.escape(p) for p in NOISY_PREFIXES)
    return {"$and": [
        {"$or": [own, {f"metadata.{kind}_id": thing_id}]},
        {"action": {"$not": re.compile(f"^({noisy})")}},
    ]}


async def search(
    db: Db, flt: dict[str, Any], *, before_seq: int | None, limit: int
) -> list[dict[str, Any]]:
    """Newest first. `before_seq` is the last `seq` of the page before."""
    query = flt if before_seq is None else {"$and": [flt, {"seq": {"$lt": before_seq}}]}
    return [r async for r in db["audit_events"].find(query).sort("seq", -1).limit(limit)]


async def count(db: Db, flt: dict[str, Any], cap: int) -> int:
    """How many match, counting no further than one past `cap`."""
    return int(await db["audit_events"].count_documents(flt, limit=cap + 1))


async def stream(db: Db, flt: dict[str, Any], batch: int = 500) -> AsyncIterator[dict[str, Any]]:
    """Every match in chain order, a batch at a time."""
    after = 0
    while True:
        query = {"$and": [flt, {"seq": {"$gt": after}}]}
        page = [r async for r in db["audit_events"].find(query).sort("seq", 1).limit(batch)]
        for record in page:
            yield record
        if len(page) < batch:
            return
        after = page[-1]["seq"]


async def head(db: Db) -> tuple[int, str]:
    """The chain's last position as the head records it."""
    doc = await db["audit_state"].find_one({"_id": HEAD})
    if doc is None:
        return 0, GENESIS
    return int(doc.get("last_seq", 0)), str(doc.get("last_hash") or GENESIS)


async def verify_paged(
    db: Db, on_page: Callable[[int], Awaitable[None]], page: int = 5000
) -> int | None:
    """AUD-5 over the whole chain without holding it in memory, while records keep arriving.

    The head is read first and only records up to it are checked, so a record appended during
    the check is not a break. Returns the first broken `seq`, or None."""
    target_seq, target_hash = await head(db)
    prev_hash, expected, checked = GENESIS, 1, 0
    while expected <= target_seq:
        query = {"seq": {"$gte": expected, "$lte": target_seq}}
        batch = [r async for r in db["audit_events"].find(query).sort("seq", 1).limit(page)]
        if not batch:
            return expected  # a record is missing
        broken = first_break(batch, expected, prev_hash)
        if broken is not None:
            return broken
        expected, prev_hash, checked = batch[-1]["seq"] + 1, batch[-1]["hash"], checked + len(batch)
        await on_page(checked)
    if expected - 1 != target_seq or (target_seq > 0 and prev_hash != target_hash):
        return expected  # the head points at a record the chain does not have
    return None


async def record_own(
    client: AsyncMongoClient[dict[str, Any]], db: Db, record: dict[str, Any]
) -> dict[str, Any]:
    """Append a record the audit module writes about itself, in its own transaction."""
    async with client.start_session() as session:

        async def body(s: AsyncClientSession) -> dict[str, Any]:
            return await append(db, record, s)

        return await session.with_transaction(body)
