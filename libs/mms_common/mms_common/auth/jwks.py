"""Public signing keys fetched from auth over the internal network (TRD §6.1).

`http://auth:8000/.well-known/jwks.json` is cached in Redis for 10 minutes and refetched on
an unknown `kid`, at most once every 30 s so a flood of forged `kid`s can't hammer auth.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any, Protocol

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from mms_common.auth.tokens import public_key_from_jwk
from mms_common.logging import get_logger
from mms_common.time import Clock

CACHE_KEY = "jwks:auth"
CACHE_TTL_S = 600
MIN_REFETCH_S = 30.0

log = get_logger(__name__)


class Cache(Protocol):
    def get(self, name: str) -> Awaitable[Any]: ...
    def set(self, name: str, value: str, *, ex: int) -> Awaitable[Any]: ...


class JwksKeys:
    def __init__(
        self,
        url: str,
        cache: Cache,
        clock: Clock,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url
        self._cache = cache
        self._clock = clock
        self._http = http
        self._keys: dict[str, Ed25519PublicKey] = {}
        self._last_fetch = float("-inf")

    async def get(self, kid: str) -> Ed25519PublicKey | None:
        if kid in self._keys:
            return self._keys[kid]
        cached = await self._cache.get(CACHE_KEY)
        if cached:
            self._load(json.loads(cached))
            if kid in self._keys:
                return self._keys[kid]
        now = self._clock.now().timestamp()
        if now - self._last_fetch < MIN_REFETCH_S:
            return None
        self._last_fetch = now
        try:
            body = await self._fetch()
        except httpx.HTTPError as exc:
            log.warning("jwks_fetch_failed", error=str(exc))
            return None
        await self._cache.set(CACHE_KEY, json.dumps(body), ex=CACHE_TTL_S)
        self._load(body)
        return self._keys.get(kid)

    async def _fetch(self) -> dict[str, Any]:
        if self._http is not None:
            response = await self._http.get(self._url, timeout=5)
        else:
            async with httpx.AsyncClient() as http:
                response = await http.get(self._url, timeout=5)
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return body

    def _load(self, body: dict[str, Any]) -> None:
        keys: dict[str, Ed25519PublicKey] = {}
        for jwk in body.get("keys", []):
            try:
                keys[str(jwk["kid"])] = public_key_from_jwk(jwk)
            except (KeyError, ValueError):
                continue
        # Replace, don't merge: a key auth has dropped stops verifying within 10 minutes.
        self._keys = keys
