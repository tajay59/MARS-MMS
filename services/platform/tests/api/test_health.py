import httpx
import pytest

from app.config import Settings
from app.main import create_app


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_health_and_ready_and_metrics():
    async def ok() -> bool:
        return True

    app = create_app(Settings(), ready_checks={"mongo": ok})
    async with client(app) as c:
        assert (await c.get("/health")).status_code == 200
        assert (await c.get("/ready")).status_code == 200
        assert (await c.get("/metrics")).status_code == 200


async def test_not_ready_when_a_dependency_is_down():
    async def down() -> bool:
        return False

    app = create_app(Settings(), ready_checks={"redis": down})
    async with client(app) as c:
        assert (await c.get("/ready")).status_code == 503


@pytest.mark.parametrize(("env", "expected"), [("local", 200), ("production", 404)])
async def test_openapi_is_disabled_in_production(env, expected):
    app = create_app(Settings(environment=env, smtp_security="starttls"), ready_checks={})
    async with client(app) as c:
        assert (await c.get("/docs")).status_code == expected


def test_production_refuses_an_unencrypted_relay():
    with pytest.raises(ValueError, match="PLATFORM_SMTP_SECURITY"):
        Settings(environment="production", smtp_security="none")
