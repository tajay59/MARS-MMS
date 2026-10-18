"""The things media's routes, jobs and worker share, built once per process.

Kept outside the layers (api, jobs, events, repo, domain) because all of them take a
`Services` and none of them builds one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from mms_common.auth.service_client import ServiceTokens
from mms_common.jobs import JobQueue
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import Settings
from app.domain.media import Kind
from app.repo.owners import OwnerClient
from app.repo.scanner import ClamdScanner, NoScanner, Scanner
from app.repo.storage import Storage, make_client

QUEUE = "media"


class Jobs(Protocol):
    async def enqueue(self, media_id: str) -> None: ...


@dataclass
class Services:
    settings: Settings
    clock: Clock
    client: AsyncMongoClient[dict[str, Any]]
    db: AsyncDatabase[dict[str, Any]]
    storage: Storage
    scanner: Scanner
    owners: OwnerClient
    jobs: Jobs

    def bucket(self, kind: str) -> str:
        """Documents, PDFs and configuration files live in `mms-documents`; images and video
        arrive in `mms-originals` and are processed into `mms-media` (TRD §10.1)."""
        if kind in (Kind.IMAGE.value, Kind.VIDEO.value):
            return self.settings.bucket_originals
        return self.settings.bucket_documents


def make_storage(settings: Settings) -> Storage:
    secret = settings.s3_secret_key.get_secret_value()
    return Storage(
        make_client(settings.s3_url, settings.s3_access_key, secret),
        make_client(settings.files_url, settings.s3_access_key, secret),
    )


def make_scanner(settings: Settings) -> Scanner:
    if settings.scan_mode == "off":
        return NoScanner()
    return ClamdScanner(settings.clamd_host, settings.clamd_port)


def make_owners(settings: Settings, clock: Clock, http: httpx.AsyncClient) -> OwnerClient:
    tokens = ServiceTokens(
        settings.auth_url, "media", settings.service_secret.get_secret_value(), clock, http
    )
    return OwnerClient({"operations": settings.ops_url}, tokens, http)


class QueueJobs:
    """Hands files to the media-worker through a Redis queue (`mms_common.jobs`). A job's ID is
    the file's, so queuing the same file twice queues it once, and a finished job leaves
    nothing behind, so a file that goes back to `uploaded` can be queued again."""

    def __init__(self, queue: JobQueue) -> None:
        self._queue = queue

    async def enqueue(self, media_id: str) -> None:
        await self._queue.enqueue(media_id)
