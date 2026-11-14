"""Two-step sign-in (W22; AUTH-14): the code step, enrolment, recovery codes, the setup window,
the shared lock, and what is never stored, logged or returned (TRD §6.1.1; ASVS 2.2, 2.8)."""

from __future__ import annotations

import base64
import json

import pytest
from mms_common.testing.leak import find_leaks
from mms_common.testing.seed import ADMIN_MFA_TOTP_SECRET, SEED_USERS

from app.domain import totp
from app.repo import totp as totp_repo
from tests.conftest import PASSWORD, RECOVERY, SECRET, TOTP_KEY

STEP = "/api/v1/auth/login/totp"
ENROL = "/api/v1/auth/login/totp/enrol/confirm"
COOKIE = "__Secure-mms_refresh"
MFA_ID = SEED_USERS["admin_mfa"].id


def days_left(auth, when) -> int:
    """Whole days from the test clock to a time read back through the test's own Mongo client,
    which hands out naive UTC datetimes."""
    return (when.replace(tzinfo=auth.clock.now().tzinfo) - auth.clock.now()).days


async def challenge(auth, client=None) -> str:
    r = await auth.login_mfa(client=client)
    assert r.status_code == 200, r.text
    assert r.json()["mfa_required"] is True
    return r.json()["challenge"]


async def finish(auth, token: str, **factor):
    return await auth.http.post(STEP, json={"challenge": token, **factor})


# --- The code step ---------------------------------------------------------------------------


@pytest.mark.req("AUTH-14")
async def test_a_correct_password_alone_is_not_a_session(auth):
    r = await auth.login_mfa()
    body = r.json()
    assert r.status_code == 200
    assert set(body) == {"mfa_required", "enrol", "challenge", "expires_in"}
    assert body["enrol"] is False and body["expires_in"] == 300
    assert "set-cookie" not in r.headers
    assert await auth.db["refresh_tokens"].count_documents({}) == 0
    assert await auth.outbox("auth.login_succeeded") == []


@pytest.mark.req("AUTH-14")
async def test_a_correct_code_finishes_the_sign_in(auth):
    r = await finish(auth, await challenge(auth), code=auth.code())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["totp_enabled"] is True and body["user"]["recovery_codes_left"] == 10
    assert body["recovery_codes"] is None
    assert COOKIE.lower() in r.headers["set-cookie"].lower()
    mine = {"Authorization": f"Bearer {body['access_token']}"}
    assert (await auth.http.get("/api/v1/auth/me", headers=mine)).status_code == 200
    [event] = await auth.outbox("auth.login_succeeded")
    assert event.data["mfa"] == "totp" and event.actor.user_id == MFA_ID
    assert (await auth.user("admin_mfa"))["last_login_at"] is not None


async def test_the_code_with_a_space_from_the_phone_keyboard_works(auth):
    code = auth.code()
    r = await finish(auth, await challenge(auth), code=f"{code[:3]} {code[3:]}")
    assert r.status_code == 200


@pytest.mark.req("AUTH-14")
async def test_an_old_app_is_told_to_reload_instead_of_getting_a_challenge(auth):
    r = await auth.login("admin.mfa@example.org")  # no supports_mfa
    assert r.status_code == 401
    assert r.json()["reason"] == "update_required"
    assert "set-cookie" not in r.headers
    assert await auth.db["refresh_tokens"].count_documents({}) == 0


@pytest.mark.req("AUTH-14")
async def test_a_wrong_code_says_only_that_it_is_incorrect_and_is_audited(auth):
    token = await challenge(auth)
    wrong = auth.code(steps=5)
    r = await finish(auth, token, code=wrong)
    assert (r.status_code, r.json()["reason"]) == (401, "invalid_code")
    assert r.json()["detail"] == "The code is incorrect"
    assert "set-cookie" not in r.headers
    [event] = await auth.outbox("auth.mfa_failed")
    assert event.data["reason"] == "wrong_code" and event.data["user_id"] == MFA_ID
    assert wrong not in json.dumps(event.data)
    # the same challenge still works with the right code: a typo is not a lockout
    assert (await finish(auth, token, code=auth.code())).status_code == 200


@pytest.mark.req("AUTH-14")
async def test_a_code_cannot_be_used_twice(auth):
    code = auth.code()
    assert (await finish(auth, await challenge(auth), code=code)).status_code == 200
    # a second sign-in with the same code, in the same 30 seconds
    r = await finish(auth, await challenge(auth), code=code)
    assert (r.status_code, r.json()["reason"]) == (401, "invalid_code")
    [event] = await auth.outbox("auth.mfa_failed")
    assert event.data["reason"] == "replayed_code"
    # the next step's code is fine
    auth.clock.advance(seconds=30)
    assert (await finish(auth, await challenge(auth), code=auth.code())).status_code == 200


@pytest.mark.req("AUTH-14")
async def test_a_challenge_is_used_once(auth):
    token = await challenge(auth)
    assert (await finish(auth, token, code=auth.code())).status_code == 200
    auth.clock.advance(seconds=30)
    r = await finish(auth, token, code=auth.code())
    assert (r.status_code, r.json()["reason"]) == (401, "invalid_challenge")


@pytest.mark.req("AUTH-14")
async def test_a_challenge_that_does_not_exist_or_expired_is_refused(auth):
    r = await finish(auth, "x" * 43, code="123456")
    assert (r.status_code, r.json()["reason"]) == (401, "invalid_challenge")
    token = await challenge(auth)
    await auth.redis.flushdb()  # what the five minutes do
    r = await finish(auth, token, code=auth.code())
    assert (r.status_code, r.json()["reason"]) == (401, "invalid_challenge")


@pytest.mark.req("AUTH-14")
async def test_five_wrong_codes_lock_the_account_for_the_password_too(auth):
    token = await challenge(auth)
    for _ in range(5):
        assert (await finish(auth, token, code=auth.code(steps=9))).status_code in (401, 429)
    # the lock is the one a wrong password uses (AUTH-10): the correct password and a correct
    # code are both refused for 15 minutes
    assert (await auth.login_mfa()).status_code == 429
    assert (await finish(auth, token, code=auth.code())).status_code in (401, 429)
    assert await auth.db["refresh_tokens"].count_documents({}) == 0


@pytest.mark.req("AUTH-14")
async def test_the_password_alone_never_resets_the_code_limit(auth):
    """Signing in with the right password between wrong codes must not clear the count."""
    for _ in range(5):
        token = await challenge(auth)
        await finish(auth, token, code=auth.code(steps=9))
    assert (await auth.login_mfa()).status_code == 429


@pytest.mark.req("AUTH-14")
async def test_a_challenge_is_bound_to_its_purpose(auth):
    await auth.add_user(email="late@example.org", roles=["admin"], org_id=None,
                        mfa_grace_until=auth.clock.now())
    enrol = (await auth.login_mfa("late@example.org")).json()
    assert enrol["enrol"] is True
    r = await finish(auth, enrol["challenge"], code=auth.code())
    assert (r.status_code, r.json()["reason"]) == (401, "invalid_challenge")
    verify = await challenge(auth)
    r = await auth.http.post("/api/v1/auth/login/totp/enrol/begin", json={"challenge": verify})
    assert (r.status_code, r.json()["reason"]) == (401, "invalid_challenge")


# --- Recovery codes --------------------------------------------------------------------------


@pytest.mark.req("AUTH-14")
async def test_a_recovery_code_signs_in_once_and_says_how_many_are_left(auth):
    r = await finish(auth, await challenge(auth), recovery_code=RECOVERY)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["recovery_codes_left"] == 9
    [event] = await auth.outbox("auth.recovery_code_used")
    assert event.data == {"user_id": MFA_ID, "remaining": 9}
    [ok] = await auth.outbox("auth.login_succeeded")
    assert ok.data["mfa"] == "recovery"
    again = await finish(auth, await challenge(auth), recovery_code=RECOVERY)
    assert (again.status_code, again.json()["reason"]) == (401, "invalid_code")
    assert (await auth.outbox("auth.mfa_failed"))[0].data["reason"] == "wrong_recovery_code"


async def test_a_recovery_code_is_accepted_however_it_is_typed(auth):
    r = await finish(auth, await challenge(auth), recovery_code=" abcde fghjk ")
    assert r.status_code == 200


@pytest.mark.req("AUTH-14")
async def test_another_users_recovery_code_does_not_open_this_challenge(auth):
    tech, headers = await staff(auth)
    _, codes = await opt_in(auth, tech, headers)
    r = await finish(auth, await challenge(auth), recovery_code=codes[0])
    assert (r.status_code, r.json()["reason"]) == (401, "invalid_code")


async def test_exactly_one_factor_is_required(auth):
    token = await challenge(auth)
    for body in ({}, {"code": "123456", "recovery_code": RECOVERY}):
        assert (await finish(auth, token, **body)).status_code == 422


# --- Refresh and disabled accounts -------------------------------------------------------------


@pytest.mark.req("AUTH-14")
async def test_refresh_never_asks_for_a_code(auth):
    assert (await finish(auth, await challenge(auth), code=auth.code())).status_code == 200
    r = await auth.http.post("/api/v1/auth/refresh")
    assert r.status_code == 200 and r.json()["user"]["totp_enabled"] is True


async def test_an_account_disabled_after_the_password_cannot_finish(auth):
    token = await challenge(auth)
    await auth.db["users"].update_one({"_id": MFA_ID}, {"$set": {"status": "disabled"}})
    r = await finish(auth, token, code=auth.code())
    assert (r.status_code, r.json()["code"]) == (403, "account_blocked")
    assert await auth.db["refresh_tokens"].count_documents({}) == 0


# --- The setup window and enrolment ------------------------------------------------------------


@pytest.mark.req("AUTH-14")
async def test_an_admin_without_a_second_factor_signs_in_and_is_told_to_set_one_up(auth):
    r = await auth.login("admin@example.org")
    assert r.status_code == 200, r.text
    assert r.json()["mfa_setup"] is not None
    stored = (await auth.user("admin"))["mfa_grace_until"]
    assert days_left(auth, stored) == 6  # seven days from now, to the second
    assert (await auth.login("tech1@example.org")).json()["mfa_setup"] is None
    # a later sign-in does not move the end of the window
    auth.clock.advance(days=3)
    await auth.login("admin@example.org")
    assert (await auth.user("admin"))["mfa_grace_until"] == stored


@pytest.mark.req("AUTH-14")
async def test_an_admin_already_signed_in_gets_the_window_at_their_next_refresh(auth):
    client = auth.client()
    await auth.login("admin@example.org", client=client)
    await auth.db["users"].update_one({"_id": SEED_USERS["admin"].id},
                                      {"$unset": {"mfa_grace_until": ""}})
    r = await client.post("/api/v1/auth/refresh")
    assert r.json()["mfa_setup"] is not None
    assert (await auth.user("admin"))["mfa_grace_until"] is not None


@pytest.mark.req("AUTH-14")
async def test_after_the_window_an_admin_signs_in_only_through_enrolment(auth):
    await auth.login("admin@example.org")  # starts the window
    auth.clock.advance(days=7, seconds=1)
    old = await auth.login("admin@example.org")  # an old app
    assert (old.status_code, old.json()["reason"]) == (401, "update_required")

    r = await auth.login_mfa("admin@example.org")
    assert r.status_code == 200 and r.json()["enrol"] is True
    assert "set-cookie" not in r.headers
    token = r.json()["challenge"]

    begin = await auth.http.post("/api/v1/auth/login/totp/enrol/begin", json={"challenge": token})
    assert begin.status_code == 200, begin.text
    secret = totp.from_base32(begin.json()["secret"])
    assert begin.json()["otpauth_uri"].startswith("otpauth://totp/MARS-MMS%3Aadmin%40example.org?")

    wrong = await auth.http.post(
        ENROL, json={"challenge": token, "code": auth.code(secret, steps=9)}
    )
    assert (wrong.status_code, wrong.json()["reason"]) == (401, "invalid_code")
    done = await auth.http.post(ENROL, json={"challenge": token, "code": auth.code(secret)})
    assert done.status_code == 200, done.text
    body = done.json()
    assert len(body["recovery_codes"]) == 10 and body["user"]["totp_enabled"] is True
    assert body["mfa_setup"] is None and COOKIE.lower() in done.headers["set-cookie"].lower()
    [enrolled] = await auth.outbox("auth.totp_enrolled")
    assert enrolled.data == {"user_id": SEED_USERS["admin"].id}

    # the confirming code is spent: the next sign-in needs the next step's code
    again = (await auth.login_mfa("admin@example.org")).json()
    assert again["enrol"] is False
    replay = await finish(auth, again["challenge"], code=auth.code(secret))
    assert replay.status_code == 401
    auth.clock.advance(seconds=30)
    ok = await finish(auth, again["challenge"], code=auth.code(secret))
    assert ok.status_code == 200, ok.text


async def test_enrolment_at_sign_in_needs_the_password_first(auth):
    r = await auth.http.post("/api/v1/auth/login/totp/enrol/begin", json={"challenge": "y" * 43})
    assert r.status_code == 401


# --- Opting in, signed in ----------------------------------------------------------------------


async def staff(auth, email="tech1@example.org"):
    client = auth.client()
    r = await auth.login(email, client=client)
    return client, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def opt_in(auth, client, headers, password=PASSWORD):
    setup = await client.post("/api/v1/auth/me/totp/begin", json={"password": password},
                              headers=headers)
    assert setup.status_code == 200, setup.text
    secret = totp.from_base32(setup.json()["secret"])
    done = await client.post("/api/v1/auth/me/totp/confirm", json={"code": auth.code(secret)},
                             headers=headers)
    assert done.status_code == 200, done.text
    return secret, done.json()["recovery_codes"]


@pytest.mark.req("AUTH-14")
async def test_a_technician_can_opt_in_and_then_signs_in_with_a_code(auth):
    client, headers = await staff(auth)
    other, _ = await staff(auth)  # a second device
    secret, codes = await opt_in(auth, client, headers)
    assert len(codes) == 10
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["totp_enabled"] is True and me["recovery_codes_left"] == 10
    # enabling does not end the other sessions
    assert (await other.post("/api/v1/auth/refresh")).status_code == 200
    r = await auth.login_mfa("tech1@example.org")
    assert r.json()["enrol"] is False
    auth.clock.advance(seconds=30)
    done = await finish(auth, r.json()["challenge"], code=auth.code(secret))
    assert done.status_code == 200, done.text
    assert len(await auth.outbox("auth.totp_enrolled")) == 1


async def test_a_viewer_can_manage_their_own(auth):
    client, headers = await staff(auth, "viewer@example.org")
    await opt_in(auth, client, headers)
    assert (await auth.user("viewer"))["totp"]["enabled_at"] is not None


@pytest.mark.req("AUTH-14")
async def test_enrolment_needs_the_password_and_a_code_from_the_app(auth):
    client, headers = await staff(auth)
    bad = await client.post("/api/v1/auth/me/totp/begin", json={"password": "nope nope nope"},
                            headers=headers)
    assert (bad.status_code, bad.json()["errors"][0]["code"]) == (422, "wrong_password")
    setup = await client.post("/api/v1/auth/me/totp/begin", json={"password": PASSWORD},
                              headers=headers)
    secret = totp.from_base32(setup.json()["secret"])
    wrong = await client.post("/api/v1/auth/me/totp/confirm",
                              json={"code": auth.code(secret, steps=9)}, headers=headers)
    assert (wrong.status_code, wrong.json()["errors"][0]["code"]) == (422, "wrong_code")
    assert not (await auth.user("tech1")).get("totp")
    # nothing started: a confirm with no begin says to start again
    fresh, fresh_headers = await staff(auth, "tech2@example.org")
    none = await fresh.post("/api/v1/auth/me/totp/confirm", json={"code": "123456"},
                            headers=fresh_headers)
    assert none.json()["errors"][0]["code"] == "setup_expired"


async def test_it_cannot_be_started_twice(auth):
    client, headers = await staff(auth)
    await opt_in(auth, client, headers)
    again = await client.post("/api/v1/auth/me/totp/begin", json={"password": PASSWORD},
                              headers=headers)
    assert (again.status_code, again.json()["code"]) == (409, "totp_enabled")


@pytest.mark.req("AUTH-14")
async def test_regenerating_recovery_codes_replaces_every_old_one(auth):
    client, headers = await staff(auth)
    secret, old = await opt_in(auth, client, headers)
    auth.clock.advance(seconds=30)
    body = {"password": PASSWORD, "code": auth.code(secret)}
    r = await client.post("/api/v1/auth/me/totp/recovery-codes", json=body, headers=headers)
    assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10
    assert set(r.json()["recovery_codes"]).isdisjoint(old)
    assert len(await auth.outbox("auth.recovery_codes_regenerated")) == 1
    # an old code no longer signs in
    token = (await auth.login_mfa("tech1@example.org")).json()["challenge"]
    assert (await finish(auth, token, recovery_code=old[0])).status_code == 401
    # and without a current code, no new ones
    nope = await client.post("/api/v1/auth/me/totp/recovery-codes",
                             json={"password": PASSWORD, "code": "000000"}, headers=headers)
    assert nope.status_code == 422


@pytest.mark.req("AUTH-14")
async def test_staff_who_opted_in_can_turn_it_off_and_other_devices_sign_in_again(auth):
    client, headers = await staff(auth)
    other, _ = await staff(auth)
    secret, _ = await opt_in(auth, client, headers)
    auth.clock.advance(seconds=30)
    r = await client.request("DELETE", "/api/v1/auth/me/totp", headers=headers,
                             json={"password": PASSWORD, "code": auth.code(secret)})
    assert r.status_code == 204, r.text
    assert not (await auth.user("tech1")).get("totp")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200  # this device stays
    assert (await other.post("/api/v1/auth/refresh")).status_code == 401
    assert len(await auth.outbox("auth.totp_disabled")) == 1
    assert (await auth.login("tech1@example.org")).status_code == 200  # a password again


@pytest.mark.req("AUTH-14")
async def test_a_role_that_requires_it_cannot_turn_it_off(auth):
    client = auth.client()
    token = (await finish(auth, await challenge(auth, client), code=auth.code())).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    auth.clock.advance(seconds=30)
    r = await client.request("DELETE", "/api/v1/auth/me/totp", headers=headers,
                             json={"password": PASSWORD, "code": auth.code()})
    assert (r.status_code, r.json()["code"]) == (409, "totp_required")
    assert (await auth.user("admin_mfa"))["totp"] is not None


async def test_a_client_cannot_opt_in(auth):
    client = auth.client()
    r = await auth.login("client.a1@example.org", client=client)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.post("/api/v1/auth/me/totp/begin", json={"password": PASSWORD},
                              headers=headers)).status_code == 403
    assert r.json()["mfa_setup"] is None


# --- A role change starts the window -----------------------------------------------------------


@pytest.mark.req("AUTH-14")
async def test_becoming_an_admin_starts_the_setup_window(auth):
    tech = SEED_USERS["tech2"]
    r = await auth.http.patch(
        f"/api/v1/users/{tech.id}", headers=auth.bearer("admin"),
        json={"version": 1, "roles": ["admin", "technician"]},
    )
    assert r.status_code == 200, r.text
    assert (await auth.user("tech2"))["mfa_grace_until"] is not None
    [event] = await auth.outbox("user.updated")
    assert "mfa_grace_until" not in event.data["changed_fields"]
    assert "roles" in event.data["changed_fields"]
    assert (await auth.login("tech2@example.org")).json()["mfa_setup"] is not None


# --- Lost phone: an admin resets it ------------------------------------------------------------


@pytest.mark.req("AUTH-14")
async def test_another_admin_resets_a_lost_phone_and_their_sessions_end(auth):
    client = auth.client()
    assert (await finish(auth, await challenge(auth, client), code=auth.code())).status_code == 200
    r = await auth.http.post(f"/api/v1/users/{MFA_ID}/totp/reset", headers=auth.bearer("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["totp_enabled"] is False
    stored = await auth.user("admin_mfa")
    assert not stored.get("totp") and stored["recovery_codes"] == []
    assert days_left(auth, stored["mfa_grace_until"]) == 6  # a full new window
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    [event] = await auth.outbox("auth.totp_reset")
    assert event.data == {"user_id": MFA_ID, "via": "admin"}
    assert event.actor.user_id == SEED_USERS["admin"].id
    # they sign in with the password and are asked to set it up again
    login = await auth.login_mfa("admin.mfa@example.org")
    assert login.status_code == 200 and login.json()["mfa_setup"] is not None


@pytest.mark.req("AUTH-14")
async def test_an_admin_cannot_reset_their_own_and_cannot_reset_nothing(auth):
    own = await auth.http.post(f"/api/v1/users/{SEED_USERS['admin'].id}/totp/reset",
                               headers=auth.bearer("admin"))
    assert (own.status_code, own.json()["code"]) == (409, "cannot_reset_self")
    none = await auth.http.post(f"/api/v1/users/{SEED_USERS['tech1'].id}/totp/reset",
                                headers=auth.bearer("admin"))
    assert (none.status_code, none.json()["code"]) == (409, "totp_not_enabled")
    assert await auth.outbox("auth.totp_reset") == []


async def test_a_technician_cannot_reset_anyones(auth):
    r = await auth.http.post(f"/api/v1/users/{MFA_ID}/totp/reset", headers=auth.bearer("tech1"))
    assert r.status_code == 403


async def test_the_server_command_does_the_same(auth, monkeypatch):
    from app import cli

    s = auth.settings
    monkeypatch.setenv("AUTH_MONGO_URI", s.mongo_uri)
    monkeypatch.setenv("AUTH_MONGO_DB", s.mongo_db)
    monkeypatch.setenv("AUTH_REDIS_URL", s.redis_url)
    client = auth.client()
    assert (await finish(auth, await challenge(auth, client), code=auth.code())).status_code == 200
    assert await cli.reset_totp("Admin.MFA@example.org") == 0
    assert not (await auth.user("admin_mfa")).get("totp")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    [event] = await auth.outbox("auth.totp_reset")
    assert event.data["via"] == "cli" and event.actor.name == "auth cli"
    assert await cli.reset_totp("admin.mfa@example.org") == 1  # nothing left to reset
    assert await cli.reset_totp("nobody@example.org") == 1


# --- What is never stored, returned or logged ---------------------------------------------------


@pytest.mark.req("AUTH-14")
async def test_the_secret_is_sealed_at_rest_and_bound_to_its_user(auth):
    stored = (await auth.user("admin_mfa"))["totp"]["secret_enc"]
    assert ADMIN_MFA_TOTP_SECRET not in stored
    assert base64.b64encode(SECRET).decode() not in stored
    key = base64.b64decode(TOTP_KEY)
    assert totp_repo.unseal(key, stored, MFA_ID) == SECRET
    assert totp_repo.unseal(key, stored, SEED_USERS["admin"].id) is None  # moved to another user
    assert totp_repo.unseal(bytes(32), stored, MFA_ID) is None  # another key


@pytest.mark.req("AUD-1")
async def test_no_event_holds_a_secret_a_code_or_a_hash(auth):
    client, headers = await staff(auth)
    secret, codes = await opt_in(auth, client, headers)
    await finish(auth, await challenge(auth), recovery_code=RECOVERY)
    await finish(auth, await challenge(auth), code=auth.code(steps=9))
    everything = json.dumps([e.model_dump(mode="json") for e in await auth.outbox()])
    for forbidden in [totp.to_base32(secret), ADMIN_MFA_TOTP_SECRET, RECOVERY, *codes,
                      "secret_enc", "recovery_codes", "last_step"]:
        assert forbidden not in everything, forbidden
    users_event = json.dumps([e.data for e in await auth.outbox("user.updated")])
    assert "totp" not in users_event


async def test_what_the_api_returns_about_a_user_has_no_second_factor_fields(auth):
    me = await auth.http.get("/api/v1/auth/me", headers=auth.bearer("admin_mfa"))
    assert find_leaks(me.json(), client=False) == []
    assert set(me.json()) >= {"totp_enabled", "recovery_codes_left"}
    listing = await auth.http.get("/api/v1/users", headers=auth.bearer("admin"))
    assert find_leaks(listing.json(), client=False) == []
    row = next(u for u in listing.json()["items"] if u["id"] == MFA_ID)
    assert row["totp_enabled"] is True
    one = await auth.http.get(f"/api/v1/users/{MFA_ID}", headers=auth.bearer("admin"))
    assert find_leaks(one.json(), client=False) == []


async def test_responses_that_carry_a_challenge_are_never_cached(auth):
    r = await auth.login_mfa()
    assert r.headers["cache-control"] == "no-store"
    bad = await finish(auth, r.json()["challenge"], code="000000")
    assert bad.headers["cache-control"] == "no-store"


async def test_the_seed_command_gives_admin_mfa_its_known_secret(auth, monkeypatch):
    from app import cli

    s = auth.settings
    monkeypatch.setenv("AUTH_MONGO_URI", s.mongo_uri)
    monkeypatch.setenv("AUTH_MONGO_DB", f"{s.mongo_db}_seed")
    monkeypatch.setenv("AUTH_REDIS_URL", s.redis_url)
    monkeypatch.setenv("AUTH_TOTP_KEY", TOTP_KEY)
    assert await cli.seed("a seed password 1") == 0
    stored = await auth.db.client[f"{s.mongo_db}_seed"]["users"].find_one({"_id": MFA_ID})
    sealed = stored["totp"]["secret_enc"]
    assert totp_repo.unseal(base64.b64decode(TOTP_KEY), sealed, MFA_ID) == SECRET
    assert len(stored["recovery_codes"]) == 10
    assert await cli.seed("a seed password 1") == 0  # idempotent
    await auth.db.client.drop_database(f"{s.mongo_db}_seed")
