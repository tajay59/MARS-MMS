"""The step between a correct password and a session (decision W22-1), kept in Redis.

A challenge is a random token that carries no rights: only its SHA-256 is a key, it maps to a user
ID and its purpose, lives five minutes, allows a handful of tries and is used once. It is not a
JWT and no other service ever sees it.

The pending secret of an enrolment in progress waits here too, sealed, until a code proves the
person's app has it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.domain.tokens import new_token, token_hash

VERIFY = "verify"  # the person has TOTP: a code or a recovery code finishes the sign-in
ENROL = "enrol"  # the person needs TOTP and has none: only enrolment finishes the sign-in
PENDING_TTL_S = 600


@dataclass(frozen=True)
class Challenge:
    user_id: str
    purpose: str


def _key(token: str) -> str:
    return f"auth:mfa:{token_hash(token)}"


def _tries(token: str) -> str:
    return f"auth:mfa-tries:{token_hash(token)}"


def _pending(user_id: str) -> str:
    return f"auth:totp-pending:{user_id}"


async def create(redis: Any, user_id: str, purpose: str, ttl_s: int) -> str:
    token = new_token()
    await redis.set(_key(token), json.dumps({"user_id": user_id, "purpose": purpose}), ex=ttl_s)
    return token


async def peek(redis: Any, token: str, purpose: str) -> Challenge | None:
    """The challenge if it exists and is for `purpose`. Costs no try."""
    raw = await redis.get(_key(token))
    if raw is None:
        return None
    data = json.loads(raw)
    return Challenge(data["user_id"], data["purpose"]) if data["purpose"] == purpose else None


async def attempt(redis: Any, token: str, purpose: str, max_tries: int) -> Challenge | None:
    """Like `peek`, and counts one try. The challenge is gone after `max_tries`."""
    found = await peek(redis, token, purpose)
    if found is None:
        return None
    count = int(await redis.incr(_tries(token)))
    if count == 1:
        await redis.expire(_tries(token), await redis.ttl(_key(token)))
    if count > max_tries:
        await consume(redis, token)
        return None
    return found


async def consume(redis: Any, token: str) -> bool:
    """True for the one caller that removed it: a second use of the same challenge gets False."""
    removed = int(await redis.delete(_key(token)))
    await redis.delete(_tries(token))
    return removed == 1


async def put_pending(redis: Any, user_id: str, sealed: str) -> None:
    await redis.set(_pending(user_id), sealed, ex=PENDING_TTL_S)


async def get_pending(redis: Any, user_id: str) -> str | None:
    raw = await redis.get(_pending(user_id))
    return raw.decode() if isinstance(raw, bytes) else raw


async def clear_pending(redis: Any, user_id: str) -> None:
    await redis.delete(_pending(user_id))
