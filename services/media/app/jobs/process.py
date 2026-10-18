"""`process_media`: the checks a whole file passes before anyone can download it (PRD MED-3).

One pass over the stored object computes its SHA-256, reads its first bytes for the magic
check and feeds the virus scanner. A file is released (`ready`) only when all of them pass.
Documents, PDFs and configuration files are kept unchanged; images and video get their own
processing in Phase 4.

Transient trouble (the scanner or store unreachable) puts the file back to `uploaded` and
raises, so arq tries again later and `reconcile` is the safety net. A file never becomes
`ready` without a scan result (`clean`, or `skipped` where the scanner is off).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from mms_common.events import Actor
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain import media as rules
from app.domain.media import Kind, ScanStatus, Status
from app.events.publish import Emitter
from app.repo import media as repo
from app.repo.scanner import ScannerUnavailable
from app.repo.storage import StorageError
from app.services import Services

log = logging.getLogger(__name__)

HEAD_BYTES = 8192
SYSTEM = Actor(roles=["service"], name="media-worker")


class Retry(Exception):
    """Try this file again later."""


@dataclass
class Verdict:
    failure: str | None  # reason code, or None when the file passed
    scan_status: ScanStatus | None = None
    delete_object: bool = False  # infected or corrupt files don't stay in the store


async def process_media(svc: Services, media_id: str) -> str:
    """Returns the file's final status for the log: ready, failed, or skipped when the file
    was not waiting. Raises `Retry` for transient trouble."""
    now = svc.clock.now()
    doc = await repo.transition(svc.db, media_id, Status.UPLOADED, Status.PROCESSING, now)
    if doc is None:
        return "skipped"  # not waiting: already handled, deleted, or another worker has it
    try:
        verdict, digest = await _inspect(svc, doc)
    except (ScannerUnavailable, StorageError) as e:
        await repo.transition(svc.db, media_id, Status.PROCESSING, Status.UPLOADED,
                              svc.clock.now())
        log.warning("process_retry", extra={"media_id": media_id, "error": str(e)})
        raise Retry(str(e)) from e
    except BaseException:
        # Cancelled or crashed: don't leave the file stuck in `processing`.
        await repo.transition(svc.db, media_id, Status.PROCESSING, Status.UPLOADED,
                              svc.clock.now())
        raise

    emitter = Emitter(svc.db, svc.clock, SYSTEM)
    done_at = svc.clock.now()

    async def body(session: AsyncClientSession) -> str:
        if verdict.failure is not None:
            moved = await repo.transition(
                svc.db, media_id, Status.PROCESSING, Status.FAILED, done_at,
                changes={"error": verdict.failure}, session=session,
            )
            if moved is not None:
                await emitter.failed(moved, verdict.failure, session, doc)
            return Status.FAILED.value
        moved = await repo.transition(
            svc.db, media_id, Status.PROCESSING, Status.READY, done_at,
            changes={"scan_status": verdict.scan_status.value if verdict.scan_status else None,
                     "processed_key": doc["original_key"], "checksum_sha256": digest},
            session=session,
        )
        if moved is not None:
            await emitter.processed(moved, session, doc)
        return Status.READY.value

    outcome = await in_transaction(svc.client, body)
    if verdict.delete_object:
        try:
            await svc.storage.delete(svc.bucket(doc["kind"]), doc["original_key"])
        except StorageError:
            log.exception("quarantine_delete_failed", extra={"media_id": media_id})
    return outcome


async def _inspect(svc: Services, doc: dict[str, Any]) -> tuple[Verdict, str]:
    bucket, key = svc.bucket(doc["kind"]), doc["original_key"]
    sha = hashlib.sha256()
    head = b""
    total = 0
    session = await svc.scanner.open()
    async for chunk in svc.storage.read(bucket, key):
        if len(head) < HEAD_BYTES:
            head += chunk[: HEAD_BYTES - len(head)]
        sha.update(chunk)
        total += len(chunk)
        await session.feed(chunk)
    result = await session.finish()
    digest = sha.hexdigest()

    if result.infected:
        log.warning("infected", extra={"media_id": doc["_id"], "signature": result.signature})
        return Verdict("infected", delete_object=True), digest
    if total != doc["size_bytes"]:
        return Verdict("size_mismatch", delete_object=True), digest
    if digest != doc["checksum_sha256"]:
        return Verdict("checksum_mismatch", delete_object=True), digest
    problem = rules.check_content(Kind(doc["kind"]), doc["filename"], head)
    if problem is not None:
        return Verdict("bad_type", delete_object=True), digest
    return Verdict(None, result.status), digest
