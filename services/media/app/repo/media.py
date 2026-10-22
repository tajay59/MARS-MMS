"""The `media` collection (TRD §5.3). Org scoping lives here (rule 3): endpoint code asks for a
record "as this user" and cannot widen the query.

Every state change takes the status it expects (`expect`), so two workers or a retried request
cannot move a record twice. Callers do the update and the outbox insert in one transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User, scoped
from pymongo import ASCENDING, ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.domain.media import Status, Visibility

Db = AsyncDatabase[dict[str, Any]]
Doc = dict[str, Any]
Session = AsyncClientSession | None


def col(db: Db) -> AsyncCollection[Doc]:
    return db["media"]


def visible_to(user: User, query: dict[str, Any] | None = None) -> dict[str, Any]:
    """Staff read every file that exists. A client reads files of their organization that
    were made visible to it, and their own uploads (a request attachment before it is
    attached). Everything else is simply not found (rule 4)."""
    merged = dict(query or {})
    merged["status"] = {"$ne": Status.DELETED.value}
    if not user.is_client:
        return merged
    return scoped(user, {"$and": [merged, {"$or": [
        {"visibility": Visibility.ORG.value}, {"uploaded_by": user.id},
    ]}]})


async def insert(db: Db, doc: Doc) -> bool:
    """False when a record with this ID already exists. Not inside a transaction: a duplicate
    key would abort it (see CLAUDE.md gotchas)."""
    try:
        await col(db).insert_one(doc)
    except DuplicateKeyError:
        return False
    return True


async def get(db: Db, id_: str) -> Doc | None:
    return await col(db).find_one({"_id": id_})


async def get_visible(db: Db, user: User, id_: str) -> Doc | None:
    return await col(db).find_one(visible_to(user, {"_id": id_}))


async def get_uploaded_by(db: Db, user: User, id_: str) -> Doc | None:
    """The record, only for the user who started the upload."""
    return await col(db).find_one(
        {"_id": id_, "uploaded_by": user.id, "status": {"$ne": Status.DELETED.value}}
    )


async def find_resumable(
    db: Db, user: User, owner_ref: str, sha256: str, size: int
) -> Doc | None:
    """An upload of this same file by this user that is still open: a user who picks the file
    again after a reload carries on from its parts instead of starting over."""
    return await col(db).find_one({
        "uploaded_by": user.id, "owner_ref": owner_ref, "checksum_sha256": sha256,
        "size_bytes": size, "status": Status.PENDING.value, "upload_id": {"$ne": None},
    })


async def set_upload_id(db: Db, id_: str, upload_id: str, now: datetime) -> bool:
    """Store the multipart upload ID if none is set yet. The loser of a race gets False and
    aborts the upload it created."""
    result = await col(db).update_one(
        {"_id": id_, "upload_id": None, "status": Status.PENDING.value},
        {"$set": {"upload_id": upload_id, "upload_started_at": now, "updated_at": now},
         "$inc": {"version": 1}},
    )
    return result.modified_count == 1


async def transition(
    db: Db,
    id_: str,
    expect: Status,
    new: Status,
    now: datetime,
    *,
    changes: Doc | None = None,
    unset: list[str] | None = None,
    session: Session = None,
) -> Doc | None:
    """Move a record from `expect` to `new`. None means it was not in `expect`."""
    update: dict[str, Any] = {
        "$set": {**(changes or {}), "status": new.value, "updated_at": now},
        "$inc": {"version": 1},
    }
    if unset:
        update["$unset"] = dict.fromkeys(unset, "")
    found: Doc | None = await col(db).find_one_and_update(
        {"_id": id_, "status": expect.value}, update,
        return_document=ReturnDocument.AFTER, session=session,
    )
    return found


async def purgeable(db: Db, ready_before: datetime, limit: int = 200) -> list[Doc]:
    """Photos and video whose original is still stored although the copy has been ready since
    before `ready_before` (30 days, TRD §10.1)."""
    cursor = col(db).find({
        "status": Status.READY.value, "kind": {"$in": ["image", "video"]},
        "thumbnail_key": {"$type": "string"}, "original_purged_at": None,
        "ready_at": {"$lt": ready_before},
    }).limit(limit)
    return [d async for d in cursor]


async def mark_purged(db: Db, id_: str, now: datetime) -> Doc | None:
    found: Doc | None = await col(db).find_one_and_update(
        {"_id": id_, "original_purged_at": None},
        {"$set": {"original_purged_at": now, "updated_at": now}, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return found


async def set_caption(db: Db, id_: str, caption: str | None, now: datetime) -> Doc | None:
    found: Doc | None = await col(db).find_one_and_update(
        {"_id": id_, "status": {"$ne": Status.DELETED.value}},
        {"$set": {"caption": caption, "updated_at": now}, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return found


async def apply_visibility(
    db: Db, ids: list[str], visibility: Visibility, version: int, now: datetime,
    session: Session = None,
) -> int:
    """Set visibility on files whose stored `visibility_version` is older (ADR-19): the newest
    request wins, however events are delivered. Returns how many files changed."""
    result = await col(db).update_many(
        {"_id": {"$in": ids}, "visibility_version": {"$lt": version}},
        {"$set": {"visibility": visibility.value, "visibility_version": version,
                  "updated_at": now}, "$inc": {"version": 1}},
        session=session,
    )
    return int(result.modified_count)


async def mark_deleted(
    db: Db, id_: str, now: datetime, session: Session = None
) -> tuple[Doc, Doc] | None:
    """Delete a file its owner no longer holds, whatever state it is in. Returns the record
    before and after, or None when it is not there or already deleted. The objects are removed
    afterwards by `purge_deleted`."""
    before = await col(db).find_one({"_id": id_, "status": {"$ne": Status.DELETED.value}},
                                    session=session)
    if before is None:
        return None
    after: Doc | None = await col(db).find_one_and_update(
        {"_id": id_, "status": before["status"]},
        {"$set": {"status": Status.DELETED.value, "deleted_at": now, "updated_at": now},
         "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    return None if after is None else (before, after)


async def deleted_with_objects(db: Db, limit: int = 200) -> list[Doc]:
    """Deleted files whose objects may still be in the store."""
    cursor = col(db).find({"status": Status.DELETED.value, "objects_removed_at": None}
                          ).limit(limit)
    return [d async for d in cursor]


async def mark_objects_removed(db: Db, id_: str, now: datetime) -> bool:
    result = await col(db).update_one(
        {"_id": id_, "objects_removed_at": None}, {"$set": {"objects_removed_at": now}}
    )
    return result.modified_count == 1


async def existing_ids(db: Db, ids: list[str], session: Session = None) -> set[str]:
    found = col(db).find({"_id": {"$in": ids}}, {"_id": 1}, session=session)
    return {d["_id"] async for d in found}


async def list_for_owner(
    db: Db, user: User, owner_ref: str, after: str | None, limit: int
) -> list[Doc]:
    query: dict[str, Any] = {"owner_ref": owner_ref}
    if after:
        query["_id"] = {"$gt": after}
    cursor = col(db).find(visible_to(user, query)).sort("_id", ASCENDING).limit(limit)
    return [d async for d in cursor]


async def stuck(db: Db, status: Status, before: datetime, limit: int = 200) -> list[Doc]:
    """Records that sat in `status` since before `before`: the cron jobs' work list."""
    cursor = col(db).find({"status": status.value, "updated_at": {"$lt": before}}).limit(limit)
    return [d async for d in cursor]
