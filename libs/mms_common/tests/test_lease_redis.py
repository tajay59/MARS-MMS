"""The outbox leader lease against a real Redis (TRD §8.2): exclusive, renewable, taken over
after expiry, and only the holder can renew or release it."""

from __future__ import annotations

import asyncio
import uuid

import pytest_asyncio
from redis.asyncio import Redis

from mms_common.outbox import LEASE_TTL_MS, LeaderLease, lease_key


@pytest_asyncio.fixture
async def redis(redis_url):
    client = Redis.from_url(redis_url)
    yield client
    await client.aclose()


def service() -> str:
    return f"svc-{uuid.uuid4().hex[:6]}"


async def test_set_nx_px_with_the_trd_ttl(redis):
    name = service()
    lease = LeaderLease(redis, name, "a")
    assert await lease.acquire_or_renew()
    assert await redis.get(lease_key(name)) == b"a"
    assert 0 < await redis.pttl(lease_key(name)) <= LEASE_TTL_MS


async def test_only_one_holder(redis):
    name = service()
    a, b = LeaderLease(redis, name, "a"), LeaderLease(redis, name, "b")
    assert await a.acquire_or_renew()
    assert not await b.acquire_or_renew()


async def test_renewal_extends_the_lease(redis):
    name = service()
    a = LeaderLease(redis, name, "a", ttl_ms=600)
    await a.acquire_or_renew()
    for _ in range(4):  # 4 x 300 ms > 600 ms: survives only because each call renews
        await asyncio.sleep(0.3)
        assert await a.acquire_or_renew()
    assert await redis.get(lease_key(name)) == b"a"


async def test_a_dead_leader_is_replaced_after_expiry_and_cannot_renew(redis):
    name = service()
    a = LeaderLease(redis, name, "a", ttl_ms=300)
    b = LeaderLease(redis, name, "b", ttl_ms=300)
    await a.acquire_or_renew()
    await asyncio.sleep(0.45)  # a stops renewing (died or stalled)
    assert await b.acquire_or_renew()
    assert not await a.acquire_or_renew()  # the old leader must not publish any more
    assert not a.held
    assert await redis.get(lease_key(name)) == b"b"


async def test_a_non_holder_cannot_release_or_renew_someone_elses_lease(redis):
    name = service()
    a = LeaderLease(redis, name, "a")
    await a.acquire_or_renew()
    impostor = LeaderLease(redis, name, "x")
    impostor.held = True  # believes it holds the lease (e.g. after a long GC pause)
    assert not await impostor.acquire_or_renew()
    impostor.held = True
    await impostor.release()
    assert await redis.get(lease_key(name)) == b"a"


async def test_release_hands_over_at_once(redis):
    name = service()
    a, b = LeaderLease(redis, name, "a"), LeaderLease(redis, name, "b")
    await a.acquire_or_renew()
    await a.release()
    assert await b.acquire_or_renew()
