"""Access-token revocation for disabled users and deactivated organizations (AUTH-11, ORG-4).

Access tokens are stateless and live 15 minutes. When auth disables a user, deactivates an
organization or completes a password reset, it records the moment in Redis; every service
then refuses tokens issued at or before it. The key outlives the longest access token, so
no token from before the change can come back.

After a restore from backup (W20-9) one more key ends every session at once: a dump brings back
users and sessions as they were, so anyone disabled since would be valid again.
"""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from typing import Any, Protocol

from mms_common.auth.tokens import ACCESS_TTL

KEY_TTL_S = int(ACCESS_TTL.total_seconds()) + 120


def user_key(user_id: str) -> str:
    return f"auth:revoked:user:{user_id}"


def org_key(org_id: str) -> str:
    return f"auth:revoked:org:{org_id}"


ALL_KEY = "auth:revoked:all"


class Store(Protocol):
    def set(self, name: str, value: str, *, ex: int) -> Awaitable[Any]: ...
    def mget(self, keys: list[str]) -> Awaitable[list[Any]]: ...


async def revoke_user(store: Store, user_id: str, at: datetime) -> None:
    await store.set(user_key(user_id), str(int(at.timestamp())), ex=KEY_TTL_S)


async def revoke_org(store: Store, org_id: str, at: datetime) -> None:
    await store.set(org_key(org_id), str(int(at.timestamp())), ex=KEY_TTL_S)


async def revoke_all(store: Store, at: datetime) -> None:
    """Every access token issued at or before `at` is refused, whoever holds it."""
    await store.set(ALL_KEY, str(int(at.timestamp())), ex=KEY_TTL_S)


async def is_revoked(store: Store, *, user_id: str, org_id: str | None, issued_at: int) -> bool:
    keys = [user_key(user_id)] + ([org_key(org_id)] if org_id else []) + [ALL_KEY]
    for value in await store.mget(keys):
        if value is not None and issued_at <= int(value):
            return True
    return False
