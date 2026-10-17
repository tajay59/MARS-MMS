"""`audit_events` and `audit_state` in the audit database (TRD §5.6, §12).

The audit Mongo user may only find and insert `audit_events` (rule 10). Appends serialize on
the `audit_state` chain head: every append writes it first in its transaction, so two
writers can never take the same `seq`; the loser's transaction is retried on the new head.
"""

from __future__ import annotations

from typing import Any

from mms_common.ids import new_id
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.audit import GENESIS, chain, first_break

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
