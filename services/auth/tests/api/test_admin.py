"""Approvals, users and organizations (AFD J1 steps 3-4; AUTH-3, AUTH-11, ORG-1, ORG-4)."""

import pytest
from mms_common.testing.leak import find_leaks
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS

ADMIN_ID = SEED_USERS["admin"].id


async def pending(auth, **fields):
    return await auth.add_user(email="maria@example.org", status="pending", org_id=None,
                               proposed_org_name="Agri Agency", **fields)


@pytest.mark.req("AUTH-3")
async def test_approve_with_an_existing_org(auth):
    user = await pending(auth)
    r = await auth.http.post(f"/api/v1/users/{user['_id']}/approve", json={"org_id": ORG_A},
                             headers=auth.bearer("admin"))
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["org_id"]) == ("active", ORG_A)
    [event] = await auth.outbox("user.approved")
    assert (event.data["org_id"], event.org_id, event.aggregate_version) == (ORG_A, ORG_A, 2)
    assert event.audit["before"]["status"] == "pending"
    assert event.audit["after"]["status"] == "active"
    assert "password_hash" not in str(event.audit)
    assert (await auth.login("maria@example.org")).status_code == 200


@pytest.mark.req("AUTH-3")
async def test_approve_creating_a_new_org(auth):
    user = await pending(auth)
    r = await auth.http.post(
        f"/api/v1/users/{user['_id']}/approve",
        json={"new_organization": {"name": "Agri Agency", "country": "JM"}},
        headers=auth.bearer("admin"),
    )
    assert r.status_code == 200, r.text
    types = [e.type for e in await auth.outbox()]
    assert types == ["org.created", "user.approved"]


@pytest.mark.req("AUTH-3")
async def test_reject_with_a_reason(auth):
    user = await pending(auth)
    r = await auth.http.post(f"/api/v1/users/{user['_id']}/reject",
                             json={"reason": "Not a client"}, headers=auth.bearer("admin"))
    assert (r.status_code, r.json()["status"]) == (200, "rejected")
    [event] = await auth.outbox("user.rejected")
    assert event.data["reason"] == "Not a client"
    assert (await auth.login("maria@example.org")).json()["code"] == "account_blocked"


async def test_only_pending_users_can_be_approved(auth):
    r = await auth.http.post(f"/api/v1/users/{SEED_USERS['tech1'].id}/approve",
                             json={"org_id": ORG_A}, headers=auth.bearer("admin"))
    assert (r.status_code, r.json()["code"]) == (409, "invalid_status")


async def test_list_users_filters(auth):
    await pending(auth)
    r = await auth.http.get("/api/v1/users?status=pending", headers=auth.bearer("admin"))
    assert [u["email"] for u in r.json()["items"]] == ["maria@example.org"]
    r = await auth.http.get(f"/api/v1/users?org_id={ORG_B}", headers=auth.bearer("admin"))
    assert [u["email"] for u in r.json()["items"]] == ["client.b1@example.org"]
    r = await auth.http.get("/api/v1/users?q=tech", headers=auth.bearer("admin"))
    assert {u["email"] for u in r.json()["items"]} == {
        "tech1@example.org", "tech2@example.org", "tech.admin@example.org"}
    page1 = await auth.http.get("/api/v1/users?limit=4", headers=auth.bearer("admin"))
    page2 = await auth.http.get(f"/api/v1/users?limit=4&after={page1.json()['next_after']}",
                                headers=auth.bearer("admin"))
    seen = [u["id"] for u in page1.json()["items"] + page2.json()["items"]]
    assert len(seen) == len(set(seen)) == 8


@pytest.mark.req("NFR-6")
@pytest.mark.parametrize("q", ['{"$ne": null}', ".*", "a)(b", "$where"])
async def test_search_text_is_never_an_operator(auth, q):
    """Rule 12: the search box is escaped, never a pattern or an operator."""
    r = await auth.http.get("/api/v1/users", params={"q": q}, headers=auth.bearer("admin"))
    assert r.status_code == 200
    assert r.json()["items"] == []


@pytest.mark.req("AUTH-11")
async def test_disabling_a_user_ends_every_session_at_once(auth):
    signed_in = await auth.login("tech1@example.org")
    access = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    tech = await auth.user("tech1")
    auth.clock.advance(seconds=1)
    r = await auth.http.patch(f"/api/v1/users/{tech['_id']}",
                              json={"version": tech["version"], "status": "disabled"},
                              headers=auth.bearer("admin"))
    assert (r.status_code, r.json()["status"]) == (200, "disabled")
    assert (await auth.http.get("/api/v1/auth/me", headers=access)).status_code == 401
    assert (await auth.http.post("/api/v1/auth/refresh")).status_code == 401
    [event] = await auth.outbox("user.disabled")
    assert event.audit["after"]["status"] == "disabled"


async def test_role_change_needs_a_fresh_sign_in(auth):
    tech = await auth.user("tech1")
    old = auth.bearer("tech1")
    auth.clock.advance(seconds=1)
    r = await auth.http.patch(f"/api/v1/users/{tech['_id']}",
                              json={"version": 1, "roles": ["technician", "admin"]},
                              headers=auth.bearer("admin"))
    assert r.json()["roles"] == ["admin", "technician"]
    assert (await auth.http.get("/api/v1/auth/me", headers=old)).status_code == 401
    [event] = await auth.outbox("user.updated")
    assert event.data["changed_fields"] == ["org_id", "roles"]


async def test_stale_version_is_409(auth):
    tech = await auth.user("tech1")
    r = await auth.http.patch(f"/api/v1/users/{tech['_id']}", json={"version": 7, "name": "X"},
                              headers=auth.bearer("admin"))
    assert (r.status_code, r.json()["code"]) == (409, "version_conflict")


async def test_admin_cannot_lock_themselves_out(auth):
    r = await auth.http.patch(f"/api/v1/users/{ADMIN_ID}",
                              json={"version": 1, "status": "disabled"},
                              headers=auth.bearer("admin"))
    assert (r.status_code, r.json()["code"]) == (409, "self_lockout")


# --- Organizations ---------------------------------------------------------------------------


@pytest.mark.req("ORG-1")
async def test_create_and_edit_an_org(auth):
    r = await auth.http.post("/api/v1/organizations",
                             json={"name": "Met Office", "country": "BB"},
                             headers=auth.bearer("admin"))
    assert r.status_code == 201, r.text
    org = r.json()
    dup = await auth.http.post("/api/v1/organizations",
                               json={"name": "  met   OFFICE ", "country": "BB"},
                               headers=auth.bearer("admin"))
    assert (dup.status_code, dup.json()["code"]) == (409, "org_name_taken")
    r = await auth.http.patch(f"/api/v1/organizations/{org['id']}",
                              json={"version": 1, "phone": "246 555 0100"},
                              headers=auth.bearer("admin"))
    assert (r.status_code, r.json()["version"]) == (200, 2)
    assert [e.type for e in await auth.outbox()] == ["org.created", "org.updated"]


@pytest.mark.req("ORG-4")
async def test_deactivating_an_org_signs_its_users_out_and_keeps_its_data(auth):
    client_token = auth.bearer("client_a1")
    auth.clock.advance(seconds=1)
    r = await auth.http.patch(f"/api/v1/organizations/{ORG_A}",
                              json={"version": 1, "status": "inactive"},
                              headers=auth.bearer("admin"))
    assert r.status_code == 200
    assert (await auth.http.get("/api/v1/auth/me", headers=client_token)).status_code == 401
    assert (await auth.login("client.a1@example.org")).status_code == 403
    assert await auth.db["users"].count_documents({"org_id": ORG_A}) == 3
    other_org = await auth.http.get("/api/v1/auth/me", headers=auth.bearer("client_b1"))
    assert other_org.status_code == 200


@pytest.mark.req("NFR-6")
async def test_client_sees_only_their_own_org(auth):
    """Rules 3 and 4: another org's record is 404, and lists hold only the own org."""
    own = await auth.http.get(f"/api/v1/organizations/{ORG_A}", headers=auth.bearer("client_a1"))
    assert own.status_code == 200
    other = await auth.http.get(f"/api/v1/organizations/{ORG_B}",
                                headers=auth.bearer("client_a1"))
    assert other.status_code == 404
    listing = await auth.http.get("/api/v1/organizations", headers=auth.bearer("client_a1"))
    assert [o["id"] for o in listing.json()["items"]] == [ORG_A]
    staff = await auth.http.get("/api/v1/organizations", headers=auth.bearer("viewer"))
    assert len(staff.json()["items"]) == 2


@pytest.mark.req("NFR-6")
async def test_client_responses_leak_nothing(auth):
    """TP client leak test: staff email and phone never reach a client."""
    own = frozenset({SEED_USERS["client_a1"].id, ORG_A})
    for path in ("/api/v1/auth/me", "/api/v1/organizations", f"/api/v1/organizations/{ORG_A}"):
        r = await auth.http.get(path, headers=auth.bearer("client_a1"))
        assert r.status_code == 200
        assert find_leaks(r.json(), own_ids=own) == [], path
    r = await auth.login("client.a1@example.org")
    assert find_leaks(r.json(), own_ids=own) == []


async def test_staff_responses_never_carry_secrets(auth):
    r = await auth.http.get("/api/v1/users", headers=auth.bearer("admin"))
    assert find_leaks(r.json(), client=False) == []
