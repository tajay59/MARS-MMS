"""Service tokens for `/internal/*` calls (TRD §6.4).

A service exchanges its secret for a 5-minute token at `auth /internal/service-token` and
reuses it until a minute before it expires.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx

from mms_common.time import Clock

RENEW_BEFORE = timedelta(minutes=1)


class ServiceTokens:
    def __init__(
        self,
        auth_url: str,
        service: str,
        secret: str,
        clock: Clock,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = auth_url.rstrip("/") + "/internal/service-token"
        self._auth = (service, secret)
        self._clock = clock
        self._http = http
        self._token: str | None = None
        self._expires: datetime | None = None
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        async with self._lock:
            now = self._clock.now()
            if self._token and self._expires and now < self._expires - RENEW_BEFORE:
                return self._token
            if self._http is not None:
                response = await self._http.post(self._url, auth=self._auth, timeout=5)
            else:
                async with httpx.AsyncClient() as http:
                    response = await http.post(self._url, auth=self._auth, timeout=5)
            response.raise_for_status()
            body = response.json()
            self._token = str(body["access_token"])
            self._expires = now + timedelta(seconds=int(body["expires_in"]))
            return self._token

    async def headers(self, request_id: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {await self.token()}"}
        if request_id:
            headers["X-Request-ID"] = request_id
        return headers
