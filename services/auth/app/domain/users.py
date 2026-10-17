"""Account rules (PRD AUTH-1 to AUTH-13, ORG-4; TRD §5.1). No I/O here."""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mms_common.auth import CLIENT, valid_role_set
from mms_common.errors import Conflict, ValidationFailed


class Status(StrEnum):
    PENDING = "pending"
    INVITED = "invited"
    ACTIVE = "active"
    REJECTED = "rejected"
    DISABLED = "disabled"


class OrgStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Theme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,253}\.[^@\s.]{2,63}$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    return len(email) <= 254 and _EMAIL.match(email) is not None


def email_hash(email: str) -> str:
    """Keys the login throttle and identifies failed logins for unknown emails (AUTH-10)."""
    return hashlib.sha256(normalize_email(email).encode()).hexdigest()


def valid_time_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def org_name_key(name: str) -> str:
    """Organization names are unique ignoring case and surrounding spaces."""
    return " ".join(name.split()).casefold()


# --- Login ------------------------------------------------------------------------------------


class LoginOutcome(StrEnum):
    OK = "ok"
    PENDING = "pending"  # 403 account_pending -> /register/pending
    BLOCKED = "blocked"  # 403 account_blocked -> "This account cannot sign in."


def login_outcome(status: str, org_status: str | None) -> tuple[LoginOutcome, str | None]:
    """Checked only after the password matched (TRD §6.1.1). Returns the outcome and the
    reason recorded in `auth.login_failed`."""
    if status == Status.PENDING:
        return LoginOutcome.PENDING, "pending"
    if status != Status.ACTIVE:
        return LoginOutcome.BLOCKED, status
    if org_status is not None and org_status != OrgStatus.ACTIVE:
        return LoginOutcome.BLOCKED, "org_inactive"
    return LoginOutcome.OK, None


# --- Status changes ---------------------------------------------------------------------------


class Action(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    ACCEPT_INVITATION = "accept_invitation"
    RESET_PASSWORD = "reset_password"  # noqa: S105 - an action name
    DISABLE = "disable"
    ENABLE = "enable"


_TRANSITIONS: dict[Action, dict[Status, Status]] = {
    Action.APPROVE: {Status.PENDING: Status.ACTIVE},
    Action.REJECT: {Status.PENDING: Status.REJECTED},
    Action.ACCEPT_INVITATION: {Status.INVITED: Status.ACTIVE},
    # Completing a reset proves the email, so it also activates an invited user whose
    # invitation expired ("Send a new link" goes through /forgot-password, AFD §7).
    Action.RESET_PASSWORD: {Status.ACTIVE: Status.ACTIVE, Status.INVITED: Status.ACTIVE},
    Action.DISABLE: {Status.ACTIVE: Status.DISABLED, Status.INVITED: Status.DISABLED},
    Action.ENABLE: {Status.DISABLED: Status.ACTIVE},
}


def transition(current: str, action: Action, *, has_password: bool = True) -> Status:
    target = _TRANSITIONS[action].get(Status(current))
    if target is None:
        raise Conflict(f"A {current} account can't be changed this way", code="invalid_status")
    if action is Action.ENABLE and not has_password:
        return Status.INVITED  # never set a password: they finish through a reset link
    return target


def can_reset_password(status: str) -> bool:
    return Status(status) in _TRANSITIONS[Action.RESET_PASSWORD]


# --- Roles and organizations -----------------------------------------------------------------


def check_roles(roles: list[str], org_id: str | None) -> None:
    """A client holds `client` alone and belongs to one organization; staff belong to none
    (PRD §2.2, TRD §5.1)."""
    if not valid_role_set(roles):
        raise ValidationFailed(
            "A user is either a client or holds staff roles", code="invalid_roles"
        )
    if CLIENT in roles and not org_id:
        raise ValidationFailed("A client needs an organization", code="org_required")
    if CLIENT not in roles and org_id:
        raise ValidationFailed(
            "Staff don't belong to a client organization", code="org_not_allowed"
        )


def check_admin_keeps_access(
    actor_id: str, target_id: str, roles: list[str], status: str
) -> None:
    """An admin can't remove their own admin role or disable themselves."""
    if actor_id == target_id and ("admin" not in roles or status != Status.ACTIVE):
        raise Conflict("You can't remove your own admin access", code="self_lockout")
