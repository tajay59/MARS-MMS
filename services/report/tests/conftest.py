"""report test fixtures: the real app with its lifespan on throwaway Mongo, Redis and SeaweedFS,
tokens for the seed users (TP), and stand-ins for the three things report asks of others:
operations (the stations to print), the PDF renderer and the job queue.

Presigned download links are used the way a browser uses them: plain HTTP GETs to the store."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import boto3
import httpx
import pytest
import pytest_asyncio
from botocore.config import Config
from mms_common.testing.seed import SEED_USERS, TestIssuer
from mms_common.time import ManualClock
from pymongo import AsyncMongoClient

from app.config import Settings
from app.domain.labels import Label
from app.main import create_app
from app.repo.operations import LockRefused, OperationsUnavailable, StationLabel
from app.repo.render import Rendered
from app.repo.storage import Storage, make_client

pytest_plugins = ["mms_common.testing.containers"]

BASE = "https://mms.test"
PDF = b"%PDF-1.7\n% fake label sheet\n"
STATION_1 = "01900000-0000-7000-8000-0000000000a1"
STATION_2 = "01900000-0000-7000-8000-0000000000a2"
UNKNOWN = "01900000-0000-7000-8000-0000000000ff"


class FakeStations:
    """What operations answers on `/internal/labels`."""

    def __init__(self) -> None:
        self.known = {
            STATION_1: StationLabel(STATION_1, "JM-KIN-001", "Kingston", "Organization A", "tok-1"),
            STATION_2: StationLabel(STATION_2, "JM-MOB-002", "Mobay", "Organization B", "tok-2"),
        }
        self.down = False
        self.calls: list[list[str]] = []

    async def labels(
        self, station_ids: list[str], request_id: str | None = None
    ) -> list[StationLabel]:
        self.calls.append(station_ids)
        if self.down:
            raise OperationsUnavailable()
        return [self.known[i] for i in station_ids if i in self.known]


class FakeFacts:
    """What operations answers on `/internal/visits/{id}/report-facts`."""

    def __init__(self) -> None:
        self.by_visit: dict[str, dict[str, Any]] = {}
        self.by_client_report: dict[str, dict[str, Any]] = {}
        self.down = False
        self.calls: list[str] = []

    async def visit_facts(self, visit_id: str) -> dict[str, Any] | None:
        self.calls.append(visit_id)
        if self.down:
            raise OperationsUnavailable()
        return self.by_visit.get(visit_id)

    async def client_report_facts(self, client_report_id: str) -> dict[str, Any] | None:
        self.calls.append(client_report_id)
        if self.down:
            raise OperationsUnavailable()
        return self.by_client_report.get(client_report_id)


class FakeLocks:
    """Operations' lock on a visit, as `lock.py` there keeps it: one report version at a time, the
    same pair again changes nothing, only the holder unlocks."""

    def __init__(self) -> None:
        self.held: dict[str, tuple[str, int]] = {}
        self.calls: list[tuple[str, str, str, int]] = []
        self.refuse: str | None = None  # the code operations answers a lock with
        self.down = False

    async def lock(self, visit_id: str, report_id: str, version: int) -> None:
        self.calls.append(("lock", visit_id, report_id, version))
        if self.down:
            raise OperationsUnavailable()
        if self.refuse:
            raise LockRefused(self.refuse)
        holder = self.held.get(visit_id)
        if holder not in (None, (report_id, version)):
            raise LockRefused("locked_by_another_report")
        self.held[visit_id] = (report_id, version)

    async def unlock(self, visit_id: str, report_id: str, version: int) -> None:
        self.calls.append(("unlock", visit_id, report_id, version))
        if self.down:
            raise OperationsUnavailable()
        if self.held.get(visit_id) == (report_id, version):
            del self.held[visit_id]


class FakeMedia:
    """Where each file stands, and the display copy of the photos that are ready."""

    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.photos: dict[str, bytes] = {}
        self.posters: dict[str, bytes] = {}  # a video's poster frame
        self.down = False

    async def status(self, media_id: str) -> str | None:
        if self.down:
            raise OperationsUnavailable()
        return self.states.get(media_id)

    async def rendition(self, media_id: str, *, thumbnail: bool = False) -> bytes | None:
        if self.down:
            raise OperationsUnavailable()
        return (self.posters if thumbnail else self.photos).get(media_id)


class FakeRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Label], str | None]] = []
        self.visits: list[dict[str, Any]] = []
        self.forms: list[dict[str, Any]] = []
        self.fail = False

    async def visit_report(self, view: dict[str, Any], template_version: str) -> Rendered:
        if self.fail:
            raise RuntimeError("boom")
        self.visits.append(view)
        # A final report differs from every other (its version and hash are in its footer)
        extra = f"% v{view['version']} {view.get('hash')}".encode() if view.get("hash") else b""
        return Rendered(pdf=PDF + extra, pages=1)

    async def client_form(self, view: dict[str, Any], template_version: str) -> Rendered:
        if self.fail:
            raise RuntimeError("boom")
        self.forms.append(view)
        return Rendered(pdf=PDF + f"% {view['number']} {view.get('hash')}".encode(), pages=1)

    async def labels(self, labels: list[Label], phone: str | None) -> Rendered:
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append((labels, phone))
        return Rendered(pdf=PDF, pages=1)


class FakeJobs:
    def __init__(self) -> None:
        self.queued: list[str] = []

    async def enqueue(self, job_id: str) -> None:
        self.queued.append(job_id)


@dataclass
class Report:
    app: Any
    http: httpx.AsyncClient
    store: httpx.AsyncClient  # talks to the files host, as a browser does
    db: Any
    clock: ManualClock
    issuer: TestIssuer
    jobs: FakeJobs
    stations: FakeStations
    renderer: FakeRenderer
    facts: FakeFacts
    media: FakeMedia
    locks: FakeLocks
    s3: Any
    settings: Settings

    @property
    def svc(self) -> Any:
        return self.app.state.services

    def bearer(self, who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.issuer.token(who)}"}

    async def start(
        self, ids: list[str] | None = None, who: str = "admin", **body: Any
    ) -> httpx.Response:
        return await self.http.post(
            "/api/v1/reports/labels", headers=self.bearer(who),
            json={"station_ids": ids or [STATION_1, STATION_2], **body},
        )

    async def job(self, job_id: str, who: str = "admin") -> httpx.Response:
        return await self.http.get(f"/api/v1/reports/jobs/{job_id}", headers=self.bearer(who))

    async def record(self, job_id: str) -> dict[str, Any]:
        doc = await self.db["report_jobs"].find_one({"_id": job_id})
        assert doc is not None
        out: dict[str, Any] = doc
        return out


@pytest.fixture(scope="session")
def s3_endpoint(seaweedfs):
    client = boto3.client(
        "s3", endpoint_url=seaweedfs.url, aws_access_key_id=seaweedfs.access_key,
        aws_secret_access_key=seaweedfs.secret_key, region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required"),
    )
    client.create_bucket(Bucket="mms-reports")
    return seaweedfs


@pytest_asyncio.fixture
async def report(mongo_uri, redis_url, s3_endpoint):
    clock = ManualClock(datetime(2026, 10, 19, 9, 0, tzinfo=UTC))
    issuer = TestIssuer(clock)
    db_name = f"report_{uuid.uuid4().hex[:8]}"
    settings = Settings(
        mongo_uri=mongo_uri, mongo_db=db_name, redis_url=redis_url, run_background=False,
        s3_url=s3_endpoint.url, files_url=s3_endpoint.url, s3_access_key=s3_endpoint.access_key,
        s3_secret_key=s3_endpoint.secret_key, app_url="https://mms.example",
    )
    secret = s3_endpoint.secret_key
    storage = Storage(
        make_client(s3_endpoint.url, s3_endpoint.access_key, secret),
        make_client(s3_endpoint.url, s3_endpoint.access_key, secret),
    )
    jobs, stations, renderer = FakeJobs(), FakeStations(), FakeRenderer()
    facts, media, locks = FakeFacts(), FakeMedia(), FakeLocks()
    mongo: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    app = create_app(settings, ready_checks={}, clock=clock, keys=issuer.keys, storage=storage,
                     stations=stations, renderer=renderer, jobs=jobs,  # type: ignore[arg-type]
                     facts=facts, media=media, locks=locks)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        from mms_common.auth.revocation import revoke_user

        await revoke_user(app.state.redis, SEED_USERS["disabled"].id, clock.now())
        transport = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transport, base_url=BASE) as http,
            httpx.AsyncClient(timeout=60) as store,
        ):
            yield Report(
                app, http, store, mongo[db_name], clock, issuer, jobs, stations, renderer,
                facts, media, locks, storage._s3, settings,
            )
    await mongo.drop_database(db_name)
    await mongo.close()
