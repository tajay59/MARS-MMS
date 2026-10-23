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
    ("GET", "/api/v1/stations/places"): WRITE,  # the station form's time zones
    ("POST", "/api/v1/stations"): WRITE,
    ("POST", "/api/v1/stations/import"): roles("admin"),  # STN-8
    ("GET", "/api/v1/stations/{id}"): Expect(ANY),
    ("PATCH", "/api/v1/stations/{id}"): WRITE,
    ("GET", "/api/v1/stations/{id}/installations"): Expect(ANY),
    # QR codes (QR-2, QR-4, QR-7): everyone resolves what their scope allows, admins regenerate.
    ("GET", "/api/v1/qr/{token}"): Expect(ANY),
    ("POST", "/api/v1/stations/{id}/qr/regenerate"): roles("admin"),
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
    # Documents (DOC-1 to DOC-4): everyone reads what their scope allows, staff write.
    ("GET", "/api/v1/documents"): Expect(ANY),
    ("POST", "/api/v1/documents"): WRITE,
    ("GET", "/api/v1/documents/{id}"): Expect(ANY),
    ("PATCH", "/api/v1/documents/{id}"): WRITE,
    ("GET", "/api/v1/documents/{id}/download"): Expect(ANY),
    ("GET", "/api/v1/stations/{id}/documents"): Expect(ANY),
    # Configuration versions (CFG-1 to CFG-3): staff only; clients never see them (rule 6).
    ("GET", "/api/v1/stations/{id}/config-versions"): STAFF,
    ("POST", "/api/v1/stations/{id}/config-versions"): WRITE,
    ("GET", "/api/v1/stations/{id}/config-versions/{version}"): STAFF,
    ("GET", "/api/v1/stations/{id}/config-versions/{version}/diff"): STAFF,
    # Requests (REQ-1, REQ-2, REQ-5, REQ-6, REQ-11): everyone reads what their scope allows;
    # clients and admins create and edit; only admins approve and deny; a client cancels their
    # own, an admin any (the state machine decides which, per status).
    ("GET", "/api/v1/requests"): Expect(ANY),
    ("POST", "/api/v1/requests"): roles("client", "admin"),
    ("GET", "/api/v1/requests/{id}"): Expect(ANY),
    ("PATCH", "/api/v1/requests/{id}"): roles("client", "admin"),
    # Queue and staffing (REQ-7, W9): technicians and admins take or release work, admins assign.
    ("GET", "/api/v1/queue"): Expect(ANY),  # staff read it; a client gets 404, not 403
    ("GET", "/api/v1/requests/workload"): roles("admin"),
    ("POST", "/api/v1/requests/{id}/assign"): roles("admin"),
    ("POST", "/api/v1/requests/{id}/claim"): WRITE,
    ("POST", "/api/v1/requests/{id}/release"): WRITE,
    # Comments and files (REQ-3, REQ-9, REQ-10, W9): everyone reads what their scope allows
    # (a client no internal comment); clients and staff post; viewers never.
    ("GET", "/api/v1/requests/{id}/comments"): Expect(ANY),
    ("POST", "/api/v1/requests/{id}/comments"): roles("client", "technician", "admin"),
    ("PATCH", "/api/v1/requests/{id}/comments/{comment_id}"):
        roles("client", "technician", "admin"),
    ("GET", "/api/v1/requests/{id}/attachments/{media_id}/download"): Expect(ANY),
    ("GET", "/api/v1/requests/{id}/comments/{comment_id}/attachments/{media_id}/download"):
        Expect(ANY),
    ("POST", "/api/v1/requests/{id}/approve"): roles("admin"),
    ("POST", "/api/v1/requests/{id}/deny"): roles("admin"),
    ("POST", "/api/v1/requests/{id}/cancel"): roles("client", "admin"),
    # Visits (VIS-1 to VIS-4, VIS-9, VIS-11, W10): everyone reads what their scope allows (a client
    # their organization's); technicians and admins plan and run them (the domain narrows it to
    # the people on the request or attending), only admins restore; viewers and clients never write.
    ("POST", "/api/v1/visits"): WRITE,
    ("GET", "/api/v1/visits/mine"): STAFF,
    ("GET", "/api/v1/visits/staff"): WRITE,
    ("GET", "/api/v1/visits"): Expect(ANY),
    ("GET", "/api/v1/visits/{id}"): Expect(ANY),
    ("PATCH", "/api/v1/visits/{id}"): WRITE,
    ("POST", "/api/v1/visits/{id}/cancel"): WRITE,
    ("POST", "/api/v1/visits/{id}/restore"): roles("admin"),
    ("POST", "/api/v1/visits/{id}/start"): WRITE,
    ("POST", "/api/v1/visits/{id}/stations/{station_id}/arrive"): WRITE,
    ("POST", "/api/v1/visits/{id}/stations/{station_id}/depart"): WRITE,
    ("POST", "/api/v1/visits/{id}/end"): WRITE,
    ("GET", "/api/v1/visits/{id}/field-bundle"): WRITE,  # OFF-1: the people attending prepare
    # A station's board (VIS-5, VIS-7, W11-22): everyone in scope reads (a client the shared
    # elements of an ended visit); technicians and admins write.
    ("GET", "/api/v1/visits/{id}/stations/{station_id}/elements"): Expect(ANY),
    ("POST", "/api/v1/visits/{id}/stations/{station_id}/elements"): WRITE,
    ("GET", "/api/v1/visits/{id}/stations/{station_id}/elements/{element_id}"): Expect(ANY),
    ("PUT", "/api/v1/visits/{id}/stations/{station_id}/elements/{element_id}"): WRITE,
    ("DELETE", "/api/v1/visits/{id}/stations/{station_id}/elements/{element_id}"): WRITE,
    ("POST", "/api/v1/visits/{id}/stations/{station_id}/elements/{element_id}/media"): WRITE,
    ("PATCH", "/api/v1/visits/{id}/stations/{station_id}/elements/{element_id}/media/{media_id}"):
        WRITE,
    ("DELETE", "/api/v1/visits/{id}/stations/{station_id}/elements/{element_id}/media/{media_id}"):
        WRITE,
    ("POST", "/api/v1/visits/{id}/stations/{station_id}/elements/{element_id}/config-version"):
        WRITE,
    ("POST", "/api/v1/visits/{id}/stations/{station_id}/elements/{element_id}/request"): WRITE,
    # Internal: read-model backfill (TRD §8.6), and the owner check media makes on upload.
    ("GET", "/internal/snapshot/{entity}"): service("report", "platform"),
    ("GET", "/internal/attachable"): service("media"),
    ("GET", "/internal/calibrations/due"): service("platform"),  # the weekly digest (CAL-5)
    ("POST", "/internal/labels"): service("report"),  # the QR tokens a label sheet prints
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
                ("GET", "/api/v1/stations/{id}/documents"): station["id"],
                ("GET", "/api/v1/qr/{token}"): station["qr_token"],
            },
        )
        assert await matrix.run() == []
