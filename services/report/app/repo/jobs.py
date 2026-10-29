"""The `report_jobs` collection (TRD §5.4): one record per requested PDF, so the screen that
asked can follow it and the worker can safely run it twice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.labels import JobStatus

Db = AsyncDatabase[dict[str, Any]]


def col(db: Db) -> Any:
    return db["report_jobs"]


async def insert(db: Db, doc: dict[str, Any]) -> None:
    await col(db).insert_one(doc)


async def get(db: Db, job_id: str) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one({"_id": job_id})
    return doc


async def claim(db: Db, job_id: str, now: datetime) -> dict[str, Any] | None:
    """Start a job, or start it again after a worker died (`running` is taken too). A job
    that has finished or failed is not touched, so a repeated queue entry does nothing."""
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": job_id, "status": {"$in": [JobStatus.QUEUED.value, JobStatus.RUNNING.value]}},
        {"$set": {"status": JobStatus.RUNNING.value, "started_at": now, "updated_at": now},
         "$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def finish(db: Db, job_id: str, result: dict[str, Any], now: datetime) -> None:
    await col(db).update_one(
        {"_id": job_id},
        {"$set": {"status": JobStatus.DONE.value, "result": result, "error": None,
                  "finished_at": now, "updated_at": now}},
    )


async def requeue(db: Db, job_id: str, now: datetime) -> None:
    await col(db).update_one(
        {"_id": job_id, "status": JobStatus.RUNNING.value},
        {"$set": {"status": JobStatus.QUEUED.value, "updated_at": now}},
    )


async def fail(db: Db, job_id: str, code: str, now: datetime) -> None:
    await col(db).update_one(
        {"_id": job_id},
        {"$set": {"status": JobStatus.FAILED.value, "error": code, "finished_at": now,
                  "updated_at": now}},
    )


async def recent_for(
    db: Db, user_id: str, job_type: str, since: datetime, limit: int = 50
) -> list[dict[str, Any]]:
    """A person's own jobs of one type, newest first (the Reports page's list)."""
    found = col(db).find(
        {"requested_by": user_id, "type": job_type, "created_at": {"$gte": since}}
    ).sort("created_at", -1).limit(limit)
    return [d async for d in found]


async def same_request(
    db: Db, user_id: str, job_type: str, params_key: str, since: datetime
) -> dict[str, Any] | None:
    """The job this person asked for a moment ago with the same parameters, if it did not fail:
    asking twice (a double click, a retry after a lost answer) makes one."""
    doc: dict[str, Any] | None = await col(db).find_one(
        {"requested_by": user_id, "type": job_type, "params_key": params_key,
         "created_at": {"$gte": since}, "status": {"$ne": JobStatus.FAILED.value}},
        sort=[("created_at", -1)],
    )
    return doc


async def older_than(
    db: Db, job_type: str, before: datetime, limit: int = 200
) -> list[dict[str, Any]]:
    found = col(db).find({"type": job_type, "created_at": {"$lt": before}}).limit(limit)
    return [d async for d in found]


async def delete(db: Db, job_id: str) -> None:
    await col(db).delete_one({"_id": job_id})
