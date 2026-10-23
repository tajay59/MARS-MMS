"""The things report's routes, jobs and worker share, built once per process.

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
from app.repo.media import MediaClient, MediaSource
from app.repo.operations import FactsSource, LabelSource, OperationsClient
from app.repo.render import Renderer, WeasyRenderer
from app.repo.storage import Storage, make_client

QUEUE = "report"


class Jobs(Protocol):
    async def enqueue(self, job_id: str) -> None: ...


@dataclass
class Services:
    settings: Settings
    clock: Clock
    client: AsyncMongoClient[dict[str, Any]]
    db: AsyncDatabase[dict[str, Any]]
    storage: Storage
    stations: LabelSource
    renderer: Renderer
    jobs: Jobs
    facts: FactsSource
    media: MediaSource


def make_storage(settings: Settings) -> Storage:
    secret = settings.s3_secret_key.get_secret_value()
    return Storage(
        make_client(settings.s3_url, settings.s3_access_key, secret),
        make_client(settings.files_url, settings.s3_access_key, secret),
    )


def make_stations(
    settings: Settings, clock: Clock, http: httpx.AsyncClient
) -> OperationsClient:
    tokens = ServiceTokens(
        settings.auth_url, "report", settings.service_secret.get_secret_value(), clock, http
    )
    return OperationsClient(settings.ops_url, tokens, http)


def make_renderer() -> Renderer:
    return WeasyRenderer()


class QueueJobs:
    """Hands jobs to the report-worker through a Redis queue (`mms_common.jobs`). A job's ID
    is the report job's, so queuing it twice queues it once."""

    def __init__(self, queue: JobQueue) -> None:
        self._queue = queue

    async def enqueue(self, job_id: str) -> None:
        await self._queue.enqueue(job_id)


def make_media(settings: Settings, clock: Clock, http: httpx.AsyncClient) -> MediaClient:
    tokens = ServiceTokens(
        settings.auth_url, "report", settings.service_secret.get_secret_value(), clock, http
    )
    return MediaClient(settings.media_url, tokens, http)
