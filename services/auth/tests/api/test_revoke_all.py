"""`python -m app.cli revoke-all-sessions` (W20-9, finding F18): after a restore from backup every
session ends, so a user disabled since the dump cannot come back with an old token or cookie."""

from __future__ import annotations

import pytest
from mms_common.auth import revocation

from app import cli
from tests.conftest import PASSWORD

COOKIE = "__Secure-mms_refresh"


@pytest.fixture
def operator(auth, monkeypatch):
    """The command reads its settings from the environment, as it does in the container."""
    s = auth.settings
    monkeypatch.setenv("AUTH_MONGO_URI", s.mongo_uri)
    monkeypatch.setenv("AUTH_MONGO_DB", s.mongo_db)
    monkeypatch.setenv("AUTH_REDIS_URL", s.redis_url)
    return auth


async def sign_in(auth, email="tech1@example.org"):
    client = auth.client()
    r = await auth.login(email, PASSWORD, client)
    assert r.status_code == 200, r.text
    return client, r.json()["access_token"]


@pytest.mark.req("AUTH-11")
async def test_every_session_ends_and_signing_in_again_works(operator):
    auth = operator
    phone, phone_token = await sign_in(auth)
    laptop, _ = await sign_in(auth, "admin@example.org")
    mine = {"Authorization": f"Bearer {phone_token}"}
    assert (await auth.http.get("/api/v1/auth/me", headers=mine)).status_code == 200

    assert await cli.revoke_all_sessions("restore") == 0

    # The access token is refused at once, and neither cookie can be refreshed
    assert (await auth.http.get("/api/v1/auth/me", headers=mine)).status_code == 401
    assert (await phone.post("/api/v1/auth/refresh")).status_code == 401
    assert (await laptop.post("/api/v1/auth/refresh")).status_code == 401
    assert await auth.db["refresh_tokens"].count_documents({"revoked_at": None}) == 0

    # A new sign-in after the moment of the revocation works
    auth.clock.advance(seconds=5)
    _, fresh = await sign_in(auth)
    ok = await auth.http.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh}"})
    assert ok.status_code == 200


@pytest.mark.req("AUD-1")
async def test_the_revocation_is_recorded_with_how_many_sessions_it_ended(operator):
    auth = operator
    await sign_in(auth)
    await sign_in(auth, "admin@example.org")
    await cli.revoke_all_sessions("key_rotation")
    [event] = await auth.outbox("auth.sessions_revoked")
    assert event.data == {"reason": "key_rotation", "count": 2}
    assert event.actor.name == "auth cli"


async def test_one_key_ends_the_tokens_of_every_service(auth):
    """Services other than auth only read Redis: the single key is what they check."""
    token_at = int(auth.clock.now().timestamp())
    assert not await revocation.is_revoked(auth.redis, user_id="u1", org_id=None, issued_at=token_at)
    await revocation.revoke_all(auth.redis, auth.clock.now())
    assert await revocation.is_revoked(auth.redis, user_id="u1", org_id=None, issued_at=token_at)
    assert not await revocation.is_revoked(
        auth.redis, user_id="u1", org_id=None, issued_at=token_at + 1
    )
