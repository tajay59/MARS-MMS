"""Authorization matrix (TP "Rule-enforcement tests": rules 3, 4, 5), from PRD §2.3.

Every route is listed with the roles that may call it. The test fails for a route missing
from the table, a mutating route that admits `viewer`, or code that lets the wrong role in.
"""

from __future__ import annotations

import httpx
import pytest
from mms_common.testing.matrix import ANY, Expect, Matrix, Route, check_table, roles, service

from app.config import Settings
from app.main import create_app

STAFF = roles("technician", "admin", "viewer")
WRITE = roles("technician", "admin")

TABLE: dict[Route, Expect] = {
    # Stations: everyone reads (clients their own organization's), staff write (STN-1, STN-6).
    ("GET", "/api/v1/stations"): Expect(ANY),
    ("GET", "/api/v1/stations/facets"): Expect(ANY),
    ("POST", "/api/v1/stations"): WRITE,
    ("POST", "/api/v1/stations/import"): roles("admin"),  # STN-8
    ("GET", "/api/v1/stations/{id}"): Expect(ANY),
    ("PATCH", "/api/v1/stations/{id}"): WRITE,
    ("GET", "/api/v1/stations/{id}/installations"): Expect(ANY),
    # Sensor inventory and calibrations: staff (SEN-1, SEN-2, CAL-1, CAL-4).
    ("GET", "/api/v1/sensor-models"): STAFF,
    ("POST", "/api/v1/sensor-models"): WRITE,
    ("GET", "/api/v1/sensor-models/{id}"): STAFF,
    ("PATCH", "/api/v1/sensor-models/{id}"): WRITE,
    ("GET", "/api/v1/sensor-units"): STAFF,
    ("POST", "/api/v1/sensor-units"): WRITE,
    ("GET", "/api/v1/sensor-units/{id}"): STAFF,
    ("PATCH", "/api/v1/sensor-units/{id}"): WRITE,
    ("POST", "/api/v1/sensor-units/{id}/install"): WRITE,
    ("POST", "/api/v1/sensor-units/{id}/remove"): WRITE,
    ("GET", "/api/v1/calibrations/due"): STAFF,
    ("GET", "/api/v1/calibrations"): STAFF,
    ("POST", "/api/v1/calibrations"): WRITE,
    # Internal: read-model backfill (TRD §8.6).
    ("GET", "/internal/snapshot/{entity}"): service("report", "platform"),
}


def test_every_route_is_in_the_table():
    app = create_app(Settings(), ready_checks={})
    assert check_table(app, TABLE) == []


@pytest.mark.req("NFR-6")
async def test_matrix(ops):
    station = await ops.station()  # organization A's
    transport = httpx.ASGITransport(app=ops.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://mms.test") as client:
        matrix = Matrix(
            client, ops.issuer, TABLE,
            cross_org={
                ("GET", "/api/v1/stations/{id}"): station["id"],
                ("GET", "/api/v1/stations/{id}/installations"): station["id"],
            },
        )
        assert await matrix.run() == []
