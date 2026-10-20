"""QR codes (QR-1 to QR-4, QR-7; rules 3, 4)."""

from __future__ import annotations

import pytest
from mms_common.testing.seed import SEED_USERS


async def _resolve(ops, who: str, token: str):
    return await ops.http.get(f"/api/v1/qr/{token}", headers=ops.bearer(who))


@pytest.mark.req("QR-2")
@pytest.mark.req("QR-3")
async def test_staff_and_the_owning_client_resolve_a_token(ops):
    station = await ops.station()
    for who, view in (("tech1", "staff"), ("viewer", "staff"), ("client_a1", "client")):
        response = await _resolve(ops, who, station["qr_token"])
        assert response.status_code == 200, response.text
        assert response.json() == {
            "station_id": station["id"], "code": station["code"], "name": station["name"],
            "view": view,
        }


@pytest.mark.req("QR-4")
async def test_another_organizations_client_gets_not_found(ops):
    station = await ops.station()
    response = await _resolve(ops, "client_b1", station["qr_token"])
    assert response.status_code == 404
    assert station["code"] not in response.text


async def test_an_unknown_token_and_no_login(ops):
    assert (await _resolve(ops, "tech1", "nope")).status_code == 404
    response = await ops.http.get("/api/v1/qr/whatever")
    assert response.status_code == 401


@pytest.mark.req("QR-1")
async def test_every_station_has_its_own_token(ops):
    first = await ops.station()
    second = await ops.station(code="JM-KIN-002")
    assert first["qr_token"] != second["qr_token"]
    # clients never receive the token (rule 6)
    detail = await ops.http.get(f"/api/v1/stations/{first['id']}", headers=ops.bearer("client_a1"))
    assert detail.json()["qr_token"] is None


@pytest.mark.req("QR-7")
async def test_regenerating_revokes_the_old_token(ops):
    station = await ops.station()
    old = station["qr_token"]
    response = await ops.http.post(
        f"/api/v1/stations/{station['id']}/qr/regenerate", headers=ops.bearer("admin")
    )
    assert response.status_code == 200, response.text
    new = response.json()["qr_token"]
    assert new and new != old and response.json()["version"] == 2

    assert (await _resolve(ops, "tech1", new)).status_code == 200
    gone = await _resolve(ops, "tech1", old)
    assert gone.status_code == 410 and gone.json()["code"] == "qr_revoked"
    assert (await _resolve(ops, "client_a1", old)).status_code == 410
    # a client of another organization still learns nothing
    assert (await _resolve(ops, "client_b1", old)).status_code == 404

    [event] = await ops.outbox("qr.regenerated")
    assert event.key == station["id"] and event.actor.user_id == SEED_USERS["admin"].id
    assert event.data == {
        "station_id": station["id"], "code": station["code"], "org_id": station["owner_org_id"]
    }
    assert old not in str(event.model_dump(mode="json")) and new not in str(
        event.model_dump(mode="json")
    )


async def test_regenerating_twice_revokes_both(ops):
    station = await ops.station()
    tokens = [station["qr_token"]]
    for _ in range(2):
        response = await ops.http.post(
            f"/api/v1/stations/{station['id']}/qr/regenerate", headers=ops.bearer("admin")
        )
        tokens.append(response.json()["qr_token"])
    assert [(await _resolve(ops, "admin", t)).status_code for t in tokens] == [410, 410, 200]


async def test_only_admins_regenerate_and_only_known_stations(ops):
    station = await ops.station()
    for who in ("tech1", "viewer", "client_a1"):
        response = await ops.http.post(
            f"/api/v1/stations/{station['id']}/qr/regenerate", headers=ops.bearer(who)
        )
        assert response.status_code == 403
    missing = await ops.http.post(
        "/api/v1/stations/01900000-0000-7000-8000-0000000000ff/qr/regenerate",
        headers=ops.bearer("admin"),
    )
    assert missing.status_code == 404


@pytest.mark.req("QR-6")
async def test_report_reads_labels_with_its_service_token(ops):
    first = await ops.station()
    second = await ops.station(code="JM-KIN-002")
    missing = "01900000-0000-7000-8000-0000000000ff"
    asked = [second["id"], missing, first["id"], second["id"]]
    headers = {"Authorization": f"Bearer {ops.issuer.service_token('report')}"}
    response = await ops.http.post("/internal/labels", json={"station_ids": asked}, headers=headers)
    assert response.status_code == 200, response.text
    assert [r["code"] for r in response.json()] == ["JM-KIN-002", "JM-KIN-001"]
    assert response.json()[1]["qr_token"] == first["qr_token"]
    # nobody else reads tokens this way
    for who in ("admin", "client_a1"):
        denied = await ops.http.post(
            "/internal/labels", json={"station_ids": [first["id"]]}, headers=ops.bearer(who)
        )
        assert denied.status_code in (401, 403)
    empty = await ops.http.post("/internal/labels", json={"station_ids": []}, headers=headers)
    assert empty.status_code == 422
