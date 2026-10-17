import httpx
import pytest
from fastapi import FastAPI

from mms_common.errors import NotFound
from mms_common.ids import is_uuid7
from mms_common.web import install


def make(checks=None):
    app = FastAPI()
    install(app, checks)

    @app.get("/boom")
    async def boom():
        raise NotFound("No such station")

    @app.get("/n/{n}")
    async def n(n: int):
        return {"n": n}

    return app


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_request_id_is_generated_and_echoed():
    async with client(make()) as c:
        r = await c.get("/health")
    assert is_uuid7(r.headers["x-request-id"])


async def test_a_safe_incoming_request_id_is_kept_and_an_unsafe_one_replaced():
    async with client(make()) as c:
        good = await c.get("/health", headers={"X-Request-ID": "abc-123"})
        bad = await c.get("/health", headers={"X-Request-ID": "a b c"})
    assert good.headers["x-request-id"] == "abc-123"
    assert bad.headers["x-request-id"] != "a b c"


async def test_errors_are_problem_details_with_the_request_id():
    async with client(make()) as c:
        r = await c.get("/boom", headers={"X-Request-ID": "r-1"})
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "not_found" and r.json()["request_id"] == "r-1"


async def test_validation_errors_do_not_echo_input():
    async with client(make()) as c:
        r = await c.get("/n/secret-value")
    assert r.status_code == 422
    assert "secret-value" not in r.text


@pytest.mark.parametrize(("ok", "status"), [(True, 200), (False, 503)])
async def test_ready_reflects_dependencies(ok, status):
    async def check():
        return ok

    async with client(make({"mongo": check})) as c:
        r = await c.get("/ready")
    assert r.status_code == status and r.json()["checks"] == {"mongo": ok}


async def test_ready_survives_a_check_that_raises():
    async def check():
        raise ConnectionError

    async with client(make({"redis": check})) as c:
        r = await c.get("/ready")
    assert r.status_code == 503


async def test_metrics_and_health():
    async with client(make()) as c:
        assert (await c.get("/health")).json() == {"status": "ok"}
        assert (await c.get("/metrics")).status_code == 200
