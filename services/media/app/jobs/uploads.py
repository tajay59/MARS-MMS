"""The upload flow (TRD §3.3, §7.3): create, resume and complete a multipart upload.

The store holds the truth about which parts have arrived (`ListParts`), and the client only
keeps a cursor, so a phone that loses its place, its connection or its response can ask again
and carry on. Every step is safe to repeat: create is idempotent by `media_id`, and complete
returns the stored result when the file is already whole.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from mms_common.auth import User
from mms_common.errors import Conflict, NotFound, ValidationFailed
from mms_common.events import Actor
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain import media as rules
from app.domain.media import Kind, Status, Visibility
from app.events.publish import Emitter
from app.repo import media as repo
from app.repo.storage import StorageError, UploadGone
from app.services import Services

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewUpload:
    media_id: str
    owner_ref: str
    kind: str
    filename: str
    size_bytes: int
    sha256: str


@dataclass
class UploadState:
    """What the client needs to carry on: the file's record, which parts the store holds, and
    fresh URLs for the rest."""

    doc: dict[str, Any]
    parts_done: list[int] = field(default_factory=list)
    urls: dict[int, str] = field(default_factory=dict)
    expires_at: datetime | None = None
    resumed: bool = False


def _reject(error: rules.Rejected) -> ValidationFailed:
    return ValidationFailed(str(error), reason=error.code)


async def create_upload(
    svc: Services, user: User, body: NewUpload, request_id: str | None = None
) -> UploadState:
    """Idempotent by `media_id`. The same file picked again by the same user continues the
    open upload; the answer then carries that upload's `media_id`."""
    if body.kind not in svc.settings.enabled_kinds:
        raise ValidationFailed("This kind of file can't be uploaded yet", reason="kind_not_enabled")
    try:
        kind = Kind(body.kind)
        filename = rules.clean_filename(body.filename)
        ext = rules.check_name(kind, filename)
        rules.check_size(kind, body.size_bytes)
        owner = rules.parse_owner(body.owner_ref)
    except rules.Rejected as e:
        raise _reject(e) from e

    existing = await repo.get(svc.db, body.media_id)
    if existing is not None:
        return await _replay(svc, user, body, existing)
    resumable = await repo.find_resumable(
        svc.db, user, body.owner_ref, body.sha256, body.size_bytes
    )
    if resumable is not None:
        state = await _state(svc, resumable)
        state.resumed = True
        return state

    # Which organization does the file belong to, and may this user attach to the owner?
    attach = await svc.owners.attachable(owner.service, owner.ref, user, request_id)
    now = svc.clock.now()
    doc = {
        "_id": body.media_id, "owner_service": owner.service, "owner_ref": owner.ref,
        "org_id": attach.org_id, "visibility": Visibility.STAFF.value, "visibility_version": 0,
        "kind": kind.value, "filename": filename, "mime": rules.content_type(filename),
        "size_bytes": body.size_bytes, "checksum_sha256": body.sha256,
        "original_key": rules.object_key(attach.org_id, owner, body.media_id, ext),
        "processed_key": None, "thumbnail_key": None, "original_purged_at": None,
        "caption": None, "status": Status.PENDING.value, "error": None, "scan_status": None,
        "upload_id": None, "upload_started_at": None, "uploaded_by": user.id,
        "created_at": now, "updated_at": now, "created_by": user.id, "updated_by": user.id,
        "version": 1,
    }
    if not await repo.insert(svc.db, doc):  # two requests with the same media_id at once
        again = await repo.get(svc.db, body.media_id)
        if again is None:  # pragma: no cover - the other request's record vanished
            raise Conflict("Try again")
        return await _replay(svc, user, body, again)
    return await _state(svc, doc)


async def _replay(
    svc: Services, user: User, body: NewUpload, existing: dict[str, Any]
) -> UploadState:
    if existing["uploaded_by"] != user.id:
        raise NotFound()  # someone else's ID: say nothing about it (rule 4)
    same = (
        existing["owner_ref"] == body.owner_ref and existing["kind"] == body.kind
        and existing["size_bytes"] == body.size_bytes
        and existing["checksum_sha256"] == body.sha256
    )
    if not same:
        raise Conflict("This media_id was used for a different file", reason="media_id_reused")
    return await _state(svc, existing)


async def _state(svc: Services, doc: dict[str, Any]) -> UploadState:
    """Make sure the multipart upload exists, then list what the store holds."""
    if doc["status"] != Status.PENDING.value:
        return UploadState(doc)
    bucket = svc.bucket(doc["kind"])
    if doc.get("upload_id") is None:
        upload_id = await svc.storage.create_multipart(bucket, doc["original_key"], doc["mime"])
        if await repo.set_upload_id(svc.db, doc["_id"], upload_id, svc.clock.now()):
            doc = {**doc, "upload_id": upload_id}
        else:  # a concurrent request got there first: use its upload, drop ours
            await svc.storage.abort(bucket, doc["original_key"], upload_id)
            fresh = await repo.get(svc.db, doc["_id"])
            if fresh is None or fresh.get("upload_id") is None:  # pragma: no cover
                raise Conflict("Try again")
            doc = fresh
    return await part_urls(svc, doc)


async def part_urls(svc: Services, doc: dict[str, Any]) -> UploadState:
    """`parts_done` from the store, and URLs for the parts still missing (1 hour)."""
    if doc["status"] != Status.PENDING.value:
        return UploadState(doc)
    bucket = svc.bucket(doc["kind"])
    try:
        stored = await svc.storage.list_parts(bucket, doc["original_key"], doc["upload_id"])
    except UploadGone:
        # The store dropped the upload (aborted by an operator, or an old record): it cannot
        # be resumed. Say so, and let the client start a new one with a new media_id.
        failed = await fail_upload(svc, doc, "upload_lost", Actor())
        return UploadState(failed or doc)
    ttl = svc.settings.part_url_ttl_s
    count = rules.part_count(doc["size_bytes"], svc.settings.part_size)
    urls = {
        n: svc.storage.part_url(bucket, doc["original_key"], doc["upload_id"], n, ttl)
        for n in range(1, count + 1) if n not in stored
    }
    return UploadState(
        doc, parts_done=sorted(stored), urls=urls,
        expires_at=svc.clock.now() + timedelta(seconds=ttl),
    )


async def fail_upload(
    svc: Services, doc: dict[str, Any], reason: str, actor: Actor,
    expect: Status = Status.PENDING,
) -> dict[str, Any] | None:
    emitter = Emitter(svc.db, svc.clock, actor)
    now = svc.clock.now()

    async def body(session: AsyncClientSession) -> dict[str, Any] | None:
        moved = await repo.transition(
            svc.db, doc["_id"], expect, Status.FAILED, now, changes={"error": reason},
            session=session,
        )
        if moved is not None:
            await emitter.failed(moved, reason, session, doc)
        return moved

    return await in_transaction(svc.client, body)


async def complete_upload(
    svc: Services, user: User, media_id: str, actor: Actor
) -> UploadState:
    """Check the parts, join them, and queue the file for its checks. Safe to repeat."""
    doc = await repo.get_uploaded_by(svc.db, user, media_id)
    if doc is None:
        raise NotFound()
    if doc["status"] != Status.PENDING.value:
        return UploadState(doc)  # already whole (a retry after a lost response), or failed
    if doc.get("upload_id") is None:
        raise Conflict("Nothing has been uploaded yet", reason="incomplete_upload")
    bucket = svc.bucket(doc["kind"])
    key, size = doc["original_key"], doc["size_bytes"]

    try:
        stored = await svc.storage.list_parts(bucket, key, doc["upload_id"])
    except UploadGone:
        # Joined by an earlier call whose answer was lost? Then the object is there.
        if await svc.storage.size(bucket, key) != size:
            await fail_upload(svc, doc, "upload_lost", actor)
            raise Conflict("The upload was lost. Start it again", reason="upload_lost") from None
    else:
        check = rules.check_parts({n: p.size for n, p in stored.items()}, size,
                                  svc.settings.part_size)
        if check.problem:
            await _abort_and_fail(svc, doc, bucket, "size_mismatch", actor)
            raise Conflict("The uploaded file isn't the size announced",
                           reason="size_mismatch")
        if check.missing:
            raise Conflict("Some parts have not arrived", reason="incomplete_upload",
                           missing=check.missing)
        try:
            await svc.storage.complete(bucket, key, doc["upload_id"], list(stored.values()))
        except UploadGone:
            pass  # a concurrent complete won; the size check below confirms the object
        if await svc.storage.size(bucket, key) != size:
            await _abort_and_fail(svc, doc, bucket, "size_mismatch", actor)
            raise Conflict("The uploaded file isn't the size announced", reason="size_mismatch")

    emitter = Emitter(svc.db, svc.clock, actor)
    now = svc.clock.now()

    async def body(session: AsyncClientSession) -> dict[str, Any] | None:
        moved = await repo.transition(svc.db, media_id, Status.PENDING, Status.UPLOADED, now,
                                      session=session)
        if moved is not None:
            await emitter.uploaded(moved, session, doc)
        return moved

    moved = await in_transaction(svc.client, body)
    if moved is None:  # a concurrent complete finished first
        moved = await repo.get(svc.db, media_id) or doc
    else:
        await enqueue_processing(svc, media_id)
    return UploadState(moved)


async def _abort_and_fail(
    svc: Services, doc: dict[str, Any], bucket: str, reason: str, actor: Actor
) -> None:
    try:
        await svc.storage.abort(bucket, doc["original_key"], doc["upload_id"])
    except StorageError:
        log.warning("abort_failed", extra={"media_id": doc["_id"]})
    await fail_upload(svc, doc, reason, actor)


async def enqueue_processing(svc: Services, media_id: str) -> None:
    """Hand the file to the worker. If Redis is down the file stays `uploaded` and the
    `reconcile` job queues it again (TRD §3.3), so a failure here loses nothing."""
    try:
        await svc.jobs.enqueue(media_id)
    except Exception:  # noqa: BLE001
        log.exception("enqueue_failed", extra={"media_id": media_id})
