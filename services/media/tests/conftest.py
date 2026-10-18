"""media test fixtures: the real app with its lifespan on throwaway Mongo, Redis and SeaweedFS,
tokens for the seed users (TP), and stand-ins for the three things media asks other systems:
the owner check (operations), the virus scanner (ClamAV) and the job queue.

Presigned URLs are used the way a browser uses them: plain HTTP PUTs to the store."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import boto3
import httpx
import pytest
import pytest_asyncio
from botocore.config import Config
from mms_common.auth import User
from mms_common.errors import Forbidden, NotFound
from mms_common.events import Envelope, validate
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS, TestIssuer
from mms_common.time import ManualClock
from pymongo import AsyncMongoClient

from app.config import Settings
from app.domain.media import ScanStatus
from app.main import create_app
from app.repo.owners import Attachable
from app.repo.scanner import ScannerUnavailable, ScanResult
from app.repo.storage import Storage, make_client

pytest_plugins = ["mms_common.testing.containers"]

BASE = "https://mms.test"
MiB = 1024 * 1024
STATION = "01900000-0000-7000-8000-0000000000a1"  # a station of organization A
MODEL = "01900000-0000-7000-8000-0000000000b1"  # a sensor model (no organization)
PDF = b"%PDF-1.7\n" + b"x" * 200


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeOwners:
    """What operations answers on `/internal/attachable`."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def attachable(
        self, service: str, owner_ref: str, user: User, request_id: str | None = None
    ) -> Attachable:
        self.calls.append(owner_ref)
        if owner_ref.startswith("document:model:"):
            org = None
        elif owner_ref.endswith(STATION):
            org = ORG_A
        else:
            raise NotFound()
        if user.is_client and user.org_id != org:
            raise NotFound()
        if not user.can_write and not user.is_client:
            raise Forbidden()
        return Attachable(org_id=org)


class FakeJobs:
    def __init__(self) -> None:
        self.queued: list[str] = []

    async def enqueue(self, media_id: str) -> None:
        self.queued.append(media_id)


class FakeSession:
    def __init__(self, scanner: FakeScanner) -> None:
        self._scanner = scanner
        self.data = b""

    async def feed(self, chunk: bytes) -> None:
        if self._scanner.down:
            raise ScannerUnavailable("down")
        self.data += chunk

    async def finish(self) -> ScanResult:
        if self._scanner.down:
            raise ScannerUnavailable("down")
        if self._scanner.infected:
            return ScanResult(None, "Eicar-Test-Signature")
        return ScanResult(self._scanner.status)


class FakeScanner:
    def __init__(self) -> None:
        self.down = False
        self.infected = False
        self.status = ScanStatus.CLEAN

    async def open(self) -> FakeSession:
        if self.down:
            raise ScannerUnavailable("down")
        return FakeSession(self)


@dataclass
class Media:
    app: Any
    http: httpx.AsyncClient
    store: httpx.AsyncClient  # talks to the files host, as a browser does
    db: Any
    clock: ManualClock
    issuer: TestIssuer
    jobs: FakeJobs
    owners: FakeOwners
    scanner: FakeScanner
    storage: Storage
    s3: Any
    settings: Settings
    endpoint: str
    _seen: set[str] = field(default_factory=set)

    @property
    def svc(self) -> Any:
        return self.app.state.services

    def bearer(self, who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.issuer.token(who)}"}

    def service(self, name: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.issuer.service_token(name)}"}

    async def create(
        self, data: bytes = PDF, *, who: str = "tech1", owner_ref: str | None = None,
        kind: str = "pdf", filename: str = "manual.pdf", media_id: str | None = None,
        sha: str | None = None, size: int | None = None,
    ) -> httpx.Response:
        return await self.http.post("/api/v1/uploads", headers=self.bearer(who), json={
            "media_id": media_id or new_id(),
            "owner_ref": owner_ref or f"document:station:{STATION}",
            "kind": kind, "filename": filename,
            "size_bytes": size if size is not None else len(data),
            "sha256": sha or sha256(data),
        })

    async def put_part(self, url: str, data: bytes) -> httpx.Response:
        response = await self.store.put(url, content=data)
        assert response.status_code == 200, response.text
        return response

    async def put_all(self, body: dict[str, Any], data: bytes) -> None:
        """Send every part the response asks for, cut the way the server says."""
        size = body["part_size"]
        for item in body["urls"]:
            n = item["part_number"]
            await self.put_part(item["url"], data[(n - 1) * size : n * size])

    async def complete(self, media_id: str, who: str = "tech1") -> httpx.Response:
        return await self.http.post(f"/api/v1/uploads/{media_id}/complete",
                                    headers=self.bearer(who))

    async def upload(self, data: bytes = PDF, **kw: Any) -> dict[str, Any]:
        """Create, send and complete a file; returns the `complete` answer."""
        created = await self.create(data, **kw)
        assert created.status_code == 201, created.text
        body = created.json()
        await self.put_all(body, data)
        done = await self.complete(body["media_id"], kw.get("who", "tech1"))
        assert done.status_code == 200, done.text
        out: dict[str, Any] = done.json()
        return out

    async def outbox(self, type_: str | None = None) -> list[Envelope]:
        query = {"type": type_} if type_ else {}
        cursor = self.db["outbox"].find(query).sort([("created_at", 1), ("_id", 1)])
        envelopes = []
        async for row in cursor:
            env = Envelope.model_validate(
                {k: v for k, v in row.items() if k not in ("_id", "created_at", "published_at")}
            )
            validate(env)
            envelopes.append(env)
        return envelopes

    async def record(self, media_id: str) -> dict[str, Any]:
        doc = await self.db["media"].find_one({"_id": media_id})
        assert doc is not None
        out: dict[str, Any] = doc
        return out

    def object_exists(self, media_id_doc: dict[str, Any]) -> bool:
        try:
            self.s3.head_object(
                Bucket=self.settings.bucket_documents, Key=media_id_doc["original_key"]
            )
        except Exception:  # noqa: BLE001
            return False
        return True


@pytest.fixture(scope="session")
def s3_endpoint(seaweedfs):
    client = boto3.client(
        "s3", endpoint_url=seaweedfs.url, aws_access_key_id=seaweedfs.access_key,
        aws_secret_access_key=seaweedfs.secret_key, region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required"),
    )
    for bucket in ("mms-originals", "mms-media", "mms-documents"):
        client.create_bucket(Bucket=bucket)
    return seaweedfs


@pytest_asyncio.fixture
async def media(mongo_uri, redis_url, s3_endpoint):
    clock = ManualClock(datetime(2026, 10, 19, 9, 0, tzinfo=UTC))
    issuer = TestIssuer(clock)
    db_name = f"media_{uuid.uuid4().hex[:8]}"
    settings = Settings(
        mongo_uri=mongo_uri, mongo_db=db_name, redis_url=redis_url, run_background=False,
        s3_url=s3_endpoint.url, files_url=s3_endpoint.url, s3_access_key=s3_endpoint.access_key,
        s3_secret_key=s3_endpoint.secret_key, part_size=5 * MiB, scan_mode="off",
    )
    secret = s3_endpoint.secret_key
    storage = Storage(
        make_client(s3_endpoint.url, s3_endpoint.access_key, secret),
        make_client(s3_endpoint.url, s3_endpoint.access_key, secret),
    )
    jobs, owners, scanner = FakeJobs(), FakeOwners(), FakeScanner()
    mongo: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    app = create_app(settings, ready_checks={}, clock=clock, keys=issuer.keys, storage=storage,
                     scanner=scanner, owners=owners, jobs=jobs)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        from mms_common.auth.revocation import revoke_user

        await revoke_user(app.state.redis, SEED_USERS["disabled"].id, clock.now())
        transport = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transport, base_url=BASE) as http,
            httpx.AsyncClient(timeout=60) as store,
        ):
            yield Media(
                app, http, store, mongo[db_name], clock, issuer, jobs, owners, scanner, storage,
                storage._s3, settings, s3_endpoint.url,
            )
    await mongo.drop_database(db_name)
    await mongo.close()


__all__ = ["ORG_A", "ORG_B", "STATION", "Media"]
