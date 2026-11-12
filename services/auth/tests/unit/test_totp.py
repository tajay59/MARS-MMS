"""TOTP (RFC 6238), recovery codes and the enforcement rule: pure code, no containers (W22)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import mfa, recovery, totp

# RFC 6238 Appendix B, SHA-1: the secret is the ASCII "12345678901234567890"; its table gives
# 8-digit codes, and the 6-digit code is the last six of the same number.
RFC_SECRET = b"12345678901234567890"
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


@pytest.mark.parametrize(("at", "expected"), RFC_VECTORS)
def test_rfc_6238_vectors(at, expected):
    assert totp.code_at(RFC_SECRET, at, digits=8) == expected
    assert totp.code_at(RFC_SECRET, at) == expected[-6:]


def test_a_code_is_accepted_one_step_either_side_and_not_two():
    now = 1_700_000_000.0
    for steps, ok in [(-2, False), (-1, True), (0, True), (1, True), (2, False)]:
        code = totp.code_at(RFC_SECRET, now + steps * totp.STEP_S)
        got = totp.verify(RFC_SECRET, code, now, None)
        assert (got is not None) is ok, steps


def test_a_step_already_used_is_a_replay():
    now = 1_700_000_000.0
    code = totp.code_at(RFC_SECRET, now)
    step = totp.verify(RFC_SECRET, code, now, None)
    assert step == totp.step_at(now)
    assert totp.verify(RFC_SECRET, code, now, step) is None  # the same code again
    earlier = totp.code_at(RFC_SECRET, now - totp.STEP_S)
    assert totp.verify(RFC_SECRET, earlier, now, step) is None  # an older step too
    later = totp.code_at(RFC_SECRET, now + totp.STEP_S)
    assert totp.verify(RFC_SECRET, later, now, step) == step + 1


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "12345a", "١٢٣٤٥٦", "12 34 5"])
def test_codes_that_are_not_six_digits_never_match(bad):
    assert totp.verify(RFC_SECRET, bad, 59, None) is None


def test_the_keyboard_suggestion_with_a_space_is_accepted():
    code = totp.code_at(RFC_SECRET, 59)
    assert totp.verify(RFC_SECRET, f"{code[:3]} {code[3:]}", 59, None) is not None


def test_base32_round_trip_and_uri():
    secret = totp.new_secret()
    assert len(secret) == 20
    text = totp.to_base32(secret)
    assert len(text) == 32 and "=" not in text
    assert totp.from_base32(text.lower()) == secret
    uri = totp.otpauth_uri(secret, "ops+a@example.org", "MARS-MMS")
    assert uri.startswith("otpauth://totp/MARS-MMS%3Aops%2Ba%40example.org?")
    assert f"secret={text}" in uri and "issuer=MARS-MMS" in uri
    assert "digits=6" in uri and "period=30" in uri and "algorithm=SHA1" in uri


def test_recovery_codes_are_ten_distinct_one_time_codes_stored_as_hashes():
    codes, records = recovery.generate()
    assert len(codes) == len(set(codes)) == recovery.COUNT == len(records)
    for code in codes:
        assert len(code) == 11 and code[5] == "-"
    assert all(len(r["hash"]) == 64 and r["used_at"] is None for r in records)
    assert not any(code.replace("-", "") in str(records) for code in codes)
    # typed without the dash, in lower case, with spaces: still the same code
    typed = codes[3].replace("-", "").lower() + " "
    assert recovery.find_unused(records, typed) == records[3]["hash"]
    assert recovery.find_unused(records, "AAAAA-AAAAA") is None
    records[3]["used_at"] = datetime.now(UTC)
    assert recovery.find_unused(records, codes[3]) is None
    assert recovery.remaining(records) == 9


NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
REQUIRED = ["admin"]


def gate(roles, *, enrolled=False, grace=None, now=NOW):
    return mfa.gate(roles=roles, enrolled=enrolled, grace_until=grace, now=now,
                    required_roles=REQUIRED)


def test_who_needs_a_second_factor():
    assert gate(["technician"]) is mfa.Gate.NOT_REQUIRED
    assert gate(["client"]) is mfa.Gate.NOT_REQUIRED
    assert gate(["technician"], enrolled=True) is mfa.Gate.ENROLLED  # opted in
    assert gate(["admin"], enrolled=True) is mfa.Gate.ENROLLED
    # a person with both roles is covered by the stricter one
    assert gate(["technician", "admin"], grace=NOW + timedelta(days=1)) is mfa.Gate.IN_WINDOW


def test_the_setup_window_ends_exactly_at_grace_until():
    end = NOW + timedelta(days=7)
    assert gate(["admin"], grace=end, now=end - timedelta(seconds=1)) is mfa.Gate.IN_WINDOW
    assert gate(["admin"], grace=end, now=end) is mfa.Gate.BLOCKED
    assert gate(["admin"], grace=None) is mfa.Gate.BLOCKED  # a window must be started first


def test_a_window_starts_only_when_needed():
    def needs(roles, enrolled=False, grace=None):
        return mfa.needs_window(roles=roles, enrolled=enrolled, grace_until=grace,
                                required_roles=REQUIRED)

    assert needs(["admin"])
    assert not needs(["admin"], grace=NOW)  # already has one (a past one is not restarted)
    assert not needs(["admin"], enrolled=True)
    assert not needs(["technician"])
