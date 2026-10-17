"""Checks against the running local stack (TP Phase 1: Nginx routing, 404 for /internal/,
CSP, database isolation, audit insert-only role).

    cd infra && docker compose -f compose.yml -f compose.dev.yml up -d
    ../.venv/Scripts/python -m pytest tests -q        (Windows; bin/python elsewhere)

Skipped when the stack is not running.
"""

from __future__ import annotations

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


@pytest.mark.parametrize(
    "path",
    ["/api/v1/auth/me", "/api/v1/stations", "/api/v1/uploads", "/api/v1/reports", "/api/v1/audit"],
)
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
    with mongo_as("audit") as c:
        events = c.audit.audit_events
        events.insert_one({"_id": "probe", "seq": 0})
        assert events.find_one({"_id": "probe"})
        with pytest.raises(OperationFailure):
            events.update_one({"_id": "probe"}, {"$set": {"seq": 1}})
        with pytest.raises(OperationFailure):
            events.delete_one({"_id": "probe"})
        with pytest.raises(OperationFailure):
            events.drop()
        c.audit.audit_state.update_one({"_id": "chain"}, {"$set": {"last_seq": 0}}, upsert=True)
    root = MongoClient(
        f"mongodb://root:{ENV['MONGO_ROOT_PASSWORD']}@127.0.0.1:{MONGO_PORT}/?directConnection=true"
    )
    root.audit.audit_events.delete_one({"_id": "probe"})  # test cleanup only
    root.close()


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
    r = _compose("exec", "-T", "kafka", "/opt/kafka/bin/kafka-topics.sh",
                 "--bootstrap-server", "localhost:9092", "--describe")
    if r.returncode != 0:
        pytest.skip("kafka not running")
    lines = r.stdout.splitlines()
    for service in ("auth", "operations", "media", "report"):
        prefix = f"Topic: mms.{service}.events\t"
        line = next((x for x in lines if x.startswith(prefix)), "")
        assert "PartitionCount: 3" in line, f"mms.{service}.events missing or wrong"
    assert "mms.dlq.audit" in r.stdout


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
