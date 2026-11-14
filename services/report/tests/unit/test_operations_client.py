"""The call to operations' `/internal/labels` (rule 1: report never reads its database)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.repo.operations import LockRefused, OperationsClient, OperationsUnavailable


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


# --- the visit lock (W17-8) ----------------------------------------------------------------------


@pytest.mark.parametrize("action", ["lock", "unlock"])
async def test_lock_and_unlock_post_the_pair_with_a_service_token(action):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"visit_id": "v1", "locked": action == "lock",
                                         "visit_version": 7})

    await getattr(client(handler), action)("v1", "r1", 2)
    [request] = seen
    assert str(request.url) == f"http://operations:8000/internal/visits/v1/{action}"
    assert json.loads(request.content) == {"report_id": "r1", "report_version": 2}
    assert request.headers["authorization"] == "Bearer service-token"


async def test_a_refused_lock_carries_operations_code():
    body = {"code": "locked_by_another_report", "status": 409}
    with pytest.raises(LockRefused) as caught:
        await client(lambda request: httpx.Response(409, json=body)).lock("v1", "r1", 2)
    assert caught.value.code == "locked_by_another_report"
    with pytest.raises(LockRefused) as caught:
        await client(lambda request: httpx.Response(404, json={"code": "not_found"})).lock(
            "v1", "r1", 2)
    assert caught.value.code == "not_found"
    with pytest.raises(LockRefused) as caught:
        await client(lambda request: httpx.Response(409, text="not json")).unlock("v1", "r1", 2)
    assert caught.value.code == "refused"


@pytest.mark.parametrize("status", [401, 500, 503])
async def test_a_lock_error_answer_or_a_dead_connection_means_unavailable(status):
    with pytest.raises(OperationsUnavailable):
        await client(lambda request: httpx.Response(status)).lock("v1", "r1", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(OperationsUnavailable):
        await client(handler).unlock("v1", "r1", 2)
