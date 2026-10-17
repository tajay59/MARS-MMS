"""Registration, password reset and invitations (AFD J1, J2; AUTH-1, 2, 6, 8, 9)."""

import base64

import pytest
from mms_common.testing.seed import SEED_USERS

from tests.conftest import PASSWORD

NEW = {
    "name": "Maria Client", "email": "Maria@Agency.example.org", "phone": "876 555 0101",
    "password": "a long new password", "organization_name": "Agri Agency",
}


def platform_headers() -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(b"platform:platform-secret").decode()}


async def platform_token(auth) -> dict[str, str]:
    r = await auth.http.post("/internal/service-token", headers=platform_headers())
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def mint(auth, kind: str, link_id: str):
    return await auth.http.post("/internal/account-links", json={"kind": kind, "id": link_id},
                                headers=await platform_token(auth))


# --- Registration ----------------------------------------------------------------------------


@pytest.mark.req("AUTH-1")
@pytest.mark.req("AUTH-2")
async def test_register_creates_a_pending_client(auth):
    r = await auth.http.post("/api/v1/auth/register", json=NEW)
    assert (r.status_code, r.json()) == (202, {"status": "pending"})
    doc = await auth.db["users"].find_one({"email": "maria@agency.example.org"})
    assert doc["status"] == "pending" and doc["roles"] == ["client"] and doc["org_id"] is None
    assert doc["proposed_org_name"] == "Agri Agency"
    assert doc["password_hash"].startswith("$argon2id$")
    [event] = await auth.outbox("user.registered")
    assert event.data["proposed_org_name"] == "Agri Agency"
    assert "password" not in str(event.model_dump())
    assert (await auth.login("maria@agency.example.org", NEW["password"])).status_code == 403


@pytest.mark.req("AUTH-10")
async def test_registering_an_existing_email_looks_the_same_and_changes_nothing(auth):
    r = await auth.http.post("/api/v1/auth/register", json={**NEW, "email": "tech1@example.org"})
    assert (r.status_code, r.json()) == (202, {"status": "pending"})
    assert (await auth.user("tech1"))["status"] == "active"
    assert await auth.outbox() == []


@pytest.mark.req("AUTH-9")
@pytest.mark.parametrize(
    ("password", "code"),
    [("short pw", "password_too_short"), ("pwned password 1", "password_breached"),
     ("password123", "password_breached")],
)
async def test_weak_passwords_get_an_inline_field_error(auth, password, code):
    r = await auth.http.post("/api/v1/auth/register", json={**NEW, "password": password})
    assert r.status_code == 422
    [error] = r.json()["errors"]
    assert (error["loc"], error["code"]) == (["body", "password"], code)
    assert password not in r.text  # never echoed


@pytest.mark.req("NFR-6")
@pytest.mark.parametrize("bad", [{"$ne": None}, {"$gt": ""}, ["a"]])
async def test_operators_in_fields_are_rejected(auth, bad):
    """Rule 12: typed values only."""
    r = await auth.http.post("/api/v1/auth/login", json={"email": bad, "password": bad})
    assert r.status_code == 422


async def test_unknown_fields_are_rejected(auth):
    r = await auth.http.post("/api/v1/auth/register", json={**NEW, "roles": ["admin"]})
    assert r.status_code == 422


# --- Password reset (J2) ---------------------------------------------------------------------


async def request_reset(auth, email="tech1@example.org"):
    return await auth.http.post("/api/v1/auth/password-reset/request", json={"email": email})


@pytest.mark.req("AUTH-8")
async def test_reset_request_always_answers_202(auth):
    for email in ("tech1@example.org", "nobody@example.org", "client.b1@example.org"):
        r = await request_reset(auth, email)
        assert (r.status_code, r.json()) == (202, {"status": "accepted"})
    events = await auth.outbox("auth.password_reset_requested")
    assert [e.data["user_id"] for e in events] == [SEED_USERS["tech1"].id,
                                                    SEED_USERS["client_b1"].id]
    for e in events:
        assert set(e.data) == {"user_id", "reset_id"}  # no token in the event


@pytest.mark.req("AUTH-8")
async def test_reset_flow_end_to_end(auth):
    signed_in = await auth.login("tech1@example.org")
    old_access = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    await request_reset(auth)
    [event] = await auth.outbox("auth.password_reset_requested")
    link = await mint(auth, "reset", event.data["reset_id"])
    assert link.status_code == 200, link.text
    assert link.json()["email"] == "tech1@example.org"
    url = link.json()["url"]
    assert url.startswith("https://mms.test/reset-password/")
    token = url.rsplit("/", 1)[1]

    auth.clock.advance(seconds=2)
    r = await auth.http.post("/api/v1/auth/password-reset/confirm",
                             json={"token": token, "password": "brand new password"})
    assert r.status_code == 204, r.text
    # Every session ends: the refresh cookie and the access token issued before.
    assert (await auth.http.post("/api/v1/auth/refresh")).status_code == 401
    assert (await auth.http.get("/api/v1/auth/me", headers=old_access)).status_code == 401
    auth.clock.advance(seconds=2)
    assert (await auth.login("tech1@example.org", PASSWORD)).status_code == 401
    assert (await auth.login("tech1@example.org", "brand new password")).status_code == 200
    # Single use.
    again = await auth.http.post("/api/v1/auth/password-reset/confirm",
                                 json={"token": token, "password": "another new password"})
    assert (again.status_code, again.json()["code"]) == (410, "link_expired")
    assert len(await auth.outbox("auth.password_reset")) == 1


@pytest.mark.req("AUTH-8")
async def test_reset_link_expires_after_an_hour(auth):
    await request_reset(auth)
    [event] = await auth.outbox("auth.password_reset_requested")
    token = (await mint(auth, "reset", event.data["reset_id"])).json()["url"].rsplit("/", 1)[1]
    auth.clock.advance(minutes=61)
    r = await auth.http.post("/api/v1/auth/password-reset/confirm",
                             json={"token": token, "password": "brand new password"})
    assert r.status_code == 410
    assert (await mint(auth, "reset", event.data["reset_id"])).status_code == 410


async def test_only_the_newest_link_works(auth):
    await request_reset(auth)
    [event] = await auth.outbox("auth.password_reset_requested")
    first = (await mint(auth, "reset", event.data["reset_id"])).json()["url"].rsplit("/", 1)[1]
    second = (await mint(auth, "reset", event.data["reset_id"])).json()["url"].rsplit("/", 1)[1]
    body = {"password": "brand new password"}
    r = await auth.http.post("/api/v1/auth/password-reset/confirm", json={**body, "token": first})
    assert r.status_code == 410
    r = await auth.http.post("/api/v1/auth/password-reset/confirm", json={**body, "token": second})
    assert r.status_code == 204


async def test_a_new_reset_request_supersedes_the_last(auth):
    await request_reset(auth)
    await request_reset(auth)
    first, second = await auth.outbox("auth.password_reset_requested")
    assert (await mint(auth, "reset", first.data["reset_id"])).status_code == 410
    assert (await mint(auth, "reset", second.data["reset_id"])).status_code == 200


async def test_reset_requests_are_limited_per_email(auth):
    for _ in range(5):
        await request_reset(auth)
    assert len(await auth.outbox("auth.password_reset_requested")) == 3


# --- Invitations (AUTH-6) -------------------------------------------------------------------


async def invite(auth, **body):
    payload = {"email": "staff@example.org", "name": "New Tech", "roles": ["technician"], **body}
    return await auth.http.post("/api/v1/users", json=payload, headers=auth.bearer("admin"))


@pytest.mark.req("AUTH-6")
async def test_invited_staff_sets_a_password_and_is_signed_in(auth):
    r = await invite(auth)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "invited"
    [event] = await auth.outbox("user.invited")
    assert event.actor.user_id == SEED_USERS["admin"].id
    link = await mint(auth, "invitation", event.data["invitation_id"])
    assert link.json()["url"].startswith("https://mms.test/invite/")
    token = link.json()["url"].rsplit("/", 1)[1]
    accepted = await auth.http.post("/api/v1/auth/invitations/accept",
                                    json={"token": token, "password": "a fine new password"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["user"]["status"] == "active"
    assert auth.http.cookies.get("__Secure-mms_refresh")
    again = await auth.http.post("/api/v1/auth/invitations/accept",
                                 json={"token": token, "password": "a fine new password"})
    assert again.status_code == 410


async def test_invited_user_with_an_expired_link_finishes_through_reset(auth):
    """AFD §7: "This link has expired" -> Send a new link -> /forgot-password."""
    await invite(auth)
    auth.clock.advance(days=8)
    await request_reset(auth, "staff@example.org")
    [event] = await auth.outbox("auth.password_reset_requested")
    token = (await mint(auth, "reset", event.data["reset_id"])).json()["url"].rsplit("/", 1)[1]
    r = await auth.http.post("/api/v1/auth/password-reset/confirm",
                             json={"token": token, "password": "a fine new password"})
    assert r.status_code == 204
    auth.clock.advance(seconds=2)
    assert (await auth.login("staff@example.org", "a fine new password")).status_code == 200


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"email": "tech1@example.org"}, 409, "email_taken"),
        ({"roles": ["client"]}, 422, "org_required"),
        ({"roles": ["client", "admin"], "org_id": SEED_USERS["client_a1"].org_id}, 422,
         "invalid_roles"),
        ({"org_id": SEED_USERS["client_a1"].org_id}, 422, "org_not_allowed"),
    ],
)
async def test_invitation_rules(auth, body, status, code):
    r = await invite(auth, **body)
    assert (r.status_code, r.json().get("code")) == (status, code)
