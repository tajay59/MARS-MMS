"""Asking the media service about files (TRD §3.2, §3.3): has this file arrived, whose is it,
where does it stand, and a download link for one that passed its checks.

Operations never reads media's database (rule 1); these are media's `/internal/*` routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx
from mms_common.auth.service_client import ServiceTokens
from mms_common.errors import AppError, Conflict


class MediaUnavailable(AppError):
    status, code, title = 503, "media_unavailable", "Try again in a moment"


@dataclass(frozen=True)
class FileInfo:
    id: str
    owner_ref: str
    kind: str
    filename: str
    size_bytes: int
    status: str
    uploaded_by: str
    org_id: str | None
    checksum_sha256: str
    scan_status: str | None


@dataclass(frozen=True)
class Link:
    url: str
    expires_at: datetime


class MediaApi(Protocol):
    async def info(self, media_id: str, request_id: str | None = None) -> FileInfo | None: ...

    async def link(
        self, media_id: str, *, inline: bool, request_id: str | None = None
    ) -> Link: ...


class MediaClient:
    def __init__(self, base_url: str, tokens: ServiceTokens, http: httpx.AsyncClient) -> None:
        self._base, self._tokens, self._http = base_url.rstrip("/"), tokens, http

    async def info(self, media_id: str, request_id: str | None = None) -> FileInfo | None:
        """The file's record, or None when media has no such file."""
        try:
            response = await self._http.get(
                f"{self._base}/internal/media/{media_id}",
                headers=await self._tokens.headers(request_id), timeout=5,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise MediaUnavailable() from e
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise MediaUnavailable()
        body = response.json()
        return FileInfo(
            id=body["id"], owner_ref=body["owner_ref"], kind=body["kind"],
            filename=body["filename"], size_bytes=body["size_bytes"], status=body["status"],
            uploaded_by=body["uploaded_by"], org_id=body.get("org_id"),
            checksum_sha256=body["checksum_sha256"], scan_status=body.get("scan_status"),
        )

    async def link(
        self, media_id: str, *, inline: bool, request_id: str | None = None
    ) -> Link:
        try:
            response = await self._http.post(
                f"{self._base}/internal/media/{media_id}/url", json={"inline": inline},
                headers=await self._tokens.headers(request_id), timeout=5,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise MediaUnavailable() from e
        if response.status_code == 409:
            raise Conflict("The file isn't ready yet", reason="not_ready")
        if response.status_code != 200:
            raise MediaUnavailable()
        body = response.json()
        return Link(url=body["url"], expires_at=datetime.fromisoformat(body["expires_at"]))
