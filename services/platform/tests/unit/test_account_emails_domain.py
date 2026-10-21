"""Account emails without I/O (PRD NOT-3, Appendix B; TRD §6.2)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.account_emails import (
    ACCOUNT_KINDS,
    EVENT_TYPES,
    MAX_ATTEMPTS,
    EmailJob,
    Kind,
    job_for,
    render,
    retry_at,
)

USER = {"user_id": "u1", "email": "maria@example.org", "name": "Maria Lopez",
        "roles": ["client"], "status": "active", "org_id": "o1"}


@pytest.mark.req("NOT-3")
@pytest.mark.parametrize(
    ("event_type", "data", "expected"),
    [
        ("user.approved", USER, EmailJob(Kind.APPROVED, "u1", to="maria@example.org",
                                         name="Maria Lopez")),
        ("user.rejected", {**USER, "status": "rejected", "reason": "Unknown org"},
         EmailJob(Kind.REJECTED, "u1", to="maria@example.org", name="Maria Lopez",
                  reason="Unknown org")),
        ("user.invited", {**USER, "status": "invited", "invitation_id": "i1"},
         EmailJob(Kind.INVITATION, "u1", link_id="i1")),
        ("auth.password_reset_requested", {"user_id": "u1", "reset_id": "r1"},
         EmailJob(Kind.RESET, "u1", link_id="r1")),
    ],
)
def test_each_account_event_asks_for_one_email(event_type, data, expected):
    assert event_type in EVENT_TYPES
    assert job_for(event_type, data) == expected


@pytest.mark.parametrize("event_type", ["user.registered", "user.updated", "user.created",
                                        "auth.login_succeeded", "auth.password_reset"])
def test_other_events_send_nothing(event_type):
    assert job_for(event_type, {**USER, "proposed_org_name": "X", "changed_fields": [],
                                "via": "cli", "email_hash": "h"}) is None


@pytest.mark.req("NOT-3")
def test_invitation_and_reset_jobs_hold_no_token_or_address():
    """The token is minted on send and the address comes back with it (TRD §6.2)."""
    job = job_for("auth.password_reset_requested", {"user_id": "u1", "reset_id": "r1"})
    assert job is not None and job.to is None and job.name is None


def test_html_escapes_every_value():
    hostile = '<script>alert(1)</script>"'
    out = render(Kind.REJECTED, name=hostile, url=None, reason=hostile)
    assert "<script>" not in out.html
    assert "&lt;script&gt;" in out.html
    assert hostile in out.text  # the plain-text part is shown as text by mail clients


def test_link_is_in_both_parts_and_the_button_is_the_only_action():
    url = "https://mms.example.org/reset-password/abc?x=1&y=2"
    out = render(Kind.RESET, name="Maria", url=url)
    assert out.subject == "Reset your MARS-MMS password"
    assert f"Set a new password: {url}" in out.text
    assert 'href="https://mms.example.org/reset-password/abc?x=1&amp;y=2"' in out.html
    assert out.html.count("<a ") == 1


def test_rejection_has_the_reason_and_no_button():
    out = render(Kind.REJECTED, name="Maria", url=None, reason="We couldn't match the email")
    assert "Reason: We couldn't match the email" in out.text
    assert "<a " not in out.html


def test_approval_links_to_login():
    out = render(Kind.APPROVED, name="Maria", url="https://mms.example.org/login")
    assert "Log in: https://mms.example.org/login" in out.text


def test_copy_follows_the_voice_rules():
    """DBD Voice and microcopy: no exclamation marks, and the product is never called AWS alone."""
    for kind in ACCOUNT_KINDS:
        out = render(kind, name="Maria", url="https://x.org/l", reason="r")
        assert "!" not in out.text
        assert " AWS " not in out.text


def test_retries_back_off_then_give_up():
    now = datetime(2026, 10, 17, 9, tzinfo=UTC)
    assert retry_at(1, now) == now + timedelta(minutes=1)
    assert retry_at(2, now) == now + timedelta(minutes=2)
    assert retry_at(8, now) == now + timedelta(hours=1)  # capped
    assert retry_at(MAX_ATTEMPTS, now) is None


def test_every_email_uses_the_product_name():
    """DBD D1: the product is MARS-MMS in emails, as in the app."""
    for kind in ACCOUNT_KINDS:
        out = render(kind, name="Maria", url="https://mms.example.org/x", reason="r")
        for part in (out.subject, out.text, out.html):
            assert "AWS-MMS" not in part
        assert "MARS-MMS" in out.text and "MARS-MMS" in out.html
