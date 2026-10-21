"""Asking auth who people are (W9-2): operations keeps no copy of users, so assigning a
request checks the chosen people with auth's `/internal/users/lookup` (rule 1)."""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from mms_common.auth.service_client import ServiceTokens
from mms_common.errors import AppError


class StaffUnavailable(AppError):
    status, code, title = 503, "staff_unavailable", "Try again in a moment"


class StaffApi(Protocol):
    async def lookup(
        self, ids: list[str], request_id: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """`{id: {id, name, roles, status}}` for the people that exist."""
        ...


class StaffClient:
    def __init__(self, base_url: str, tokens: ServiceTokens, http: httpx.AsyncClient) -> None:
        self._base, self._tokens, self._http = base_url.rstrip("/"), tokens, http

    async def lookup(
        self, ids: list[str], request_id: str | None = None
    ) -> dict[str, dict[str, Any]]:
        try:
            response = await self._http.post(
                f"{self._base}/internal/users/lookup", json={"ids": ids},
                headers=await self._tokens.headers(request_id), timeout=5,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise StaffUnavailable() from e
        if response.status_code != 200:
            raise StaffUnavailable()
        return {u["id"]: u for u in response.json()["users"]}
