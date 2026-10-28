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


class LockRefused(Exception):  # noqa: N818 - reads as the answer it is
    """Operations will not lock the visit for this report: another report version holds it
    (`locked_by_another_report`), the visit has not ended (`not_ended`) or is not known."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VisitLocks(Protocol):
    async def lock(self, visit_id: str, report_id: str, version: int) -> None: ...

    async def unlock(self, visit_id: str, report_id: str, version: int) -> None: ...


class FactsSource(Protocol):
    async def visit_facts(self, visit_id: str) -> dict[str, Any] | None: ...

    async def client_report_facts(self, client_report_id: str) -> dict[str, Any] | None: ...


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

    async def _lock_call(self, action: str, visit_id: str, report_id: str, version: int) -> None:
        try:
            response = await self._http.post(
                f"{self._base}/internal/visits/{visit_id}/{action}",
                json={"report_id": report_id, "report_version": version},
                headers=await self._tokens.headers(), timeout=30,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise OperationsUnavailable() from e
        if response.status_code in (404, 409):
            code = "visit_not_found" if response.status_code == 404 else "refused"
            try:
                code = str(response.json().get("code", code))
            except ValueError:
                pass
            raise LockRefused(code)
        if response.status_code != 200:
            raise OperationsUnavailable(str(response.status_code))

    async def lock(self, visit_id: str, report_id: str, version: int) -> None:
        """Lock the visit's boards for this report version (W17-8). Idempotent."""
        await self._lock_call("lock", visit_id, report_id, version)

    async def unlock(self, visit_id: str, report_id: str, version: int) -> None:
        """Open the boards again. Does nothing if another version holds the lock."""
        await self._lock_call("unlock", visit_id, report_id, version)

    async def visit_facts(self, visit_id: str) -> dict[str, Any] | None:
        """The visit, its request, its stations and their boards, for a draft report (W16-2).
        None when operations does not know the visit."""
        try:
            response = await self._http.get(
                f"{self._base}/internal/visits/{visit_id}/report-facts",
                headers=await self._tokens.headers(), timeout=30,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise OperationsUnavailable() from e
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise OperationsUnavailable(str(response.status_code))
        facts: dict[str, Any] = response.json()
        return facts

    async def client_report_facts(self, client_report_id: str) -> dict[str, Any] | None:
        """A client's submitted online-form report: its text, stations and pictures (W18-10).
        None when operations does not know it (or it is not a submitted form)."""
        try:
            response = await self._http.get(
                f"{self._base}/internal/client-reports/{client_report_id}",
                headers=await self._tokens.headers(), timeout=30,
            )
        except (httpx.HTTPError, ConnectionError) as e:
            raise OperationsUnavailable() from e
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise OperationsUnavailable(str(response.status_code))
        facts: dict[str, Any] = response.json()
        return facts
