"""`email_queue` in the notification database: account emails waiting to be sent (NOT-3).

The consumer inserts a row in the same transaction as `processed_events`, keyed by the event
ID, so a redelivered event never queues a second email. Senders claim one due row at a time
with an atomic update; a claim lapses after `LEASE`, so a sender that died mid-send hands the
row to the next one. Finished rows keep `done_at` and expire after `KEEP_DONE`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.account_emails import EmailJob, Kind

Db = AsyncDatabase[dict[str, Any]]
QUEUE = "email_queue"
LEASE = timedelta(minutes=2)
KEEP_DONE = timedelta(days=90)

PENDING, SENDING, SENT, SKIPPED, FAILED = "pending", "sending", "sent", "skipped", "failed"


async def ensure_indexes(db: Db) -> None:
    queue = db[QUEUE]
    await queue.create_index([("status", ASCENDING), ("next_attempt_at", ASCENDING)])
    await queue.create_index("locked_until", sparse=True)
    await queue.create_index("done_at", expireAfterSeconds=int(KEEP_DONE.total_seconds()))


async def enqueue(
    db: Db, event_id: str, job: EmailJob, now: datetime, session: AsyncClientSession
) -> None:
    await db[QUEUE].insert_one(
        {
            "_id": event_id,
            **{k: (str(v) if isinstance(v, Kind) else v) for k, v in asdict(job).items()},
            "status": PENDING,
            "attempts": 0,
            "next_attempt_at": now,
            "created_at": now,
        },
        session=session,
    )


def to_job(row: dict[str, Any]) -> EmailJob:
    return EmailJob(
        kind=Kind(row["kind"]),
        user_id=row["user_id"],
        to=row.get("to"),
        name=row.get("name"),
        link_id=row.get("link_id"),
        reason=row.get("reason"),
    )


async def claim(db: Db, now: datetime) -> dict[str, Any] | None:
    """Take the oldest due row, or one whose sender's claim lapsed."""
    return await db[QUEUE].find_one_and_update(
        {
            "$or": [
                {"status": PENDING, "next_attempt_at": {"$lte": now}},
                {"status": SENDING, "locked_until": {"$lt": now}},
            ]
        },
        {"$set": {"status": SENDING, "locked_until": now + LEASE}, "$inc": {"attempts": 1}},
        sort=[("next_attempt_at", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )


async def mark_sent(db: Db, row_id: str, now: datetime) -> None:
    await _finish(db, row_id, SENT, now)


async def mark_skipped(db: Db, row_id: str, now: datetime, reason: str) -> None:
    await _finish(db, row_id, SKIPPED, now, last_error=reason)


async def mark_failed(db: Db, row_id: str, now: datetime, error: str) -> None:
    await _finish(db, row_id, FAILED, now, last_error=error)


async def retry_later(db: Db, row_id: str, at: datetime, error: str) -> None:
    await db[QUEUE].update_one(
        {"_id": row_id, "status": SENDING},
        {
            "$set": {"status": PENDING, "next_attempt_at": at, "last_error": error[:500]},
            "$unset": {"locked_until": ""},
        },
    )


async def _finish(db: Db, row_id: str, status: str, now: datetime, **extra: Any) -> None:
    fields: dict[str, Any] = {"status": status, "done_at": now, **extra}
    if "last_error" in fields:
        fields["last_error"] = str(fields["last_error"])[:500]
    await db[QUEUE].update_one(
        {"_id": row_id, "status": SENDING},
        {"$set": fields, "$unset": {"locked_until": ""}},
    )


async def counts(db: Db) -> dict[str, int]:
    """Rows per status, for `/metrics` and the stack test."""
    out: dict[str, int] = {}
    async for row in await db[QUEUE].aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        out[str(row["_id"])] = int(row["n"])
    return out
