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
