"""Media's side of a visit report: where a file stands, and the display copy of a photo
(`/internal/media/...`, W16-7). The report service has no rights on media's buckets."""

from __future__ import annotations

from typing import Protocol

import httpx
from mms_common.auth.service_client import ServiceTokens

from app.repo.operations import OperationsUnavailable


class MediaSource(Protocol):
    async def status(self, media_id: str) -> str | None:
        """`pending`, `uploaded`, `processing`, `ready`, `failed` or `deleted`; None if unknown."""
        ...

    async def rendition(self, media_id: str, *, thumbnail: bool = False) -> bytes | None:
        """The photo's display copy (WebP), or with `thumbnail` the small picture of a photo or
        a video's poster frame; None when it has none (not ready, not a picture)."""
        ...


class MediaClient:
    def __init__(self, base_url: str, tokens: ServiceTokens, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._tokens, self._http = tokens, http

    async def _get(self, path: str) -> httpx.Response:
        try:
            return await self._http.get(
                f"{self._base}{path}", headers=await self._tokens.headers(), timeout=30)
        except (httpx.HTTPError, ConnectionError) as e:
            raise OperationsUnavailable() from e

    async def status(self, media_id: str) -> str | None:
        response = await self._get(f"/internal/media/{media_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise OperationsUnavailable(str(response.status_code))
        status: str = response.json()["status"]
        return status

    async def rendition(self, media_id: str, *, thumbnail: bool = False) -> bytes | None:
        variant = "?variant=thumbnail" if thumbnail else ""
        response = await self._get(f"/internal/media/{media_id}/rendition{variant}")
        if response.status_code in (404, 409):
            return None
        if response.status_code != 200:
            raise OperationsUnavailable(str(response.status_code))
        return response.content
