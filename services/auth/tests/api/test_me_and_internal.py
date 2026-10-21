"""My profile (AUTH-13, D2) and the internal routes (TRD §6.1, §6.4, §8.6)."""

import base64

import pytest
from mms_common.auth.tokens import SERVICE_AUDIENCE, verify
from mms_common.ids import new_id
from mms_common.testing.seed import SEED_USERS

from tests.conftest import PASSWORD


@pytest.mark.req("AUTH-13")
async def test_edit_own_profile(auth):
    r = await auth.http.patch(
        "/api/v1/auth/me",
        json={"name": "Devon T", "phone": "876 555 0123", "time_zone": "America/Jamaica",
              "theme": "dark"},
        headers=auth.bearer("tech1"),
    )
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["theme"], r.json()["time_zone"]) == (
        "Devon T", "dark", "America/Jamaica")
    [event] = await auth.outbox("user.updated")
    assert event.data["changed_fields"] == ["name", "phone", "theme", "time_zone"]


async def test_viewer_may_edit_their_own_profile(auth):
    r = await auth.http.patch("/api/v1/auth/me", json={"theme": "light"},
                              headers=auth.bearer("viewer"))
    assert r.status_code == 200


async def test_unknown_time_zone_is_422(auth):
    r = await auth.http.patch("/api/v1/auth/me", json={"time_zone": "Mars/Olympus"},
                              headers=auth.bearer("tech1"))
    assert (r.status_code, r.json()["errors"][0]["code"]) == (422, "invalid_time_zone")


@pytest.mark.req("AUTH-13")
async def test_password_change_needs_the_current_one_and_signs_out_other_devices(auth):
    phone, laptop = auth.client(), auth.client()
    await auth.login("tech1@example.org", client=phone)
    signed_in = await auth.login("tech1@example.org", client=laptop)
    headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    wrong = await laptop.patch("/api/v1/auth/me", headers=headers,
                               json={"current_password": "nope", "new_password": "x" * 12})
    assert (wrong.status_code, wrong.json()["errors"][0]["code"]) == (422, "wrong_password")
    r = await laptop.patch("/api/v1/auth/me", headers=headers,
                           json={"current_password": PASSWORD, "new_password": "the new one!"})
    assert r.status_code == 200, r.text
    assert (await laptop.post("/api/v1/auth/refresh")).status_code == 200
    assert (await phone.post("/api/v1/auth/refresh")).status_code == 401


async def test_me_is_the_caller(auth):
    r = await auth.http.get("/api/v1/auth/me", headers=auth.bearer("client_a1"))
    assert (r.json()["id"], r.json()["org_id"]) == (SEED_USERS["client_a1"].id,
                                                    SEED_USERS["client_a1"].org_id)


# --- Internal --------------------------------------------------------------------------------


async def test_jwks_publishes_the_signing_key(auth):
    r = await auth.http.get("/.well-known/jwks.json")
    assert r.status_code == 200
    [key] = r.json()["keys"]
    assert key["kid"] == auth.issuer.signing.kid
    assert set(key) == {"kty", "crv", "x", "kid", "alg", "use"}  # public half only


def basic(name: str, secret: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"{name}:{secret}".encode()).decode()}


async def test_service_token_for_a_known_secret(auth):
    headers = basic("platform", "platform-secret")
    r = await auth.http.post("/internal/service-token", headers=headers)
    assert r.status_code == 200
    claims = await verify(r.json()["access_token"], auth.issuer.keys, clock=auth.clock,
                          audience=SERVICE_AUDIENCE)
    assert (claims["sub"], claims["roles"]) == ("platform", ["service"])
    assert r.json()["expires_in"] == 300


@pytest.mark.parametrize("headers", [basic("platform", "wrong"), basic("media", "x"), {},
                                     {"Authorization": "Basic !!!"}])
async def test_service_token_refused(auth, headers):
    assert (await auth.http.post("/internal/service-token", headers=headers)).status_code == 401


async def test_snapshot_pages_users_without_secrets(auth):
    token = auth.issuer.service_token("platform")
    r = await auth.http.get("/internal/snapshot/users?limit=5",
                            headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    first = r.json()
    assert len(first["items"]) == 5 and first["next_after"]
    assert set(first["items"][0]) == {"user_id", "email", "name", "roles", "status", "org_id",
                                      "aggregate_version"}
    rest = await auth.http.get(f"/internal/snapshot/users?after={first['next_after']}",
                               headers={"Authorization": f"Bearer {token}"})
    assert len(first["items"]) + len(rest.json()["items"]) == len(SEED_USERS)
    assert rest.json()["next_after"] is None


async def test_lookup_gives_operations_names_and_roles_only(auth):
    ids = [SEED_USERS["tech1"].id, SEED_USERS["admin"].id, new_id()]
    headers = {"Authorization": f"Bearer {auth.issuer.service_token('operations')}"}
    r = await auth.http.post("/internal/users/lookup", json={"ids": ids}, headers=headers)
    assert r.status_code == 200
    users = {u["id"]: u for u in r.json()["users"]}
    assert set(users) == {SEED_USERS["tech1"].id, SEED_USERS["admin"].id}  # unknown IDs left out
    assert set(users[SEED_USERS["tech1"].id]) == {"id", "name", "roles", "status"}
    assert users[SEED_USERS["tech1"].id]["roles"] == ["technician"]


async def test_lookup_is_for_operations_only(auth):
    other = {"Authorization": f"Bearer {auth.issuer.service_token('platform')}"}
    r = await auth.http.post("/internal/users/lookup", json={"ids": [new_id()]}, headers=other)
    assert r.status_code == 403
