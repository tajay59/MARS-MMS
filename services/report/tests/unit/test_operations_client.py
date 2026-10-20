"""The call to operations' `/internal/labels` (rule 1: report never reads its database)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.repo.operations import OperationsClient, OperationsUnavailable


class FakeTokens:
    async def headers(self, request_id: str | None = None) -> dict[str, str]:
        return {"Authorization": "Bearer service-token", "X-Request-ID": request_id or ""}


def client(handler) -> OperationsClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OperationsClient("http://operations:8000/", FakeTokens(), http)  # type: ignore[arg-type]


async def test_it_posts_the_ids_with_a_service_token_and_reads_the_labels():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{
            "station_id": "s1", "code": "C1", "name": "One", "org_name": "Org",
            "qr_token": "tok", "country": "JM",
        }])

    [label] = await client(handler).labels(["s1"], "req-1")
    assert (label.code, label.qr_token, label.org_name) == ("C1", "tok", "Org")
    [request] = seen
    assert str(request.url) == "http://operations:8000/internal/labels"
    assert json.loads(request.content) == {"station_ids": ["s1"]}
    assert request.headers["authorization"] == "Bearer service-token"


@pytest.mark.parametrize("status", [401, 404, 500, 503])
async def test_an_error_answer_means_unavailable(status):
    with pytest.raises(OperationsUnavailable):
        await client(lambda request: httpx.Response(status)).labels(["s1"])


async def test_a_dead_connection_means_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(OperationsUnavailable):
        await client(handler).labels(["s1"])
