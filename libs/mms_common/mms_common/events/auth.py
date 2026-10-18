"""Payloads of the events the auth service produces on `mms.auth.events` (TRD §8.4).

The message key is the root aggregate: `user_id` for `user.*` and `auth.*`, `org_id` for
`org.*`. A failed login for an unknown email has no user, so its key is the email hash.

No event carries a password, a password hash or a token. Reset and invitation links are
minted on send through auth's `/internal/account-links` (TRD §6.2), never put in an event.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from mms_common.events.registry import register


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserData(_Data):
    """Every `user.*` event carries the user's current directory fields, so platform's
    `user_directory` read model can upsert from any of them (TRD §5.5)."""

    user_id: str
    email: str
    name: str
    roles: list[str]
    status: str
    org_id: str | None = None


# --- auth.* security events (audit only) -----------------------------------------------------


@register("auth.login_succeeded")
class LoginSucceeded(_Data):
    user_id: str
    email_hash: str


@register("auth.login_failed")
class LoginFailed(_Data):
    user_id: str | None = None
    email_hash: str
    # wrong_password | unknown_email | pending | rejected | disabled | invited | org_inactive
    reason: str


@register("auth.logout")
class Logout(_Data):
    user_id: str


@register("auth.password_reset_requested")
class PasswordResetRequested(_Data):
    """notification mints the link through `/internal/account-links` (kind `reset`)."""

    user_id: str
    reset_id: str


@register("auth.password_reset")
class PasswordReset(_Data):
    user_id: str
    email_hash: str


@register("auth.token_reuse_detected")
class TokenReuseDetected(_Data):
    """A rotated refresh token was presented after the 30 s grace: its family is revoked."""

    user_id: str
    family_id: str


# --- user.* ----------------------------------------------------------------------------------


@register("user.registered")
class UserRegistered(UserData):
    proposed_org_name: str


@register("user.invited")
class UserInvited(UserData):
    """notification mints the link through `/internal/account-links` (kind `invitation`)."""

    invitation_id: str


@register("user.created")
class UserCreated(UserData):
    """An account made outside the app's flows: the first admin, from auth's CLI."""

    via: str


@register("user.approved")
class UserApproved(UserData):
    pass


@register("user.rejected")
class UserRejected(UserData):
    reason: str


@register("user.updated")
class UserUpdated(UserData):
    changed_fields: list[str]


@register("user.disabled")
class UserDisabled(UserData):
    pass


@register("user.purged")
class UserPurged(_Data):
    """A pending registration deleted after the configured period (AUTH-5)."""

    user_id: str


# --- org.* -----------------------------------------------------------------------------------


class OrgData(_Data):
    org_id: str
    name: str
    country: str
    status: str


@register("org.created")
class OrgCreated(OrgData):
    pass


@register("org.updated")
class OrgUpdated(OrgData):
    changed_fields: list[str]


# --- branding.* ------------------------------------------------------------------------------


@register("branding.updated")
class BrandingUpdated(_Data):
    """An admin changed the organization-wide brand colours (decision W4-12). `custom` is false
    when they went back to the built-in colours. Keyed `branding`."""

    custom: bool
    name: str | None = None
    seed: str | None = None
