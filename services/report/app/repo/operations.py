"""Operations' side of a label sheet: the stations to print, with their QR tokens
(`POST /internal/labels`). Tokens travel in no event or snapshot, so this is the only way
to read them (rule 1: report never touches operations' database)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from mms_common.auth.service_client import ServiceTokens


class OperationsUnavailable(Exception):
    """Operations did not answer, or answered with an error. The job tries again."""


@dataclass(frozen=True)
class StationLabel:
    station_id: str
    code: str
    name: str
    org_name: str
    qr_token: str


class LabelSource(Protocol):
    async def labels(
        self, station_ids: list[str], request_id: str | None = None
    ) -> list[StationLabel]: ...


class SnapshotSource(Protocol):
    async def snapshot(
        self, entity: str, after: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]: ...


class OperationsClient:
    def __init__(self, base_url: str, tokens: ServiceTokens, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._tokens, self._http = tokens, http

    async def labels(
        self, station_ids: list[str], request_id: str | None = None
    ) -> list[StationLabel]:
        try:
            response = await self._http.post(
                f"{self._base}/internal/labels",
                json={"station_ids": station_ids},
                headers=await self._tokens.headers(request_id),
                timeout=15,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise OperationsUnavailable() from e
        if response.status_code != 200:
            raise OperationsUnavailable(str(response.status_code))
        rows: list[dict[str, Any]] = response.json()
        return [
            StationLabel(
                station_id=r["station_id"], code=r["code"], name=r["name"],
                org_name=r["org_name"], qr_token=r["qr_token"],
            )
            for r in rows
        ]

    async def snapshot(
        self, entity: str, after: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        """One page of `/internal/snapshot/<entity>` and the cursor for the next (TRD §8.6)."""
        params: dict[str, Any] = {"limit": 500}
        if after:
            params["after"] = after
        try:
            response = await self._http.get(
                f"{self._base}/internal/snapshot/{entity}", params=params,
                headers=await self._tokens.headers(), timeout=30,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise OperationsUnavailable() from e
        if response.status_code != 200:
            raise OperationsUnavailable(str(response.status_code))
        body = response.json()
        items: list[dict[str, Any]] = body["items"]
        next_after: str | None = body.get("next_after")
        return items, next_after
