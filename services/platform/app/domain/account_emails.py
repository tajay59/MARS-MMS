"""Account emails (PRD NOT-3, Appendix B; TRD §3.5). No I/O here.

Four auth events become an email: approval, rejection, invitation and password reset. They
are always sent (NOT-4 can't turn them off). Reset and invitation links are minted when the
email is sent (TRD §6.2), so a job holds the link's `{kind, id}`, never a token.

Sending is at least once: a crash between the SMTP hand-off and marking the row sent sends
the email again. Minting again replaces the token, so only the newest email's link works.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    INVITATION = "invitation"
    RESET = "reset"
    # Not account emails: the email that follows a notification, and the weekly digest.
    # They are sent only if the person has not turned them off (NOT-4), and are
    # rendered from the notification or digest at send time.
    NOTIFICATION = "notification"
    DIGEST = "digest"


ACCOUNT_KINDS = (Kind.APPROVED, Kind.REJECTED, Kind.INVITATION, Kind.RESET)

# The link kinds auth's `/internal/account-links` takes.
LINK_KIND = {Kind.INVITATION: "invitation", Kind.RESET: "reset"}

MAX_ATTEMPTS = 10
FIRST_RETRY = timedelta(minutes=1)
LONGEST_RETRY = timedelta(hours=1)


@dataclass(frozen=True)
class EmailJob:
    kind: Kind
    user_id: str
    # Approval and rejection carry the address in the event. Invitation and reset get it
    # from auth together with the link, so a changed address is respected.
    to: str | None = None
    name: str | None = None
    link_id: str | None = None
    reason: str | None = None
    notification_id: str | None = None
    digest_id: str | None = None


def job_for(event_type: str, data: Mapping[str, Any]) -> EmailJob | None:
    """The email an auth event asks for, if any."""
    user_id = str(data["user_id"])
    match event_type:
        case "user.approved":
            return EmailJob(Kind.APPROVED, user_id, to=data["email"], name=data["name"])
        case "user.rejected":
            return EmailJob(
                Kind.REJECTED, user_id, to=data["email"], name=data["name"], reason=data["reason"]
            )
        case "user.invited":
            return EmailJob(Kind.INVITATION, user_id, link_id=str(data["invitation_id"]))
        case "auth.password_reset_requested":
            return EmailJob(Kind.RESET, user_id, link_id=str(data["reset_id"]))
    return None


EVENT_TYPES = ("user.approved", "user.rejected", "user.invited", "auth.password_reset_requested")


def retry_at(attempts: int, now: datetime) -> datetime | None:
    """When to try again after `attempts` failed tries; None once the email is given up."""
    if attempts >= MAX_ATTEMPTS:
        return None
    wait: timedelta = min(FIRST_RETRY * 2 ** (attempts - 1), LONGEST_RETRY)
    return now + wait


# --- Rendering (DBD "PDF reports and email"; voice from DBD "Voice and microcopy") -----------

# The product name shown to users (DBD D1), as in the app (frontend/src/app/brand.ts).
PRODUCT_NAME = "MARS-MMS"
PRODUCT_LONG_NAME = "Automatic Weather Station Maintenance Management System"


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


@dataclass(frozen=True)
class _Copy:
    subject: str
    heading: str
    paragraphs: tuple[str, ...]
    button: str | None = None


def _copy(kind: Kind, reason: str | None) -> _Copy:
    match kind:
        case Kind.APPROVED:
            return _Copy(
                "Your MARS-MMS account is approved",
                "Your account is approved",
                ("You can now log in to see your stations, report problems and follow the work.",),
                "Log in",
            )
        case Kind.REJECTED:
            return _Copy(
                "Your MARS-MMS registration",
                "We couldn't approve your account",
                (
                    f"Reason: {reason or 'none given'}",
                    "If you think this is a mistake, contact the service desk.",
                ),
            )
        case Kind.INVITATION:
            return _Copy(
                "You're invited to MARS-MMS",
                "You're invited to MARS-MMS",
                (
                    "Set a password to finish setting up your account.",
                    "The link works once, for 7 days. When it expires, use “Forgot "
                    "password?” on the login page to get a new one.",
                ),
                "Set your password",
            )
        case Kind.RESET:
            return _Copy(
                "Reset your MARS-MMS password",
                "Reset your password",
                (
                    "We got a request to reset the password for this account. The link works "
                    "once, for 1 hour.",
                    "If you didn't ask for this, ignore this email. Your password stays the same.",
                ),
                "Set a new password",
            )
        case _:
            raise ValueError(f"{kind} is not an account email")


# Brand primary-600 and slate neutrals (DBD Colour palette). Email uses the system font stack:
# web fonts are unreliable in mail clients (DBD).
_FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def render(kind: Kind, *, name: str, url: str | None, reason: str | None = None) -> Rendered:
    """Subject, plain text and HTML (a single 600 px column, one primary button). Every value
    from the event or from auth is escaped in the HTML part."""
    copy = _copy(kind, reason)
    greeting = f"Hello {name},"

    text_parts = [greeting, copy.heading + ".", *copy.paragraphs]
    if copy.button and url:
        text_parts.append(f"{copy.button}: {url}")
    text_parts.append(f"{PRODUCT_NAME} · {PRODUCT_LONG_NAME}")
    text = "\n\n".join(text_parts) + "\n"

    e = html.escape
    paragraphs = "".join(
        f'<p style="margin:0 0 16px;font-size:16px;line-height:24px;color:#0F172A">{e(p)}</p>'
        for p in copy.paragraphs
    )
    button = ""
    if copy.button and url:
        button = (
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 24px">'
            '<tr><td style="border-radius:6px;background:#22569A">'
            f'<a href="{e(url, quote=True)}" style="display:inline-block;padding:12px 20px;'
            "font-size:16px;line-height:24px;font-weight:600;color:#FFFFFF;text-decoration:none;"
            f'border-radius:6px">{e(copy.button)}</a></td></tr></table>'
            '<p style="margin:0 0 16px;font-size:14px;line-height:20px;color:#475569">'
            "If the button doesn't work, copy this address into your browser:<br>"
            f'<span style="word-break:break-all;color:#22569A">{e(url)}</span></p>'
        )
    body = (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(copy.subject)}</title></head>"
        f'<body style="margin:0;padding:0;background:#F8FAFC;font-family:{_FONT}">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#F8FAFC"><tr><td align="center" style="padding:32px 16px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="width:100%;max-width:600px;background:#FFFFFF;border:1px solid #E2E8F0;'
        'border-radius:10px">'
        '<tr><td style="padding:24px 32px;border-bottom:1px solid #E2E8F0;font-size:18px;'
        f'line-height:24px;font-weight:600;color:#22569A">{PRODUCT_NAME}</td></tr>'
        '<tr><td style="padding:32px">'
        '<p style="margin:0 0 16px;font-size:16px;line-height:24px;color:#0F172A">'
        f"{e(greeting)}</p>"
        f'<h1 style="margin:0 0 16px;font-size:20px;line-height:28px;font-weight:600;'
        f'color:#0F172A">{e(copy.heading)}</h1>'
        f"{paragraphs}{button}"
        "</td></tr>"
        '<tr><td style="padding:16px 32px;border-top:1px solid #E2E8F0;font-size:12px;'
        f'line-height:16px;color:#475569">{PRODUCT_LONG_NAME}. '
        "This email was sent because of a change to your account.</td></tr>"
        "</table></td></tr></table></body></html>"
    )
    return Rendered(copy.subject, text, body)
