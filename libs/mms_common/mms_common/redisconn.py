"""The one way a service opens Redis.

`Redis.from_url(url)` with its defaults kept pooled connections without checking them, so a
connection Redis or the network had dropped while idle failed on its next use. In auth that
turned a committed organization deactivation into a 500 (found 2026-11-19). Here every
connection is checked before use when it has been idle, sockets are kept alive, and a dropped
connection or a timeout is retried a few times with a short backoff before the error reaches
the caller. Every Redis write the services make is safe to repeat (SET with a value, queue
pushes guarded by job ids), so a retried command does no harm.
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

HEALTH_CHECK_INTERVAL_S = 30
CONNECT_TIMEOUT_S = 5.0
RETRIES = 3


def connect(url: str) -> Redis:
    """A client for `url` that survives a dropped idle connection."""
    return Redis.from_url(
        url,
        health_check_interval=HEALTH_CHECK_INTERVAL_S,
        socket_keepalive=True,
        socket_connect_timeout=CONNECT_TIMEOUT_S,
        retry=Retry(ExponentialBackoff(cap=1.0, base=0.05), RETRIES),
        retry_on_error=[RedisConnectionError, RedisTimeoutError],
    )
