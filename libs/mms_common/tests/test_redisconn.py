"""The shared Redis client (mms_common.redisconn) and revocation after a commit, against a real
Redis: a connection dropped while idle no longer fails the next command (found 2026-11-19, when
auth answered 500 after committing an organization's deactivation)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from redis.exceptions import ConnectionError as RedisConnectionError

from mms_common import redisconn
from mms_common.auth import revocation
from mms_common.metrics import REVOCATION_FAILURES


@pytest_asyncio.fixture
async def redis(redis_url):
    client = redisconn.connect(redis_url)
    yield client
    await client.aclose()


async def test_a_connection_killed_while_idle_is_replaced_on_the_next_command(redis, redis_url):
    key = f"t:{uuid.uuid4().hex}"
    await redis.set(key, "1")
    # Another client kills every normal connection, as a Redis restart or a NAT timeout would
    admin = redisconn.connect(redis_url)
    try:
        own = (await redis.client_id())
        assert await admin.client_kill_filter(_id=own) == 1
    finally:
        await admin.aclose()
    # The pooled connection is dead; the command still succeeds on a fresh one
    assert await redis.get(key) == b"1"
    await redis.set(key, "2")
    assert await redis.get(key) == b"2"


def test_every_client_checks_idle_connections_and_retries():
    client = redisconn.connect("redis://localhost:6390/0")
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["health_check_interval"] == redisconn.HEALTH_CHECK_INTERVAL_S
    assert kwargs["socket_keepalive"] is True
    assert kwargs["retry"].get_retries() == redisconn.RETRIES
    assert RedisConnectionError in kwargs["retry_on_error"]


class _Down:
    """A store whose writes always fail, as when Redis stays unreachable after the retries."""

    async def set(self, name: str, value: str, *, ex: int) -> None:
        raise RedisConnectionError("Connection lost")

    async def mget(self, keys: list[str]) -> list[None]:
        return [None for _ in keys]


async def test_a_revocation_redis_refuses_after_a_commit_is_counted_not_raised():
    before = REVOCATION_FAILURES.labels("org")._value.get()
    written = await revocation.after_commit(
        revocation.revoke_org(_Down(), "org-1", datetime.now(UTC)), kind="org"
    )
    assert written is False
    assert REVOCATION_FAILURES.labels("org")._value.get() == before + 1


async def test_a_revocation_that_lands_says_so(redis):
    org = f"org-{uuid.uuid4().hex[:8]}"
    at = datetime.now(UTC)
    assert await revocation.after_commit(revocation.revoke_org(redis, org, at), kind="org") is True
    issued = int(at.timestamp())
    assert await revocation.is_revoked(redis, user_id="u", org_id=org, issued_at=issued)


@pytest.mark.parametrize("kind", ["user", "org"])
def test_the_failure_counter_has_a_series_per_kind(kind):
    REVOCATION_FAILURES.labels(kind)  # exists, so the alert has something to watch from start-up
