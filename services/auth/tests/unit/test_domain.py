"""Domain rules: statuses, login outcome, roles, refresh decisions, sealing (no I/O)."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from mms_common.errors import Conflict, ValidationFailed

from app.domain import users as rules
from app.domain.passwords import Hasher, check_new_password
from app.domain.tokens import Refresh, decide, new_token, open_successor, seal_successor, token_hash

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)
GRACE = timedelta(seconds=30)


@pytest.mark.parametrize(
    ("status", "org", "outcome", "reason"),
    [
        ("active", None, rules.LoginOutcome.OK, None),
        ("active", "active", rules.LoginOutcome.OK, None),
        ("active", "inactive", rules.LoginOutcome.BLOCKED, "org_inactive"),
        ("pending", None, rules.LoginOutcome.PENDING, "pending"),
        ("rejected", None, rules.LoginOutcome.BLOCKED, "rejected"),
        ("disabled", "active", rules.LoginOutcome.BLOCKED, "disabled"),
        ("invited", None, rules.LoginOutcome.BLOCKED, "invited"),
    ],
)
def test_login_outcome(status, org, outcome, reason):
    assert rules.login_outcome(status, org) == (outcome, reason)


@pytest.mark.parametrize(
    ("current", "action", "target"),
    [
        ("pending", rules.Action.APPROVE, "active"),
        ("pending", rules.Action.REJECT, "rejected"),
        ("invited", rules.Action.ACCEPT_INVITATION, "active"),
        ("invited", rules.Action.RESET_PASSWORD, "active"),
        ("active", rules.Action.DISABLE, "disabled"),
        ("disabled", rules.Action.ENABLE, "active"),
    ],
)
def test_allowed_transitions(current, action, target):
    assert rules.transition(current, action) == target


@pytest.mark.parametrize(
    ("current", "action"),
    [("active", rules.Action.APPROVE), ("rejected", rules.Action.APPROVE),
     ("disabled", rules.Action.RESET_PASSWORD), ("pending", rules.Action.DISABLE),
     ("active", rules.Action.ACCEPT_INVITATION)],
)
def test_refused_transitions(current, action):
    with pytest.raises(Conflict):
        rules.transition(current, action)


def test_enabling_a_user_who_never_set_a_password_leaves_them_invited():
    assert rules.transition("disabled", rules.Action.ENABLE, has_password=False) == "invited"


@pytest.mark.parametrize(
    ("roles", "org", "ok"),
    [(["client"], "o", True), (["admin", "technician"], None, True), (["client"], None, False),
     (["viewer"], "o", False), (["client", "viewer"], "o", False), ([], None, False)],
)
def test_check_roles(roles, org, ok):
    if ok:
        rules.check_roles(roles, org)
    else:
        with pytest.raises(ValidationFailed):
            rules.check_roles(roles, org)


def test_admin_keeps_their_own_access():
    with pytest.raises(Conflict):
        rules.check_admin_keeps_access("a", "a", ["technician"], "active")
    with pytest.raises(Conflict):
        rules.check_admin_keeps_access("a", "a", ["admin"], "disabled")
    rules.check_admin_keeps_access("a", "b", ["technician"], "disabled")


def test_email_rules():
    assert rules.normalize_email("  Maria@Agency.ORG ") == "maria@agency.org"
    assert rules.email_hash("A@b.org") == rules.email_hash(" a@B.org")
    assert rules.valid_email("a@b.org")
    assert not rules.valid_email("a@b")
    assert not rules.valid_email("not an email")


def test_org_name_key_ignores_case_and_spacing():
    assert rules.org_name_key("  Met   Office ") == rules.org_name_key("met office")


def row(**fields):
    base = {"expires_at": NOW + timedelta(days=30), "revoked_at": None, "replaced_by": None,
            "rotated_at": None}
    return {**base, **fields}


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, Refresh.ROTATE),
        ({"expires_at": NOW}, Refresh.INVALID),
        ({"revoked_at": NOW, "replaced_by": "n", "rotated_at": NOW - timedelta(seconds=30)},
         Refresh.GRACE),
        ({"revoked_at": NOW, "replaced_by": "n", "rotated_at": NOW - timedelta(seconds=31)},
         Refresh.REUSE),
        ({"revoked_at": NOW}, Refresh.INVALID),  # logged out or revoked
    ],
)
def test_refresh_decision(fields, expected):
    assert decide(row(**fields), NOW, GRACE) is expected


def test_unknown_refresh_token_is_invalid():
    assert decide(None, NOW, GRACE) is Refresh.INVALID


@given(st.text(min_size=1, max_size=50))
def test_only_the_replaced_token_opens_its_successor(other):
    presented, successor = new_token(), new_token()
    sealed = seal_successor(presented, successor)
    assert open_successor(presented, sealed) == successor
    if other != presented:
        assert open_successor(other, sealed) is None
    assert successor not in sealed


def test_tokens_are_256_bit_and_stored_hashed():
    raw = new_token()
    assert len(raw) >= 43
    assert token_hash(raw) != raw and len(token_hash(raw)) == 64


def test_hasher_and_dummy_verify():
    hasher = Hasher(1, 1024, 1)
    stored = hasher.hash("a long password")
    assert hasher.verify(stored, "a long password")
    assert not hasher.verify(stored, "wrong")
    assert not hasher.verify(None, "dummy password for unknown accounts")
    assert stored.startswith("$argon2id$")


class NeverBreached:
    async def is_breached(self, password):
        return False


async def test_common_passwords_fail_even_without_a_list():
    with pytest.raises(ValidationFailed) as err:
        await check_new_password("Password123", NeverBreached())
    assert err.value.extra["errors"][0]["code"] == "password_breached"
    await check_new_password("long enough and unusual", NeverBreached())
