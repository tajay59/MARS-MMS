"""Who is calling: a user from an access token, or a service from a service token."""

from __future__ import annotations

from dataclasses import dataclass

from mms_common.auth.roles import ADMIN, CLIENT, STAFF, STAFF_WRITE


@dataclass(frozen=True)
class User:
    id: str
    roles: frozenset[str]
    org_id: str | None
    name: str
    token_id: str

    @property
    def is_client(self) -> bool:
        return CLIENT in self.roles

    @property
    def is_staff(self) -> bool:
        return bool(self.roles & STAFF)

    @property
    def can_write(self) -> bool:
        """Staff who may change records; viewers may not (rule 5)."""
        return bool(self.roles & STAFF_WRITE)

    @property
    def is_admin(self) -> bool:
        return ADMIN in self.roles


@dataclass(frozen=True)
class ServicePrincipal:
    name: str
