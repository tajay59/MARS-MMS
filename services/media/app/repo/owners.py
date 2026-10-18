"""The owner check on upload (TRD §3.3): media asks the service that owns the thing a file is
attached to whether this user may attach to it, and which organization the file belongs to.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from mms_common.auth import User
from mms_common.auth.service_client import ServiceTokens
from mms_common.errors import AppError, Forbidden, NotFound


class OwnerUnavailable(AppError):
    status, code, title = 503, "owner_unavailable", "Try again in a moment"


@dataclass(frozen=True)
class Attachable:
    org_id: str | None  # the organization the file belongs to; None for model documents


class OwnerClient:
    def __init__(self, urls: dict[str, str], tokens: ServiceTokens, http: httpx.AsyncClient):
        self._urls, self._tokens, self._http = urls, tokens, http

    async def attachable(
        self, service: str, owner_ref: str, user: User, request_id: str | None = None
    ) -> Attachable:
        """Raises `NotFound` when the owner does not exist or is out of the user's scope, and
        `Forbidden` when their role may not attach to it (a viewer)."""
        base = self._urls.get(service)
        if base is None:
            raise NotFound()
        try:
            response = await self._http.get(
                f"{base.rstrip('/')}/internal/attachable",
                params={
                    "owner_ref": owner_ref, "user_id": user.id,
                    "roles": ",".join(sorted(user.roles)), "org_id": user.org_id or "",
                },
                headers=await self._tokens.headers(request_id),
                timeout=5,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise OwnerUnavailable() from e
        if response.status_code == 404:
            raise NotFound()
        if response.status_code == 403:
            raise Forbidden()
        if response.status_code != 200:
            raise OwnerUnavailable()
        org = response.json().get("org_id")
        return Attachable(org_id=org if isinstance(org, str) else None)
