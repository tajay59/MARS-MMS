"""Authorization matrix (TP "Rule-enforcement tests": rules 3, 4, 5), from PRD §2.3.

Every route is listed with the roles that may call it. The test fails for a route missing
from the table, a mutating route that admits `viewer`, or code that lets the wrong role in.
"""

from __future__ import annotations

import httpx
import pytest
from mms_common.auth import Authenticator, install_auth
from mms_common.auth.revocation import revoke_user
from mms_common.testing.matrix import ANY, Expect, Matrix, Route, check_table, roles, service
from mms_common.testing.memory import MemoryStore
from mms_common.testing.seed import SEED_USERS, TestIssuer
from mms_common.time import ManualClock

from app.config import Settings
from app.main import create_app

# Uploading and captioning need a role that can write or own the upload; the owner check then
# decides whether this person may attach to this owner (staff to stations, clients to their
# own requests). Viewers never mutate (rule 5).
UPLOAD = roles("technician", "admin", "client")

TABLE: dict[Route, Expect] = {
    ("POST", "/api/v1/uploads"): UPLOAD,
    ("POST", "/api/v1/uploads/{media_id}/parts"): UPLOAD,
    ("POST", "/api/v1/uploads/{media_id}/complete"): UPLOAD,
    ("GET", "/api/v1/media"): Expect(ANY),
    ("GET", "/api/v1/media/{media_id}"): Expect(ANY),
    ("PATCH", "/api/v1/media/{media_id}"): UPLOAD,
    ("DELETE", "/api/v1/media/{media_id}"): UPLOAD,
    ("GET", "/internal/media/{media_id}"): service("operations"),
    ("POST", "/internal/media/{media_id}/url"): service("operations"),
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
