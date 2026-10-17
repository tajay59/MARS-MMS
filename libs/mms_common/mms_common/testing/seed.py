"""The seed users every level of testing shares (TP "Seed users"), and a token issuer for
service tests that don't run auth.

IDs are fixed UUIDv7 strings so failures reproduce between local runs, CI and staging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mms_common.auth.tokens import (
    ACCESS_TTL,
    SigningKey,
    StaticKeys,
    issue_access,
    issue_service,
)
from mms_common.time import Clock

ORG_A = "01900000-0000-7000-8000-00000000a000"
ORG_B = "01900000-0000-7000-8000-00000000b000"


@dataclass(frozen=True)
class SeedUser:
    key: str
    id: str
    name: str
    email: str
    roles: tuple[str, ...]
    org_id: str | None = None
    status: str = "active"
    labels: frozenset[str] = field(default_factory=frozenset)


def _id(n: int) -> str:
    return f"01900000-0000-7000-8000-{n:012x}"


SEED_USERS: dict[str, SeedUser] = {
    u.key: u
    for u in [
        SeedUser("client_a1", _id(0xA1), "Client A1", "client.a1@example.org", ("client",), ORG_A),
        SeedUser("client_a2", _id(0xA2), "Client A2", "client.a2@example.org", ("client",), ORG_A),
        SeedUser("client_b1", _id(0xB1), "Client B1", "client.b1@example.org", ("client",), ORG_B),
        SeedUser("admin", _id(0xAD), "Admin", "admin@example.org", ("admin",)),
        SeedUser("tech1", _id(0x71), "Tech 1", "tech1@example.org", ("technician",)),
        SeedUser("tech2", _id(0x72), "Tech 2", "tech2@example.org", ("technician",)),
        SeedUser(
            "tech_admin", _id(0x7A), "Tech-Admin", "tech.admin@example.org", ("technician", "admin")
        ),
        SeedUser("viewer", _id(0x77), "Viewer", "viewer@example.org", ("viewer",)),
        SeedUser(
            "disabled", _id(0xD1), "Disabled", "disabled@example.org", ("client",), ORG_A,
            status="disabled",
        ),
    ]
}


class TestIssuer:
    """Signs tokens with a throwaway key. Give the app `issuer.keys` as its key source."""

    __test__ = False  # not a pytest test class

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.signing = SigningKey(Ed25519PrivateKey.generate())
        self.keys = StaticKeys([self.signing.jwk])

    def token(self, user: SeedUser | str, ttl: timedelta = ACCESS_TTL) -> str:
        seed = SEED_USERS[user] if isinstance(user, str) else user
        return issue_access(
            self.signing,
            clock=self.clock,
            user_id=seed.id,
            roles=list(seed.roles),
            org_id=seed.org_id,
            name=seed.name,
            ttl=ttl,
        )

    def service_token(self, service: str) -> str:
        return issue_service(self.signing, clock=self.clock, service=service)

    def tokens(self) -> dict[str, str]:
        """A token per seed user, for the authorization matrix."""
        return {key: self.token(user) for key, user in SEED_USERS.items()}
