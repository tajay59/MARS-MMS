"""Fixtures: throwaway MongoDB (single-node replica set, for transactions), Redis and Kafka
containers, on the same image versions as infra/compose.yml. Each starts only when a test
asks for it, and every test that needs one is skipped when Docker is not reachable."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient

MONGO_IMAGE = "mongo:8.0.34"
REDIS_IMAGE = "redis:7.4.11-alpine"
KAFKA_IMAGE = "apache/kafka:4.3.1"
RS_INIT = "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]}).ok"


def _docker() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    candidate = os.path.join(local, "Programs", "DockerDesktop", "resources", "bin", "docker.exe")
    if os.path.exists(candidate):
        # docker run shells out to helpers (docker-credential-desktop) that sit beside it
        os.environ["PATH"] += os.pathsep + os.path.dirname(candidate)
        return candidate
    return None


@pytest.fixture(scope="session")
def docker() -> str:
    path = _docker()
    if path is None or subprocess.run([path, "info"], capture_output=True).returncode != 0:
        pytest.skip("Docker is not available")
    return path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def _container(docker: str, prefix: str, args: list[str]) -> Iterator[str]:
    name = f"mms-test-{prefix}-{uuid.uuid4().hex[:8]}"
    subprocess.run([docker, "run", "-d", "--rm", "--name", name, *args], check=True,
                   capture_output=True)
    try:
        yield name
    finally:
        subprocess.run([docker, "rm", "-f", name], capture_output=True)


def _wait(check, what: str, seconds: int = 90) -> None:
    for _ in range(seconds):
        if check():
            return
        time.sleep(1)
    raise TimeoutError(f"{what} did not start in {seconds} s")


@pytest.fixture(scope="session")
def mongo_uri(docker):
    port = _free_port()
    args = ["-p", f"127.0.0.1:{port}:27017", MONGO_IMAGE, "--replSet", "rs0", "--bind_ip_all"]
    with _container(docker, "mongo", args) as name:

        def initiated() -> bool:
            r = subprocess.run([docker, "exec", name, "mongosh", "--quiet", "--eval", RS_INIT],
                               capture_output=True, text=True)
            return r.returncode == 0 and "1" in r.stdout

        def primary() -> bool:
            r = subprocess.run(
                [docker, "exec", name, "mongosh", "--quiet", "--eval",
                 "db.hello().isWritablePrimary"],
                capture_output=True, text=True,
            )
            return "true" in r.stdout

        _wait(initiated, "mongo")
        _wait(primary, "mongo primary")
        # directConnection: the set advertises "localhost:27017", unreachable from the host.
        yield f"mongodb://127.0.0.1:{port}/?directConnection=true"


@pytest_asyncio.fixture
async def mongo(mongo_uri):
    client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    db = client[f"t_{uuid.uuid4().hex[:8]}"]
    yield db
    await client.drop_database(db.name)
    await client.close()


@pytest.fixture(scope="session")
def redis_url(docker):
    port = _free_port()
    with _container(docker, "redis", ["-p", f"127.0.0.1:{port}:6379", REDIS_IMAGE]) as name:

        def up() -> bool:
            r = subprocess.run([docker, "exec", name, "redis-cli", "ping"],
                               capture_output=True, text=True)
            return "PONG" in r.stdout

        _wait(up, "redis")
        yield f"redis://127.0.0.1:{port}/0"


@pytest.fixture(scope="session")
def kafka_bootstrap(docker):
    # The broker must advertise the host-side port, so it is chosen before the container starts.
    port = _free_port()
    env = {
        "KAFKA_NODE_ID": "1",
        "KAFKA_PROCESS_ROLES": "broker,controller",
        # PLAINTEXT for the tests on the host; INTERNAL for the CLI inside the container, which
        # cannot reach the host-side address the PLAINTEXT listener advertises.
        "KAFKA_LISTENERS": "PLAINTEXT://:9092,INTERNAL://:19092,CONTROLLER://:9093",
        "KAFKA_ADVERTISED_LISTENERS": f"PLAINTEXT://127.0.0.1:{port},INTERNAL://localhost:19092",
        "KAFKA_INTER_BROKER_LISTENER_NAME": "INTERNAL",
        "KAFKA_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
        "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": (
            "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,INTERNAL:PLAINTEXT"
        ),
        "KAFKA_CONTROLLER_QUORUM_VOTERS": "1@localhost:9093",
        "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
        "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR": "1",
        "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR": "1",
        "KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS": "0",
        "KAFKA_AUTO_CREATE_TOPICS_ENABLE": "false",
    }
    args = ["-p", f"127.0.0.1:{port}:9092"]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    with _container(docker, "kafka", [*args, KAFKA_IMAGE]) as name:

        def up() -> bool:
            r = subprocess.run(
                [docker, "exec", name, "/opt/kafka/bin/kafka-broker-api-versions.sh",
                 "--bootstrap-server", "localhost:19092"],
                capture_output=True, text=True,
            )
            return r.returncode == 0

        _wait(up, "kafka", seconds=120)
        bootstrap = f"127.0.0.1:{port}"

        def create_topic(topic: str, partitions: int = 3) -> None:
            subprocess.run(
                [docker, "exec", name, "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server",
                 "localhost:19092", "--create", "--if-not-exists", "--topic", topic,
                 "--partitions", str(partitions), "--replication-factor", "1"],
                check=True, capture_output=True,
            )

        yield bootstrap, create_topic
