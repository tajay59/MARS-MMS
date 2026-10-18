"""Authorization matrix (TP "Rule-enforcement tests": rules 3, 4, 5), from PRD §2.3.

Every route is listed with the roles that may call it. The test fails for a route missing
from the table, a mutating route that admits `viewer`, or code that lets the wrong role in.
"""

from __future__ import annotations

import httpx
import pytest
from mms_common.testing.matrix import (
    ANY,
    PUBLIC,
    Expect,
    Matrix,
    Route,
    check_table,
    roles,
    service,
)
from mms_common.testing.seed import ORG_A

from app.config import Settings
from app.main import create_app

TABLE: dict[Route, Expect] = {
    # Public: the account pages before sign-in. refresh and logout use the cookie.
    ("POST", "/api/v1/auth/register"): Expect(PUBLIC),
    ("POST", "/api/v1/auth/login"): Expect(PUBLIC),
    ("POST", "/api/v1/auth/refresh"): Expect(PUBLIC),
    ("POST", "/api/v1/auth/logout"): Expect(PUBLIC),
    ("POST", "/api/v1/auth/password-reset/request"): Expect(PUBLIC),
    ("POST", "/api/v1/auth/password-reset/confirm"): Expect(PUBLIC),
    ("POST", "/api/v1/auth/invitations/accept"): Expect(PUBLIC),
    # Own profile: every role, viewers included (BSD "Own user profile").
    ("GET", "/api/v1/auth/me"): Expect(ANY),
    ("PATCH", "/api/v1/auth/me"): Expect(ANY, self_service=True),
    # Brand colours: everyone reads them, before sign-in too; admins change them (W4-12).
    ("GET", "/api/v1/auth/branding"): Expect(PUBLIC),
    ("PUT", "/api/v1/auth/branding"): roles("admin"),
    # Manage users and registrations: admin only (PRD §2.3).
    ("GET", "/api/v1/users"): roles("admin"),
    ("POST", "/api/v1/users"): roles("admin"),
    ("GET", "/api/v1/users/{id}"): roles("admin"),
    ("PATCH", "/api/v1/users/{id}"): roles("admin"),
    ("POST", "/api/v1/users/{id}/approve"): roles("admin"),
    ("POST", "/api/v1/users/{id}/reject"): roles("admin"),
    # Organizations: staff read all, a client reads their own, admins write.
    ("GET", "/api/v1/organizations"): Expect(ANY),
    ("GET", "/api/v1/organizations/{id}"): Expect(ANY),
    ("POST", "/api/v1/organizations"): roles("admin"),
    ("PATCH", "/api/v1/organizations/{id}"): roles("admin"),
    # Internal.
    ("POST", "/internal/service-token"): service(),  # HTTP Basic with a service secret
    ("POST", "/internal/account-links"): service("platform"),
    ("GET", "/internal/snapshot/{entity}"): service("platform", "operations", "report"),
}


def test_every_route_is_in_the_table():
    app = create_app(Settings(), ready_checks={})
    assert check_table(app, TABLE) == []


@pytest.mark.req("NFR-6")
async def test_matrix(auth):
    transport = httpx.ASGITransport(app=auth.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://mms.test") as client:
        matrix = Matrix(
            client, auth.issuer, TABLE,
            cross_org={("GET", "/api/v1/organizations/{id}"): ORG_A},
        )
        assert await matrix.run() == []
