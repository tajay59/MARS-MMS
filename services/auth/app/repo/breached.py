"""Breached-password lists (AUTH-9, TRD §6.2, T1).

`HibpCheck` asks the Have I Been Pwned range API with k-anonymity: only the first five hex
characters of the password's SHA-1 leave the server, padded so the response size reveals
nothing. If the API is unreachable it falls back to the local list; with no local list the
password is accepted and the failure logged, so an outage never blocks registration.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from mms_common.logging import get_logger
from prometheus_client import Counter

log = get_logger(__name__)
UNCHECKED = Counter(
    "auth_breached_check_unavailable_total",
    "Passwords accepted without a breached-list check because no list was reachable",
)


def _sha1(password: str) -> str:
    return hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()


class NoCheck:
    async def is_breached(self, password: str) -> bool:
        return False


class FileCheck:
    """A local list: one uppercase SHA-1 hex per line, optionally `:count` after it."""

    def __init__(self, path: str) -> None:
        self._hashes = {
            line.split(":", 1)[0].strip().upper()
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    async def is_breached(self, password: str) -> bool:
        return _sha1(password) in self._hashes


class HibpCheck:
    def __init__(
        self,
        url: str,
        timeout_s: float,
        fallback: FileCheck | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url
        self._timeout = timeout_s
        self._fallback = fallback
        self._http = http

    async def is_breached(self, password: str) -> bool:
        digest = _sha1(password)
        try:
            body = await self._range(digest[:5])
        except httpx.HTTPError as exc:
            log.warning("hibp_unreachable", error=type(exc).__name__)
            if self._fallback is not None:
                return await self._fallback.is_breached(password)
            UNCHECKED.inc()
            return False
        suffix = digest[5:]
        for line in body.splitlines():
            found, _, count = line.partition(":")
            if found.strip().upper() == suffix and count.strip() not in ("", "0"):
                return True  # padding entries have a count of 0
        return False

    async def _range(self, prefix: str) -> str:
        headers = {"Add-Padding": "true", "User-Agent": "aws-mms-auth"}
        url = self._url + prefix
        if self._http is not None:
            response = await self._http.get(url, headers=headers, timeout=self._timeout)
        else:
            async with httpx.AsyncClient() as http:
                response = await http.get(url, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return response.text
