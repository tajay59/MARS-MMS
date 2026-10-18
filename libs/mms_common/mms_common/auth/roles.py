"""Roles and role groups (PRD §2.2, TRD §6.3)."""

from __future__ import annotations

from collections.abc import Iterable

CLIENT = "client"
TECHNICIAN = "technician"
ADMIN = "admin"
VIEWER = "viewer"
SERVICE = "service"

STAFF = frozenset({TECHNICIAN, ADMIN, VIEWER})
STAFF_WRITE = frozenset({TECHNICIAN, ADMIN})  # viewers never mutate (CLAUDE.md rule 5)
USER_ROLES = frozenset({CLIENT, *STAFF})


def valid_role_set(roles: Iterable[str]) -> bool:
    """A user holds `client` alone, or one or more staff roles (PRD §2.2, TRD §5.1)."""
    held = set(roles)
    if not held or not held <= USER_ROLES:
        return False
    return held == {CLIENT} or CLIENT not in held
