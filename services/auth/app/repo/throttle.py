"""Login throttle and reset-request limit in Redis (AUTH-10, TRD §6.2).

Keyed by the hash of the normalized email whether or not the account exists, so the
throttle itself can't reveal which emails are registered.
"""

from __future__ import annotations

from typing import Any


def _fail_key(email_hash: str) -> str:
    return f"auth:login-fail:{email_hash}"


def _reset_key(email_hash: str) -> str:
    return f"auth:reset-req:{email_hash}"


async def is_locked(redis: Any, email_hash: str, max_failures: int) -> bool:
    count = await redis.get(_fail_key(email_hash))
    return count is not None and int(count) >= max_failures


async def record_failure(redis: Any, email_hash: str, window_s: int) -> None:
    """5 failures within 15 minutes of the first lock the account for the rest of the window."""
    key = _fail_key(email_hash)
    if await redis.incr(key) == 1:
        await redis.expire(key, window_s)


async def clear(redis: Any, email_hash: str) -> None:
    await redis.delete(_fail_key(email_hash))


async def allow_reset_request(redis: Any, email_hash: str, per_hour: int) -> bool:
    key = _reset_key(email_hash)
    count = int(await redis.incr(key))
    if count == 1:
        await redis.expire(key, 3600)
    return count <= per_hour
