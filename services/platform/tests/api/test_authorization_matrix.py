"""Authorization matrix (TP "Rule-enforcement tests": rules 3, 4, 5).

Add every route to TABLE with the roles PRD §2.3 allows. The test fails for a route missing
from the table, a mutating route that admits `viewer`, or code that lets the wrong role in.
"""

from __future__ import annotations

import httpx
import pytest
from mms_common.auth import Authenticator, install_auth
from mms_common.auth.revocation import revoke_user
from mms_common.testing.matrix import ANY, Expect, Matrix, Route, check_table, roles
from mms_common.testing.memory import MemoryStore
from mms_common.testing.seed import SEED_USERS, TestIssuer
from mms_common.time import ManualClock

from app.config import Settings
from app.main import create_app

TABLE: dict[Route, Expect] = {
    # Notifications (NOT-1, NOT-2): everyone reads and marks their own, and only their own.
    # Marking as read changes nothing of anyone's work, so a viewer may (self service, rule 5).
    ("GET", "/api/v1/notifications"): Expect(ANY),
    ("GET", "/api/v1/notifications/preferences"): Expect(ANY),
    ("PUT", "/api/v1/notifications/preferences"): Expect(ANY, self_service=True),
    ("POST", "/api/v1/notifications/read-all"): Expect(ANY, self_service=True),
    ("POST", "/api/v1/notifications/{id}/read"): Expect(ANY, self_service=True),
    # The audit log (AUD-4 to AUD-6): admins read the whole trail, export it and run the
    # check. Staff and the Viewer read a resource's History; clients read none of it. Starting
    # a check changes nothing of anyone's work, but it is a POST and admin-only (rule 5).
    ("GET", "/api/v1/audit/events"): roles("admin"),
    ("GET", "/api/v1/audit/events/export.csv"): roles("admin"),
    ("GET", "/api/v1/audit/resources/{kind}/{thing_id}"): roles("admin", "technician", "viewer"),
    ("POST", "/api/v1/audit/verify"): roles("admin"),
    ("GET", "/api/v1/audit/checks/latest"): roles("admin"),
    ("GET", "/api/v1/audit/checks/{check_id}"): roles("admin"),
}


def test_every_route_is_in_the_table():
    app = create_app(Settings(), ready_checks={})
    assert check_table(app, TABLE) == []


@pytest.mark.req("NFR-6")
async def test_matrix():
    clock = ManualClock()
    issuer = TestIssuer(clock)
    store = MemoryStore()
    await revoke_user(store, SEED_USERS["disabled"].id, clock.now())
    app = create_app(Settings(), ready_checks={}, clock=clock)
    # No lifespan here (no Mongo): routes that reach the database answer after the auth
    # check, which is all the matrix looks at. The API tests cover what the routes do.
    install_auth(app, Authenticator(issuer.keys, clock, store))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as client:
        assert await Matrix(client, issuer, TABLE).run() == []
