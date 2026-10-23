"""Authorization matrix (TP "Rule-enforcement tests": rules 3, 4, 5).

Every route is listed with the roles PRD §2.3 allows. The test fails for a route missing
from the table, a mutating route that admits `viewer`, or code that lets the wrong role in.
"""

from __future__ import annotations

import httpx
import pytest
from mms_common.auth import Authenticator, install_auth
from mms_common.auth.revocation import revoke_user
from mms_common.testing.matrix import Expect, Matrix, Route, check_table, roles
from mms_common.testing.memory import MemoryStore
from mms_common.testing.seed import SEED_USERS, TestIssuer
from mms_common.time import ManualClock

from app.config import Settings
from app.main import create_app

TABLE: dict[Route, Expect] = {
    # Label sheets (QR-6): admins print; a job is visible to whoever asked for it.
    ("POST", "/api/v1/reports/labels"): roles("admin"),
    ("GET", "/api/v1/reports/jobs/{job_id}"): roles("technician", "admin", "viewer"),
    # Visit reports (W16): staff read drafts; a client reads only a final report of their own
    # organization (the route filters, rule 6); only attending staff and admins ask for a preview.
    ("GET", "/api/v1/reports"): roles("technician", "admin", "viewer", "client"),
    ("GET", "/api/v1/reports/{report_id}"): roles("technician", "admin", "viewer", "client"),
    ("GET", "/api/v1/reports/{report_id}/download"): roles("technician", "admin", "viewer", "client"),
    ("POST", "/api/v1/reports/{report_id}/preview"): roles("technician", "admin"),
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
