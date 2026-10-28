"""The `reports` collection (TRD 5.4): visit report drafts and, from W17, their final versions.

Every write to a draft goes through a conditional update, so a consumer, the cron and the worker
can touch one report at once without losing each other's work.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]


def col(db: Db) -> Any:
    return db["reports"]


async def get(
    db: Db, report_id: str, session: AsyncClientSession | None = None
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one({"_id": report_id}, session=session)
    return doc


async def for_subject(
    db: Db, subject_ref: str, version: int = 1, session: AsyncClientSession | None = None
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one(
        {"subject_ref": subject_ref, "version": version}, session=session)
    return doc


async def list_reports(
    db: Db, *, subject_ref: str | None, type_: str | None, limit: int = 200
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if subject_ref:
        query["subject_ref"] = subject_ref
    if type_:
        query["type"] = type_
    cursor = col(db).find(query).sort([("subject_ref", 1), ("version", -1)]).limit(limit)
    return [d async for d in cursor]


async def insert_if_new(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> bool:
    """Reads first: inside a consumer's transaction a duplicate-key error aborts the whole
    transaction even when caught (TRD 8.6, as built 2.6)."""
    if await for_subject(db, doc["subject_ref"], doc["version"], session) is not None:
        return False
    await col(db).insert_one(doc, session=session)
    return True


async def mark_stale(
    db: Db, visit_id: str, now: datetime, session: AsyncClientSession
) -> int:
    """A board changed: the draft's facts must be read again (never a final report's)."""
    result = await col(db).update_many(
        {"visit_id": visit_id, "type": "visit", "status": "draft"},
        {"$set": {"facts_stale": True, "facts_stale_at": now, "updated_at": now}},
        session=session,
    )
    return int(result.modified_count)


async def stale_drafts(db: Db, limit: int = 50) -> list[dict[str, Any]]:
    cursor = col(db).find({"status": "draft", "facts_stale": True}).sort("facts_stale_at", 1)
    return [d async for d in cursor.limit(limit)]


async def set_facts(
    db: Db, report_id: str, *, expected_stale_at: datetime, expected_content_version: int,
    expected_hash: str | None, facts: dict[str, Any], narrative: dict[str, Any] | None,
    selection: list[dict[str, Any]], awaiting: list[str], content_hash: str, now: datetime,
    session: AsyncClientSession | None = None,
) -> bool:
    """Store freshly read facts. If the board changed again while they were being read
    (`facts_stale_at` moved), or a person edited the report meanwhile (`content_version` moved),
    the report stays stale and is read once more. The narrative is written only the first time
    (`narrative` is None afterwards). When what prints changed (`content_hash`), the content
    version moves too, so a signer who read the old page cannot sign the new one (W17-3)."""
    changes: dict[str, Any] = {
        "content.facts": facts, "content.media_selection": selection,
        "awaiting_media": awaiting, "content_hash": content_hash, "updated_at": now,
    }
    if narrative is not None:
        changes["content.narrative"] = narrative
    bump = 1 if expected_hash is not None and expected_hash != content_hash else 0
    result = await col(db).update_one(
        {"_id": report_id, "status": "draft", "facts_stale_at": expected_stale_at,
         "content_version": expected_content_version, "content_hash": expected_hash},
        {"$set": {**changes, "facts_stale": False},
         "$inc": {"facts_version": 1, "content_version": bump}},
        session=session,
    )
    if result.matched_count == 0:
        await col(db).update_one(
            {"_id": report_id, "status": "draft"},
            {"$set": {"awaiting_media": awaiting, "updated_at": now}}, session=session,
        )
    return bool(result.matched_count)


async def set_content(
    db: Db, report_id: str, *, expected_version: int, narrative: dict[str, Any],
    selection: list[dict[str, Any]], content_hash: str, now: datetime,
    session: AsyncClientSession,
) -> bool:
    """A person's edit (W17-2). False when the content moved on since they read it."""
    result = await col(db).update_one(
        {"_id": report_id, "status": "draft", "content_version": expected_version},
        {"$set": {"content.narrative": narrative, "content.media_selection": selection,
                  "content_hash": content_hash, "updated_at": now},
         "$inc": {"content_version": 1}},
        session=session,
    )
    return bool(result.modified_count)


async def hold_version(
    db: Db, report_id: str, version: int, now: datetime, session: AsyncClientSession
) -> bool:
    """Take the draft at a content version inside a transaction (a signature binds to it). A
    concurrent edit writes the same document, so one of the two sees the other's version and
    stops."""
    result = await col(db).update_one(
        {"_id": report_id, "status": "draft", "content_version": version},
        {"$set": {"updated_at": now}}, session=session,
    )
    return bool(result.matched_count)


async def set_awaiting(db: Db, report_id: str, awaiting: list[str], now: datetime) -> None:
    await col(db).update_one(
        {"_id": report_id, "status": "draft"},
        {"$set": {"awaiting_media": awaiting, "updated_at": now}},
    )


async def waiting_for_media(db: Db) -> list[dict[str, Any]]:
    cursor = col(db).find({"status": "draft", "awaiting_media.0": {"$exists": True}})
    return [d async for d in cursor.limit(100)]


async def due_for_first_pdf(db: Db) -> list[dict[str, Any]]:
    """Drafts with their facts read, no PDF yet and nothing rendering."""
    cursor = col(db).find({
        "status": "draft", "draft_pdf": None, "facts_stale": False,
        "render.state": "idle", "content.facts": {"$ne": None},
    })
    return [d async for d in cursor.limit(100)]


# --- rendering --------------------------------------------------------------------------------


async def request_render(db: Db, report_id: str, now: datetime) -> bool:
    """Idle or failed -> queued. False when a render is already queued or running, so asking
    twice queues once."""
    result = await col(db).update_one(
        {"_id": report_id, "status": "draft", "render.state": {"$in": ["idle", "failed"]}},
        {"$set": {"render.state": "queued", "render.queued_at": now, "render.error": None,
                  "render.attempts": 0, "updated_at": now}},
    )
    return bool(result.modified_count)


async def claim_render(db: Db, report_id: str, now: datetime) -> dict[str, Any] | None:
    """Start a render, or start it again after a worker died (`running` is taken too)."""
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": report_id, "status": "draft", "render.state": {"$in": ["queued", "running"]}},
        {"$set": {"render.state": "running", "render.started_at": now, "updated_at": now},
         "$inc": {"render.attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def requeue_render(db: Db, report_id: str, now: datetime) -> None:
    await col(db).update_one(
        {"_id": report_id, "render.state": "running"},
        {"$set": {"render.state": "queued", "updated_at": now}},
    )


async def fail_render(db: Db, report_id: str, code: str, now: datetime) -> None:
    await col(db).update_one(
        {"_id": report_id, "render.state": {"$in": ["queued", "running"]}},
        {"$set": {"render.state": "failed", "render.error": code, "updated_at": now}},
    )


async def finish_render(
    db: Db, report_id: str, pdf: dict[str, Any], *, first: bool, session: AsyncClientSession,
) -> bool:
    """Record the PDF. `first` also stamps `drafted_at` (the notification goes out with it, in
    the same transaction: the caller adds the event)."""
    changes: dict[str, Any] = {
        "draft_pdf": pdf, "render.state": "idle", "render.error": None, "updated_at": pdf["at"],
    }
    if first:
        changes["drafted_at"] = pdf["at"]
    result = await col(db).update_one(
        {"_id": report_id, "status": "draft", "render.state": "running"},
        {"$set": changes}, session=session,
    )
    return bool(result.modified_count)


# --- finalizing and reopening (W17-7, W17-10) ------------------------------------------------


async def request_finalize(
    db: Db, report_id: str, *, content_version: int, content_hash: str, by: str,
    actor: dict[str, Any], now: datetime,
) -> bool:
    """draft -> finalizing, if the content is still the one that was signed. False when it moved
    or another request got there first."""
    result = await col(db).update_one(
        {"_id": report_id, "status": "draft", "content_version": content_version,
         "content_hash": content_hash},
        {"$set": {"status": "finalizing", "finalizing_at": now, "finalize_requested_by": by,
                  "finalize_actor": actor, "finalize_attempts": 0, "finalize_error": None,
                  "updated_at": now}},
    )
    return bool(result.modified_count)


async def claim_finalizing(db: Db, report_id: str, now: datetime) -> dict[str, Any] | None:
    """Start a try of the saga, or start it again after a worker died. Counts the try."""
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": report_id, "status": "finalizing"},
        {"$set": {"updated_at": now}, "$inc": {"finalize_attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def back_to_draft(
    db: Db, report_id: str, *, error: str, stale: bool, unlock: dict[str, Any] | None,
    now: datetime, session: AsyncClientSession,
) -> bool:
    """finalizing -> draft. `stale` makes the facts be read again; `unlock` is the lock still owed
    to operations (done after the transaction, or by the cron if that fails)."""
    changes: dict[str, Any] = {
        "status": "draft", "finalize_error": error, "finalizing_at": None, "updated_at": now,
        "unlock_pending": unlock,
    }
    if stale:
        changes.update(facts_stale=True, facts_stale_at=now)
    result = await col(db).update_one(
        {"_id": report_id, "status": "finalizing"}, {"$set": changes}, session=session)
    return bool(result.modified_count)


async def finish_final(
    db: Db, report_id: str, *, final_pdf: dict[str, Any], by: str, at: datetime,
    content_hash: str, session: AsyncClientSession,
) -> bool:
    """finalizing -> final, once, if the content is still the one that was signed."""
    result = await col(db).update_one(
        {"_id": report_id, "status": "finalizing", "content_hash": content_hash},
        {"$set": {"status": "final", "finalized_at": at, "finalized_by": by,
                  "final_pdf": final_pdf, "pdf_key": final_pdf["key"],
                  "pdf_sha256": final_pdf["sha256"], "finalize_error": None,
                  "finalizing_at": None, "unlock_pending": None, "updated_at": at}},
        session=session,
    )
    return bool(result.modified_count)


async def stuck_finalizing(db: Db, before: datetime) -> list[dict[str, Any]]:
    cursor = col(db).find({"status": "finalizing", "finalizing_at": {"$lte": before}})
    return [d async for d in cursor.limit(50)]


async def unlock_owed(db: Db) -> list[dict[str, Any]]:
    cursor = col(db).find({"unlock_pending": {"$ne": None}})
    return [d async for d in cursor.limit(50)]


async def clear_unlock(db: Db, report_id: str, pending: dict[str, Any]) -> None:
    await col(db).update_one(
        {"_id": report_id, "unlock_pending": pending}, {"$set": {"unlock_pending": None}})


async def supersede(
    db: Db, report_id: str, *, by: str, now: datetime, session: AsyncClientSession
) -> bool:
    result = await col(db).update_one(
        {"_id": report_id, "status": "final"},
        {"$set": {"status": "superseded", "superseded_at": now, "superseded_by": by,
                  "updated_at": now}}, session=session)
    return bool(result.modified_count)


async def by_pdf_hash(db: Db, sha256: str) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one({"pdf_sha256": sha256})
    return doc


# --- a client's online-form report (W18-10) --------------------------------------------------


async def next_sequence(db: Db, key: str, session: AsyncClientSession) -> int:
    """The next number of a series (`CR-…-NN`). It moves inside the caller's transaction, so a
    report that fails to save does not use one up."""
    counter: dict[str, Any] | None = await db["counters"].find_one_and_update(
        {"_id": key}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER,
        session=session,
    )
    if counter is None:  # upsert=True always returns the document
        raise RuntimeError("the counter was not created")
    return int(counter["seq"])


async def for_client_report(
    db: Db, client_report_id: str, session: AsyncClientSession | None = None
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one(
        {"type": "client_form", "client_report_id": client_report_id}, session=session)
    return doc


async def restart_client_form(
    db: Db, report_id: str, *, attempt: int, now: datetime, session: AsyncClientSession
) -> bool:
    """render_failed -> rendering, for the client's next try. False if it moved meanwhile."""
    result = await col(db).update_one(
        {"_id": report_id, "status": "render_failed", "attempt": {"$lt": attempt}},
        {"$set": {"status": "rendering", "attempt": attempt, "render.state": "idle",
                  "render.attempts": 0, "render.error": None, "updated_at": now}},
        session=session,
    )
    return bool(result.modified_count)


async def client_forms_waiting(db: Db, stuck_before: datetime) -> list[dict[str, Any]]:
    """Forms to draw: none queued yet, or queued or running for so long that the worker that had
    it is gone (the job is safe to take twice)."""
    cursor = col(db).find({
        "type": "client_form", "status": "rendering",
        "$or": [{"render.state": "idle"},
                {"render.state": {"$in": ["queued", "running"]},
                 "updated_at": {"$lte": stuck_before}}],
    })
    return [d async for d in cursor.limit(50)]


async def queue_client_form(db: Db, report_id: str, now: datetime, stuck_before: datetime) -> bool:
    """idle (or abandoned) -> queued, once: two ticks queue it once."""
    result = await col(db).update_one(
        {"_id": report_id, "status": "rendering",
         "$or": [{"render.state": "idle"},
                 {"render.state": {"$in": ["queued", "running"]},
                  "updated_at": {"$lte": stuck_before}}]},
        {"$set": {"render.state": "queued", "render.queued_at": now, "updated_at": now}},
    )
    return bool(result.modified_count)


async def claim_client_form(db: Db, report_id: str, now: datetime) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": report_id, "status": "rendering", "render.state": {"$in": ["queued", "running"]}},
        {"$set": {"render.state": "running", "render.started_at": now, "updated_at": now},
         "$inc": {"render.attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def requeue_client_form(db: Db, report_id: str, now: datetime) -> None:
    await col(db).update_one(
        {"_id": report_id, "status": "rendering", "render.state": "running"},
        {"$set": {"render.state": "queued", "updated_at": now}},
    )


async def finish_client_form(
    db: Db, report_id: str, *, attempt: int, facts: dict[str, Any], content_hash: str,
    final_pdf: dict[str, Any], session: AsyncClientSession,
) -> bool:
    """rendering -> final, once, for the attempt the PDF was drawn for."""
    at = final_pdf["at"]
    result = await col(db).update_one(
        {"_id": report_id, "status": "rendering", "attempt": attempt},
        {"$set": {"status": "final", "content.form": facts, "content_hash": content_hash,
                  "final_pdf": final_pdf, "pdf_key": final_pdf["key"],
                  "pdf_sha256": final_pdf["sha256"], "finalized_at": at, "render.state": "idle",
                  "render.error": None, "updated_at": at}},
        session=session,
    )
    return bool(result.modified_count)


async def fail_client_form(
    db: Db, report_id: str, *, attempt: int, code: str, now: datetime, session: AsyncClientSession
) -> bool:
    """rendering -> render_failed, once. The client may submit again."""
    result = await col(db).update_one(
        {"_id": report_id, "status": "rendering", "attempt": attempt},
        {"$set": {"status": "render_failed", "render.state": "failed", "render.error": code,
                  "updated_at": now}},
        session=session,
    )
    return bool(result.modified_count)
