"""Login, refresh rotation with the 30 s grace, reuse detection and logout (TRD §6.1, §6.1.1;
TP "Refresh race", "Security")."""

import asyncio

import pytest
from mms_common.auth.tokens import ACCESS_AUDIENCE, verify
from mms_common.testing.seed import ORG_A, SEED_USERS

from tests.conftest import PASSWORD

COOKIE = "__Secure-mms_refresh"


def set_cookie(response) -> str:
    return response.headers.get("set-cookie", "")


@pytest.mark.req("AUTH-7")
async def test_login_returns_an_access_token_and_a_locked_down_refresh_cookie(auth):
    r = await auth.login("tech1@example.org")
    assert r.status_code == 200, r.text
    body = r.json()
    claims = await verify(body["access_token"], auth.issuer.keys, clock=auth.clock,
                          audience=ACCESS_AUDIENCE)
    assert claims["sub"] == SEED_USERS["tech1"].id
    assert claims["roles"] == ["technician"]
    assert claims["name"] == "Tech 1"
    assert body["expires_in"] == 900
    assert body["user"]["email"] == "tech1@example.org"
    assert "password_hash" not in body["user"]
    cookie = set_cookie(r)
    for part in (f"{COOKIE}=", "HttpOnly", "Secure", "SameSite=strict", "Path=/api/v1/auth",
                 "Max-Age=2592000"):
        assert part.lower() in cookie.lower(), cookie
    assert r.headers["cache-control"] == "no-store"
    # The PWA keeps refresh_expires_at as offline_until for the PIN session (AUTH-12).
    assert body["refresh_expires_at"].startswith(str((auth.clock.now()).year))


@pytest.mark.req("AUD-1")
async def test_login_is_audited_with_ip_and_device(auth):
    await auth.http.post(
        "/api/v1/auth/login",
        json={"email": "tech1@example.org", "password": PASSWORD},
        headers={"X-Real-IP": "203.0.113.9", "User-Agent": "Phone", "X-Device-ID": "dev-1"},
    )
    [event] = await auth.outbox("auth.login_succeeded")
    assert event.actor.user_id == SEED_USERS["tech1"].id
    assert (event.actor.ip, event.actor.user_agent, event.actor.device_id) == (
        "203.0.113.9", "Phone", "dev-1")
    assert event.key == SEED_USERS["tech1"].id
    assert event.correlation_id


@pytest.mark.req("AUTH-10")
async def test_wrong_password_and_unknown_email_look_the_same(auth):
    wrong = await auth.login("tech1@example.org", "not the password")
    unknown = await auth.login("nobody@example.org", "not the password")
    assert wrong.status_code == unknown.status_code == 401
    strip = lambda r: {k: v for k, v in r.json().items() if k != "request_id"}  # noqa: E731
    assert strip(wrong) == strip(unknown)
    assert strip(wrong)["detail"] == "Email or password is incorrect"
    reasons = [e.data["reason"] for e in await auth.outbox("auth.login_failed")]
    assert reasons == ["wrong_password", "unknown_email"]


@pytest.mark.req("AUTH-10")
@pytest.mark.parametrize("email", ["tech1@example.org", "nobody@example.org"])
async def test_five_failures_lock_the_email_for_15_minutes(auth, email):
    for _ in range(5):
        assert (await auth.login(email, "wrong password!")).status_code == 401
    locked = await auth.login(email, PASSWORD)
    assert locked.status_code == 429
    assert locked.json()["detail"] == "Too many attempts, try again in 15 minutes"
    if email.startswith("tech1"):
        await auth.redis.delete(*[k async for k in auth.redis.scan_iter("auth:login-fail:*")])
        assert (await auth.login(email)).status_code == 200


@pytest.mark.req("AUTH-2")
async def test_pending_account_gets_account_pending(auth):
    await auth.add_user(email="new@example.org", status="pending", org_id=None)
    r = await auth.login("new@example.org")
    assert r.status_code == 403
    assert r.json()["code"] == "account_pending"


@pytest.mark.req("ORG-4")
@pytest.mark.parametrize("status", ["rejected", "disabled"])
async def test_blocked_accounts_cannot_sign_in(auth, status):
    await auth.add_user(email="x@example.org", status=status)
    r = await auth.login("x@example.org")
    assert r.status_code == 403
    assert r.json()["code"] == "account_blocked"
    assert r.json()["detail"] == "This account cannot sign in. Contact the service desk."


@pytest.mark.req("ORG-4")
async def test_users_of_a_deactivated_org_cannot_sign_in(auth):
    await auth.db["organizations"].update_one({"_id": ORG_A}, {"$set": {"status": "inactive"}})
    r = await auth.login("client.a1@example.org")
    assert (r.status_code, r.json()["code"]) == (403, "account_blocked")
    [failed] = await auth.outbox("auth.login_failed")
    assert failed.data["reason"] == "org_inactive"


async def test_email_is_case_insensitive(auth):
    assert (await auth.login("  Tech1@Example.ORG ")).status_code == 200


# --- Refresh ---------------------------------------------------------------------------------


async def refresh(client):
    return await client.post("/api/v1/auth/refresh")


@pytest.mark.req("AUTH-12")
async def test_refresh_rotates_the_cookie(auth):
    await auth.login("tech1@example.org")
    first = auth.http.cookies.get(COOKIE)
    r = await refresh(auth.http)
    assert r.status_code == 200, r.text
    assert auth.http.cookies.get(COOKIE) not in (None, first)
    assert r.json()["user"]["id"] == SEED_USERS["tech1"].id


async def test_refresh_without_a_cookie_is_401(auth):
    r = await refresh(auth.http)
    assert (r.status_code, r.json()["reason"]) == (401, "no_session")


@pytest.mark.req("AUTH-12")
async def test_two_tabs_and_the_worker_refreshing_together_stay_signed_in(auth):
    """TP "Refresh race": concurrent refreshes with the same cookie all succeed, end on the
    same successor, and the family is not revoked."""
    await auth.login("tech1@example.org")
    raw = auth.http.cookies.get(COOKIE)
    tabs = [auth.client() for _ in range(3)]
    for tab in tabs:
        tab.cookies.set(COOKIE, raw, domain="mms.test", path="/api/v1/auth")
    results = await asyncio.gather(*(refresh(tab) for tab in tabs))
    assert [r.status_code for r in results] == [200, 200, 200], [r.text for r in results]
    successors = {tab.cookies.get(COOKIE) for tab in tabs}
    assert len(successors) == 1 and raw not in successors
    # The shared successor keeps working.
    assert (await refresh(tabs[0])).status_code == 200
    assert await auth.outbox("auth.token_reuse_detected") == []


@pytest.mark.req("AUTH-12")
async def test_grace_returns_the_same_successor_for_30_seconds(auth):
    await auth.login("tech1@example.org")
    raw = auth.http.cookies.get(COOKIE)
    assert (await refresh(auth.http)).status_code == 200
    successor = auth.http.cookies.get(COOKIE)
    late = auth.client()
    late.cookies.set(COOKIE, raw, domain="mms.test", path="/api/v1/auth")
    auth.clock.advance(seconds=29)
    assert (await refresh(late)).status_code == 200
    assert late.cookies.get(COOKIE) == successor


@pytest.mark.req("NFR-6")
async def test_reuse_after_the_grace_window_revokes_the_whole_family(auth):
    await auth.login("tech1@example.org")
    stolen = auth.http.cookies.get(COOKIE)
    assert (await refresh(auth.http)).status_code == 200
    auth.clock.advance(seconds=31)
    attacker = auth.client()
    attacker.cookies.set(COOKIE, stolen, domain="mms.test", path="/api/v1/auth")
    r = await refresh(attacker)
    assert (r.status_code, r.json()["reason"]) == (401, "session_revoked")
    assert 'max-age=0' in set_cookie(r).lower()  # cookie cleared on the error response
    # The legitimate holder of the successor is logged out too.
    r = await refresh(auth.http)
    assert (r.status_code, r.json()["reason"]) == (401, "session_expired")
    [event] = await auth.outbox("auth.token_reuse_detected")
    assert event.data["user_id"] == SEED_USERS["tech1"].id


async def test_refresh_expires_30_days_after_the_last_use(auth):
    await auth.login("tech1@example.org")
    auth.clock.advance(days=29)
    assert (await refresh(auth.http)).status_code == 200  # sliding window
    auth.clock.advance(days=29)
    assert (await refresh(auth.http)).status_code == 200
    auth.clock.advance(days=31)
    r = await refresh(auth.http)
    assert (r.status_code, r.json()["reason"]) == (401, "session_expired")


@pytest.mark.req("AUTH-11")
async def test_refresh_fails_once_the_user_is_disabled(auth):
    await auth.login("tech1@example.org")
    await auth.db["users"].update_one({"_id": SEED_USERS["tech1"].id},
                                      {"$set": {"status": "disabled"}})
    r = await refresh(auth.http)
    assert (r.status_code, r.json()["reason"]) == (401, "account_blocked")


@pytest.mark.req("AUD-1")
async def test_logout_revokes_the_session_and_is_audited(auth):
    await auth.login("tech1@example.org")
    r = await auth.http.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert auth.http.cookies.get(COOKIE) is None
    assert [e.data["user_id"] for e in await auth.outbox("auth.logout")] == [
        SEED_USERS["tech1"].id]


async def test_logout_with_a_stale_cookie_still_ends_the_family(auth):
    await auth.login("tech1@example.org")
    raw = auth.http.cookies.get(COOKIE)
    other = auth.client()
    other.cookies.set(COOKIE, raw, domain="mms.test", path="/api/v1/auth")
    assert (await other.post("/api/v1/auth/logout")).status_code == 204
    assert (await refresh(auth.http)).status_code == 401


async def test_logout_without_a_session_is_harmless(auth):
    assert (await auth.http.post("/api/v1/auth/logout")).status_code == 204
