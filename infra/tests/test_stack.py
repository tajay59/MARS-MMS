"""Checks against the running local stack (TP Phase 1: Nginx routing, 404 for /internal/,
CSP, database isolation, audit insert-only role, and J1/J2 end to end into the audit chain).

    cd infra && docker compose -f compose.yml -f compose.dev.yml up -d
    ../.venv/Scripts/python -m pytest tests -q        (Windows; bin/python elsewhere)

Skipped when the stack is not running.
"""

from __future__ import annotations

import itertools
import os
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from pymongo import MongoClient
from pymongo.errors import OperationFailure

INFRA = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (INFRA / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


ENV = _env() if (INFRA / ".env").exists() else {}
MMS = ENV.get("MMS_HOST", "mms.localhost")
FILES = ENV.get("FILES_HOST", "files.mms.localhost")
MONGO_PORT = ENV.get("MONGO_DEV_PORT", "27018")

# Exactly the CSP in TRD §15, with the local host names.
EXPECTED_CSP = (
    f"default-src 'self'; img-src 'self' https://{FILES} https://tile.openstreetmap.org data: "
    f"blob:; media-src 'self' https://{FILES} blob:; connect-src 'self' https://{FILES} "
    f"https://tile.openstreetmap.org wss://{MMS}; script-src 'self'; worker-src 'self'; "
    "style-src 'self' 'unsafe-inline'"
)


@pytest.fixture(scope="session")
def web():
    # Connect to 127.0.0.1 and send the host name, so no hosts-file entry is needed.
    client = httpx.Client(base_url="https://127.0.0.1", verify=False, timeout=10)  # noqa: S501
    try:
        client.get("/", headers={"Host": MMS})
    except httpx.HTTPError:
        pytest.skip("stack not running (nginx on 443)")
    yield client
    client.close()


def get(web, path, host=MMS, **kw):
    return web.get(path, headers={"Host": host, **kw.pop("headers", {})}, **kw)


# --- Nginx: routing ------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/internal/service-token", "/.well-known/jwks.json"])
def test_internal_and_jwks_are_never_routed(web, path):
    assert get(web, path).status_code == 404


def test_unknown_api_path_is_404_problem_json(web):
    r = get(web, "/api/v1/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


def test_integrations_are_reserved_with_501(web):
    r = get(web, "/api/v1/integrations/anything")
    assert r.status_code == 501 and r.json()["code"] == "not_implemented"


@pytest.mark.parametrize("path", ["/api/v1/reports", "/api/v1/dashboard/summary"])  # report: P6
def test_routes_to_a_service_that_is_not_up_yet_answer_503(web, path):
    r = get(web, path)
    assert r.status_code == 503 and r.json()["code"] == "service_unavailable"


def test_http_redirects_to_https():
    r = httpx.get("http://127.0.0.1/x", headers={"Host": MMS}, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"https://{MMS}/x"


# --- Nginx: headers ------------------------------------------------------------------------


def test_csp_matches_the_trd(web):
    assert get(web, "/").headers["content-security-policy"] == EXPECTED_CSP


@pytest.mark.parametrize("path", ["/", "/stations/123", "/assets/", "/api/v1/nope"])
def test_security_headers_on_every_kind_of_response(web, path):
    h = get(web, path).headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert h["strict-transport-security"].startswith("max-age=31536000")
    assert "camera=(self)" in h["permissions-policy"]


def test_request_id_is_kept_or_generated(web):
    assert get(web, "/", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"
    assert get(web, "/", headers={"X-Request-ID": "bad id"}).headers["x-request-id"] != "bad id"


def test_spa_fallback_and_no_cache_on_index(web):
    r = get(web, "/stations/0192f0c4/whatever")
    assert r.status_code == 200 and "<div id=\"app\">" in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert get(web, "/theme-init.js").headers["cache-control"] == "no-cache"


def test_hashed_assets_are_immutable(web):
    index = get(web, "/").text
    start = index.index("/assets/")
    asset = index[start : index.index('"', start)]
    r = get(web, asset)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_files_host_serves_no_app(web):
    r = get(web, "/", host=FILES)
    assert "<div id=\"app\">" not in r.text
    assert r.status_code in (403, 400)  # S3 refuses an anonymous bucket listing


# --- MongoDB: one user per service, isolation, audit role ------------------------------------

SERVICE_USERS = {
    "auth": "AUTH_DB_PASSWORD",
    "operations": "OPS_DB_PASSWORD",
    "media": "MEDIA_DB_PASSWORD",
    "report": "REPORT_DB_PASSWORD",
    "notification": "PLATFORM_NOTIFICATION_DB_PASSWORD",
    "audit": "PLATFORM_AUDIT_DB_PASSWORD",
}


def mongo_as(user: str) -> MongoClient:
    password = ENV[SERVICE_USERS[user]]
    uri = f"mongodb://{user}:{password}@127.0.0.1:{MONGO_PORT}/{user}?directConnection=true"
    return MongoClient(uri, serverSelectionTimeoutMS=3000)


@pytest.fixture(scope="session")
def mongo_up():
    try:
        mongo_as("auth").admin.command("ping")
    except Exception:  # noqa: BLE001
        pytest.skip(f"mongo not reachable on 127.0.0.1:{MONGO_PORT}")


@pytest.mark.parametrize("user", [u for u in SERVICE_USERS if u != "audit"])
def test_each_service_writes_its_own_database(mongo_up, user):
    with mongo_as(user) as c:
        c[user].isolation_probe.insert_one({"ok": 1})
        c[user].isolation_probe.drop()


@pytest.mark.parametrize("user", list(SERVICE_USERS))
def test_no_service_reads_another_database_rule_1(mongo_up, user):
    other = "operations" if user != "operations" else "auth"
    with mongo_as(user) as c, pytest.raises(OperationFailure):
        c[other].list_collection_names()


def test_audit_events_are_insert_only_rule_10(mongo_up):
    # A negative seq and a separate state document keep the live chain untouched: platform's
    # audit consumer may be appending while this runs.
    with mongo_as("audit") as c:
        events = c.audit.audit_events
        events.insert_one({"_id": "probe", "seq": -1})
        assert events.find_one({"_id": "probe"})
        with pytest.raises(OperationFailure):
            events.update_one({"_id": "probe"}, {"$set": {"seq": -2}})
        with pytest.raises(OperationFailure):
            events.delete_one({"_id": "probe"})
        with pytest.raises(OperationFailure):
            events.drop()
        c.audit.audit_state.update_one({"_id": "probe"}, {"$set": {"x": 1}}, upsert=True)
    root = root_mongo()
    root.audit.audit_events.delete_one({"_id": "probe"})  # test cleanup only
    root.audit.audit_state.delete_one({"_id": "probe"})
    root.close()


def root_mongo() -> MongoClient:
    return MongoClient(
        f"mongodb://root:{ENV['MONGO_ROOT_PASSWORD']}@127.0.0.1:{MONGO_PORT}/?directConnection=true",
        tz_aware=True,
    )


def test_replica_set_supports_transactions(mongo_up):
    with mongo_as("auth") as c:
        assert c.admin.command("hello")["setName"] == "rs0"
        with c.start_session() as s, s.start_transaction():
            c.auth.tx_probe.insert_one({"x": 1}, session=s)
        c.auth.tx_probe.drop()


# --- Redis, Kafka, SeaweedFS -----------------------------------------------------------------


def test_redis_requires_a_password():
    import redis

    try:
        redis.Redis(host="127.0.0.1", port=6379, socket_timeout=2).ping()
    except redis.AuthenticationError:
        pass
    except redis.ConnectionError:
        pytest.skip("redis not reachable on 127.0.0.1:6379")
    else:
        pytest.fail("redis answered without a password")
    assert redis.Redis(host="127.0.0.1", port=6379, password=ENV["REDIS_PASSWORD"]).ping()


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    local = os.environ.get("LOCALAPPDATA", "")
    docker = shutil.which("docker") or os.path.join(
        local, "Programs", "DockerDesktop", "resources", "bin", "docker.exe"
    )
    return subprocess.run(  # noqa: S603
        [docker, "compose", "-f", "compose.yml", "-f", "compose.dev.yml", *args],
        cwd=INFRA, capture_output=True, text=True, check=False,
    )


def test_kafka_topics_exist_with_three_partitions():
    # The loopback-only plaintext listener: from inside the broker's own container
    r = _compose("exec", "-T", "kafka", "/opt/kafka/bin/kafka-topics.sh",
                 "--bootstrap-server", "127.0.0.1:9094", "--describe")
    if r.returncode != 0:
        pytest.skip("kafka not running")
    lines = r.stdout.splitlines()
    for service in ("auth", "operations", "media", "report"):
        prefix = f"Topic: mms.{service}.events\t"
        line = next((x for x in lines if x.startswith(prefix)), "")
        assert "PartitionCount: 3" in line, f"mms.{service}.events missing or wrong"
    assert "mms.dlq.audit" in r.stdout


# TRD §15: Kafka needs SASL/SCRAM, and each service's user has ACLs on its own topics only.
# Checked from inside the auth container, which is on the backend network and has aiokafka.
KAFKA_PROBE = """
import asyncio, os, socket, sys
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

def scram(user, password):
    return dict(security_protocol="SASL_PLAINTEXT", sasl_mechanism="SCRAM-SHA-512",
                sasl_plain_username=user, sasl_plain_password=password)

async def outcome(make, act):
    client = make()
    try:
        await asyncio.wait_for(client.start(), 15)
        await asyncio.wait_for(act(client), 15)
        return "ok"
    except Exception as error:
        return type(error).__name__
    finally:
        try:
            await client.stop()
        except Exception:
            pass

def port(p):
    try:
        socket.create_connection(("kafka", p), 3).close()
        return "open"
    except OSError:
        return "closed"

async def main(case):
    own = os.environ["AUTH_KAFKA_PASSWORD"]
    produce = lambda c: c.send_and_wait("mms.dlq.audit", b"probe")
    if case == "anonymous":
        print(await outcome(lambda: AIOKafkaProducer(bootstrap_servers="kafka:9092",
                                                     request_timeout_ms=5000), produce))
    elif case == "wrong-password":
        print(await outcome(lambda: AIOKafkaProducer(bootstrap_servers="kafka:9092",
                                                     **scram("auth", "not-" + own)), produce))
    elif case == "other-topic":
        print(await outcome(lambda: AIOKafkaProducer(bootstrap_servers="kafka:9092",
                                                     **scram("auth", own)), produce))
    elif case == "consume":
        async def read(c):
            await c.getmany(timeout_ms=3000)
        print(await outcome(lambda: AIOKafkaConsumer("mms.auth.events",
                                                     bootstrap_servers="kafka:9092",
                                                     group_id="audit", **scram("auth", own)), read))
    elif case == "ports":
        print(port(9093), port(9094))

asyncio.run(main(sys.argv[1]))
"""


def _kafka_probe(case: str) -> str:
    r = _compose("exec", "-T", "auth", "python", "-c", KAFKA_PROBE, case)
    if r.returncode != 0 and not r.stdout:
        pytest.skip(f"auth not running: {r.stderr.strip()[:200]}")
    return r.stdout.strip().splitlines()[-1]


def test_kafka_refuses_clients_without_credentials():
    assert _kafka_probe("anonymous") != "ok"


def test_kafka_refuses_a_wrong_password():
    assert _kafka_probe("wrong-password") != "ok"


def test_a_service_cannot_write_another_services_topic():
    # auth may only write mms.auth.events (kafka/users.yml)
    assert _kafka_probe("other-topic") == "TopicAuthorizationFailedError"


def test_a_service_cannot_join_another_services_consumer_group():
    assert _kafka_probe("consume") != "ok"


def test_the_controller_and_plaintext_listeners_are_loopback_only():
    assert _kafka_probe("ports") == "closed closed"


def test_bucket_keys_are_limited_to_their_buckets():
    boto3 = pytest.importorskip("boto3")
    from botocore.exceptions import ClientError, EndpointConnectionError

    def s3(prefix: str):
        return boto3.client(
            "s3",
            endpoint_url="http://127.0.0.1:8333",
            aws_access_key_id=ENV[f"{prefix}_S3_ACCESS_KEY"],
            aws_secret_access_key=ENV[f"{prefix}_S3_SECRET_KEY"],
            region_name="us-east-1",
        )

    media, report = s3("MEDIA"), s3("REPORT")
    try:
        media.put_object(Bucket="mms-media", Key="probe.txt", Body=b"x")
    except EndpointConnectionError:
        pytest.skip("seaweedfs not reachable on 127.0.0.1:8333")
    assert report.get_object(Bucket="mms-media", Key="probe.txt")["Body"].read() == b"x"
    with pytest.raises(ClientError):
        report.put_object(Bucket="mms-media", Key="probe2.txt", Body=b"x")
    with pytest.raises(ClientError):
        media.put_object(Bucket="mms-reports", Key="probe.txt", Body=b"x")
    media.delete_object(Bucket="mms-media", Key="probe.txt")


# --- auth and platform: J1 and J2 end to end (IP Phase 1 exit criterion) ---------------------

ORG_A = "01900000-0000-7000-8000-00000000a000"  # mms_common.testing.seed


def api(web, method, path, token=None, **kw):
    """Login, register and reset share Nginx's `auth` zone (10/min per IP, burst 5), which the
    J1 and J2 tests together exceed: wait out a 429 rather than fail."""
    import time

    headers = {"Host": MMS, **kw.pop("headers", {})}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for _ in range(15):
        response = web.request(method, path, headers=headers, **kw)
        if response.status_code != 429:
            return response
        time.sleep(6)
    return response


@pytest.fixture(scope="session")
def seeded(web):
    r = _compose("exec", "-T", "-e", f"AUTH_SEED_PASSWORD={ENV['AUTH_SEED_PASSWORD']}", "auth",
                 "python", "-m", "app.cli", "seed")
    if r.returncode != 0:
        pytest.skip(f"auth not running: {r.stderr[-300:]}")
    return ENV["AUTH_SEED_PASSWORD"]


def test_services_are_routed_and_check_tokens_themselves(web):
    r = get(web, "/api/v1/auth/me")
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem")
    r = get(web, "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401
    assert get(web, "/api/v1/audit/events").status_code == 404  # platform: not built until P7
    r = get(web, "/api/v1/media/not-a-file")  # media (Phase 2): the token is checked first
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem")
    r = get(web, "/api/v1/stations")  # operations (Phase 2)
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem")
    assert get(web, "/api/v1/users").headers["cache-control"] == "no-store"


def test_register_approve_login_reset_lands_in_the_audit_chain(web, seeded, mongo_up):
    import time
    import uuid

    email = f"j1-{uuid.uuid4().hex[:8]}@example.org"
    r = api(web, "POST", "/api/v1/auth/register", json={
        "name": "J1 Client", "email": email, "password": "a long test password",
        "organization_name": "Organization A"})
    assert r.status_code == 202, r.text
    assert api(web, "POST", "/api/v1/auth/login",
               json={"email": email, "password": "a long test password"}).status_code == 403

    login = api(web, "POST", "/api/v1/auth/login",
                json={"email": "admin@example.org", "password": seeded})
    assert login.status_code == 200, login.text
    admin = login.json()["access_token"]
    found = api(web, "GET", "/api/v1/users", admin, params={"status": "pending", "q": email})
    [user] = found.json()["items"]
    r = api(web, "POST", f"/api/v1/users/{user['id']}/approve", admin, json={"org_id": ORG_A})
    assert r.status_code == 200, r.text

    client = api(web, "POST", "/api/v1/auth/login",
                 json={"email": email, "password": "a long test password"})
    assert client.status_code == 200, client.text
    cookie = client.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "Path=/api/v1/auth" in cookie
    refreshed = web.post("/api/v1/auth/refresh", headers={
        "Host": MMS, "Cookie": cookie.split(";", 1)[0]})
    assert refreshed.status_code == 200, refreshed.text
    assert api(web, "POST", "/api/v1/auth/password-reset/request",
               json={"email": email}).status_code == 202

    wanted = {"user.registered", "user.approved", "auth.login_succeeded",
              "auth.password_reset_requested", "auth.login_failed"}
    root = root_mongo()
    try:
        for _ in range(60):  # outbox relay -> Kafka -> platform audit consumer
            actions = {d["action"] for d in root.audit.audit_events.find(
                {"resource.id": user["id"]}, {"action": 1})}
            if wanted <= actions:
                break
            time.sleep(1)
        assert wanted <= actions, actions
        chain = list(root.audit.audit_events.find({"seq": {"$gte": 1}}).sort("seq", 1))
        assert [d["seq"] for d in chain] == list(range(1, len(chain) + 1))
        for before, after in itertools.pairwise(chain):
            assert after["prev_hash"] == before["hash"]
        head = root.audit.audit_state.find_one({"_id": "chain"})
        assert head["last_seq"] >= chain[-1]["seq"]  # more may have arrived since
    finally:
        root.close()


# --- operations: stations (Phase 2) -----------------------------------------------------------


def _login(web, email: str, password: str) -> str:
    r = api(web, "POST", "/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


def test_seeded_stations_are_scoped_by_organization_and_audited(web, seeded, mongo_up):
    """STN-6, ORG-3 through Nginx, and station events into the audit chain (AUD-1)."""
    import time

    for _ in range(30):  # operations copies the organizations from auth (events or backfill)
        r = _compose("exec", "-T", "operations", "python", "-m", "app.cli", "seed")
        if r.returncode == 0 and "Errors" not in r.stdout:
            break
        time.sleep(2)
    assert r.returncode == 0, r.stdout + r.stderr
    admin = _login(web, "admin@example.org", seeded)
    client = _login(web, "client.a1@example.org", seeded)
    staff = api(web, "GET", "/api/v1/stations", admin, params={"q": "-00"})
    codes = {s["code"] for s in staff.json()["items"]}
    assert {"JM-KIN-001", "TT-POS-001"} <= codes
    mine = api(web, "GET", "/api/v1/stations", client).json()["items"]
    assert mine and {s["owner_org_id"] for s in mine} == {ORG_A}
    other = next(s for s in staff.json()["items"] if s["code"] == "TT-POS-001")
    assert api(web, "GET", f"/api/v1/stations/{other['id']}", client).status_code == 404
    kingston = next(s for s in staff.json()["items"] if s["code"] == "JM-KIN-001")
    detail = api(web, "GET", f"/api/v1/stations/{kingston['id']}", client).json()
    assert detail["installed"] and detail["qr_token"] is None
    root = root_mongo()
    try:
        for _ in range(60):  # outbox relay -> Kafka -> platform audit consumer
            found = root.audit.audit_events.find_one(
                {"action": "station.created", "resource.id": kingston["id"]})
            if found:
                break
            time.sleep(1)
        assert found is not None
    finally:
        root.close()


# --- media: a document goes through the gateway and the files host (W6) ----------------------


def _uuid7() -> str:
    """A UUIDv7 for a device-made ID (rule 9): 48 bits of milliseconds, then random bits."""
    import secrets
    import time

    ms = int(time.time() * 1000)
    rand = secrets.randbits(74)
    value = (ms << 80) | (0x7 << 76) | ((rand >> 62) << 64) | (0b10 << 62) | (rand & (2**62 - 1))
    h = f"{value:032x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _to_files_host(url: str) -> tuple[str, str]:
    """A presigned URL is for the files host name; connect to the local Nginx and send that
    name, which is what the signature covers."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    assert parts.netloc == FILES, parts.netloc
    return f"{parts.path}?{parts.query}", parts.netloc


@pytest.mark.req("MED-6")
def test_a_document_goes_through_the_gateway_and_the_files_host(web, seeded, mongo_up):
    """The whole W6 path on the real stack: presigned multipart upload straight to the files host
    (8 MiB parts, CORS with the ETag readable), the media worker's checks, the document in
    operations, client visibility, and the events in the audit chain."""
    import hashlib
    import time

    for _ in range(30):
        r = _compose("exec", "-T", "operations", "python", "-m", "app.cli", "seed")
        if r.returncode == 0 and "Errors" not in r.stdout:
            break
        time.sleep(2)
    tech = _login(web, "tech1@example.org", seeded)
    client_a = _login(web, "client.a1@example.org", seeded)
    client_b = _login(web, "client.b1@example.org", seeded)
    stations = api(web, "GET", "/api/v1/stations", tech, params={"q": "JM-KIN-001"}).json()
    station = stations["items"][0]
    data = b"%PDF-1.7\n" + os.urandom(10 * 1024 * 1024)  # two parts: 8 MiB and the rest
    digest = hashlib.sha256(data).hexdigest()
    media_id = _uuid7()

    created = api(web, "POST", "/api/v1/uploads", tech, json={
        "media_id": media_id, "owner_ref": f"document:station:{station['id']}", "kind": "pdf",
        "filename": "Installation record.pdf", "size_bytes": len(data), "sha256": digest,
    })
    assert created.status_code == 201, created.text
    upload = created.json()
    assert upload["part_count"] == 2 and upload["part_size"] == 8 * 1024 * 1024

    origin = {"Origin": f"https://{MMS}"}
    for item in upload["urls"]:
        target, host = _to_files_host(item["url"])
        start = (item["part_number"] - 1) * upload["part_size"]
        chunk = data[start : start + upload["part_size"]]
        # The browser asks first; only the app's origin may upload.
        pre = web.request("OPTIONS", target, headers={
            "Host": host, **origin, "Access-Control-Request-Method": "PUT"})
        assert pre.headers.get("access-control-allow-origin") == f"https://{MMS}", pre.headers
        put = web.put(target, content=chunk, headers={"Host": host, **origin}, timeout=60)
        assert put.status_code == 200, put.text
        assert "etag" in put.headers.get("access-control-expose-headers", "").lower()
    refused = web.request("OPTIONS", target, headers={
        "Host": host, "Origin": "https://evil.example", "Access-Control-Request-Method": "PUT"})
    assert refused.headers.get("access-control-allow-origin") != "https://evil.example"

    done = api(web, "POST", f"/api/v1/uploads/{media_id}/complete", tech)
    assert done.status_code == 200 and done.json()["status"] == "uploaded", done.text
    for _ in range(60):  # media-worker: size, type, checksum, scan
        detail = api(web, "GET", f"/api/v1/media/{media_id}", tech).json()
        if detail["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    assert detail["status"] == "ready", detail
    assert detail["visibility"] == "staff" and detail["checksum_sha256"] == digest

    doc_id = _uuid7()
    made = api(web, "POST", "/api/v1/documents", tech, json={
        "id": doc_id, "scope": "station", "scope_id": station["id"], "doc_type": "installation",
        "title": "Installation record", "media_id": media_id})
    assert made.status_code == 201 and made.json()["status"] == "available", made.text
    # Staff-only until someone says otherwise: the owner's client can't see it (fail closed).
    assert api(web, "GET", f"/api/v1/documents/{doc_id}", client_a).status_code == 404
    assert api(web, "GET", f"/api/v1/media/{media_id}", client_a).status_code == 404

    link = api(web, "GET", f"/api/v1/documents/{doc_id}/download", tech).json()
    target, host = _to_files_host(link["url"])
    fetched = web.get(target, headers={"Host": host}, timeout=60)
    assert fetched.status_code == 200 and fetched.content == data
    assert fetched.headers["content-type"] == "application/pdf"
    assert fetched.headers["content-disposition"].startswith("inline;")

    shown = api(web, "PATCH", f"/api/v1/documents/{doc_id}", tech,
                json={"version": made.json()["version"], "client_visible": True})
    assert shown.status_code == 200
    for _ in range(60):  # operations -> Kafka -> media applies the visibility request
        if api(web, "GET", f"/api/v1/media/{media_id}", client_a).status_code == 200:
            break
        time.sleep(1)
    assert api(web, "GET", f"/api/v1/media/{media_id}", client_a).status_code == 200
    assert api(web, "GET", f"/api/v1/documents/{doc_id}/download", client_a).status_code == 200
    assert api(web, "GET", f"/api/v1/documents/{doc_id}", client_b).status_code == 404
    assert api(web, "GET", f"/api/v1/media/{media_id}", client_b).status_code == 404

    root = root_mongo()
    try:
        for action, resource in (("media.uploaded", media_id), ("document.uploaded", doc_id),
                                 ("media.visibility_requested", doc_id)):
            for _ in range(60):
                if root.audit.audit_events.find_one({"action": action, "resource.id": resource}):
                    break
                time.sleep(1)
            assert root.audit.audit_events.find_one(
                {"action": action, "resource.id": resource}), action
    finally:
        root.close()


# --- platform: account emails through Mailpit (NOT-3; J1 step 5, J2 step 4) -----------------

MAILPIT = "http://127.0.0.1:8025"


def _mail_to(address: str, subject: str, seconds: int = 60) -> dict:
    """The newest message to `address` with `subject`, waiting for the consumer and sender."""
    import time

    with httpx.Client(base_url=MAILPIT, timeout=5) as mailpit:
        for _ in range(seconds):
            found = mailpit.get("/api/v1/search", params={"query": f'to:"{address}"'}).json()
            for summary in found.get("messages", []):
                if summary["Subject"] == subject:
                    return mailpit.get(f"/api/v1/message/{summary['ID']}").json()
            time.sleep(1)
    raise AssertionError(f"no email {subject!r} to {address} within {seconds} s")


@pytest.fixture(scope="session")
def mailpit_up():
    try:
        httpx.get(f"{MAILPIT}/api/v1/info", timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Mailpit not running (compose.dev.yml)")


@pytest.mark.req("NOT-3")
def test_approval_and_reset_emails_arrive_and_the_reset_link_works(web, seeded, mailpit_up):
    import re
    import uuid

    email = f"j2-{uuid.uuid4().hex[:8]}@example.org"
    assert api(web, "POST", "/api/v1/auth/register", json={
        "name": "J2 Client", "email": email, "password": "a long test password",
        "organization_name": "Organization A"}).status_code == 202
    admin = api(web, "POST", "/api/v1/auth/login",
                json={"email": "admin@example.org", "password": seeded}).json()["access_token"]
    [user] = api(web, "GET", "/api/v1/users", admin,
                 params={"status": "pending", "q": email}).json()["items"]
    assert api(web, "POST", f"/api/v1/users/{user['id']}/approve", admin,
               json={"org_id": ORG_A}).status_code == 200

    approved = _mail_to(email, "Your MARS-MMS account is approved")
    assert f"https://{MMS}/login" in approved["Text"]
    assert approved["HTML"].count("<a ") == 1

    assert api(web, "POST", "/api/v1/auth/password-reset/request",
               json={"email": email}).status_code == 202
    reset = _mail_to(email, "Reset your MARS-MMS password")
    match = re.search(rf"https://{re.escape(MMS)}/reset-password/(\S+)", reset["Text"])
    assert match, reset["Text"]
    new_password = f"reset {uuid.uuid4().hex}"  # never on a breached list
    r = api(web, "POST", "/api/v1/auth/password-reset/confirm",
            json={"token": match.group(1), "password": new_password})
    assert r.status_code == 204, r.text
    assert api(web, "POST", "/api/v1/auth/login",
               json={"email": email, "password": new_password}).status_code == 200
    # Single use: the same link fails the second time.
    assert api(web, "POST", "/api/v1/auth/password-reset/confirm",
               json={"token": match.group(1), "password": f"again {uuid.uuid4().hex}"}
               ).status_code == 410


# --- Restarts (last: the stack must come back for whatever runs next) -------------------------


def test_mongo_comes_back_after_a_plain_restart(mongo_up):
    # A host reboot or crash restarts the same container, so /tmp still holds the last start's
    # key file. Staging, 2026-10-18: after a reboot mongod never came back (protected_regular).
    import time

    r = _compose("restart", "mongo")
    assert r.returncode == 0, r.stderr
    deadline = time.monotonic() + 120
    health = ""
    while time.monotonic() < deadline:
        health = _compose("ps", "--format", "{{.Health}}", "mongo").stdout.strip()
        if health == "healthy":
            break
        time.sleep(2)
    assert health == "healthy", _compose("logs", "--tail", "20", "mongo").stdout
    assert mongo_as("auth").admin.command("ping")["ok"] == 1
