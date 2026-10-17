"""Fixtures. The Mongo fixture is a real single-node replica set because the outbox
needs transactions; it is skipped when Docker is not reachable."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient

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
def mongo_uri():
    docker = _docker()
    if docker is None or subprocess.run([docker, "info"], capture_output=True).returncode != 0:
        pytest.skip("Docker is not available")
    name = f"mms-test-mongo-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [docker, "run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::27017",
         "mongo:8", "--replSet", "rs0", "--bind_ip_all"],
        check=True, capture_output=True,
    )
    try:
        port = subprocess.run(
            [docker, "port", name, "27017/tcp"], check=True, capture_output=True, text=True
        ).stdout.strip().splitlines()[0].split(":")[-1]
        for _ in range(60):
            r = subprocess.run(
                [docker, "exec", name, "mongosh", "--quiet", "--eval", RS_INIT],
                capture_output=True, text=True,
            )
            if r.returncode == 0 and "1" in r.stdout:
                break
            time.sleep(1)
        time.sleep(2)  # let the node win its election
        # directConnection: the set advertises "localhost:27017", unreachable from the host.
        yield f"mongodb://127.0.0.1:{port}/?directConnection=true"
    finally:
        subprocess.run([docker, "rm", "-f", name], capture_output=True)


@pytest_asyncio.fixture
async def mongo(mongo_uri):
    client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    db = client[f"t_{uuid.uuid4().hex[:8]}"]
    yield db
    await client.drop_database(db.name)
    await client.close()
