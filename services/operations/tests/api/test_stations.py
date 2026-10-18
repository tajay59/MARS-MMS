"""Stations API (STN-1 to STN-6, ORG-2, ORG-3; rules 3, 4, 6)."""

from __future__ import annotations

import pytest
from mms_common.testing.leak import find_leaks
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS

from tests.conftest import ORG_C, station_body


@pytest.mark.req("STN-1")
async def test_staff_create_a_station_and_it_is_announced(ops):
    station = await ops.station()
    assert station["code"] == "JM-KIN-001"
    assert station["owner_org_name"] == "Organization A"
    assert station["latitude"] == 17.97 and station["longitude"] == -76.79
    assert station["status"] == "operational"
    assert station["qr_token"] and len(station["qr_token"]) >= 20
    assert station["installed"] == [] and station["version"] == 1

    [event] = await ops.outbox("station.created")
    assert event.key == station["id"] and event.org_id == ORG_A
    assert event.data["code"] == "JM-KIN-001" and event.data["via"] == "api"
    assert event.actor.user_id == SEED_USERS["tech1"].id
    assert event.audit["after"]["owner_org_id"] == ORG_A


@pytest.mark.parametrize(("fields", "code"), [
    ({"owner_org_id": ORG_C}, "org_inactive"),
    ({"owner_org_id": "01900000-0000-7000-8000-0000000000ff"}, "org_inactive"),
    ({"time_zone": "Mars/Base"}, "invalid_time_zone"),
    ({"country": "XX"}, "invalid_country"),
    ({"code": "has space"}, "invalid_code"),
    ({"parameters": ["air temp"]}, "invalid_parameter"),
])
async def test_create_checks(ops, fields, code):
    response = await ops.http.post("/api/v1/stations", json=station_body(**fields),
                                   headers=ops.bearer("admin"))
    assert response.status_code == 422, response.text
    assert response.json()["code"] == code


async def test_codes_are_unique(ops):
    await ops.station()
    response = await ops.http.post(
        "/api/v1/stations", json=station_body(code="jm-kin-001"), headers=ops.bearer("admin")
    )
    assert response.status_code == 409
    assert response.json()["code"] == "code_taken"


@pytest.mark.req("ORG-3")
async def test_clients_list_only_their_organizations_stations(ops):
    await ops.station(code="A-1")
    await ops.station(code="A-2")
    await ops.station(code="B-1", owner_org_id=ORG_B, country="TT",
                      time_zone="America/Port_of_Spain")
    seen = {}
    for who in ("client_a1", "client_b1", "viewer"):
        response = await ops.http.get("/api/v1/stations", headers=ops.bearer(who))
        assert response.status_code == 200
        seen[who] = [s["code"] for s in response.json()["items"]]
    assert seen == {"client_a1": ["A-1", "A-2"], "client_b1": ["B-1"],
                    "viewer": ["A-1", "A-2", "B-1"]}
    # A client can't widen their scope with a filter.
    response = await ops.http.get(f"/api/v1/stations?org_id={ORG_B}",
                                  headers=ops.bearer("client_a1"))
    assert response.json()["items"] == []


@pytest.mark.req("STN-5")
async def test_filters_search_and_paging(ops):
    await ops.station(code="A-1", name="Kingston Harbour", parameters=["AT", "RAIN"])
    await ops.station(code="A-2", name="Montego Bay", status="offline", type="Aviation",
                      parameters=["AT"])
    await ops.station(code="B-1", name="Port of Spain", owner_org_id=ORG_B, country="TT",
                      time_zone="America/Port_of_Spain", parameters=["WS"])

    async def codes(query: str) -> list[str]:
        response = await ops.http.get(f"/api/v1/stations?{query}", headers=ops.bearer("tech1"))
        assert response.status_code == 200, response.text
        return [s["code"] for s in response.json()["items"]]

    assert await codes("country=TT") == ["B-1"]
    assert await codes("status=offline") == ["A-2"]
    assert await codes("type=Aviation") == ["A-2"]
    assert await codes("parameter=rain") == ["A-1"]
    assert await codes(f"org_id={ORG_A}") == ["A-1", "A-2"]
    assert await codes("q=bay") == ["A-2"]
    assert await codes("q=.*") == []  # typed input, never a pattern (rule 12)

    first = (await ops.http.get("/api/v1/stations?limit=2", headers=ops.bearer("tech1"))).json()
    assert [s["code"] for s in first["items"]] == ["A-1", "A-2"]
    assert first["total"] == 3 and first["next_after"] == "A-2"
    assert await codes("limit=2&after=A-2") == ["B-1"]


@pytest.mark.req("STN-5")
async def test_facets(ops):
    await ops.station(code="A-1", type="Synoptic")
    await ops.station(code="B-1", owner_org_id=ORG_B, country="TT", type="Coastal",
                      time_zone="America/Port_of_Spain", parameters=["WS"])
    staff = (await ops.http.get("/api/v1/stations/facets", headers=ops.bearer("viewer"))).json()
    assert staff["countries"] == ["JM", "TT"]
    assert staff["types"] == ["Coastal", "Synoptic"]
    assert staff["parameters"] == ["AT", "RAIN", "RH", "WS"]
    assert [o["name"] for o in staff["organizations"]] == ["Organization A", "Organization B"]
    client = (await ops.http.get("/api/v1/stations/facets",
                                 headers=ops.bearer("client_b1"))).json()
    assert client["countries"] == ["TT"] and client["organizations"] == []


@pytest.mark.req("STN-6")
async def test_another_organizations_station_is_not_found(ops):
    station = await ops.station()
    for path in (f"/api/v1/stations/{station['id']}",
                 f"/api/v1/stations/{station['id']}/installations"):
        response = await ops.http.get(path, headers=ops.bearer("client_b1"))
        assert response.status_code == 404  # rule 4: not 403


@pytest.mark.req("STN-6")
async def test_clients_see_a_summary_without_staff_fields_or_contacts(ops):
    station = await ops.station()
    response = await ops.http.get(f"/api/v1/stations/{station['id']}",
                                  headers=ops.bearer("client_a1"))
    assert response.status_code == 200
    body = response.json()
    assert body["qr_token"] is None and body["current_config_version"] is None
    assert body["name"] == "Kingston Harbour"
    assert find_leaks(body, own_ids=frozenset({SEED_USERS["client_a1"].id, ORG_A})) == []


@pytest.mark.req("STN-1")
async def test_staff_edit_a_station(ops):
    station = await ops.station()
    response = await ops.http.patch(
        f"/api/v1/stations/{station['id']}",
        json={"version": 1, "name": "Kingston Port", "status": "degraded",
              "latitude": 18.0, "longitude": -76.8, "logger": {"model": "CR1000X"},
              "install_date": "2019-03-14"},
        headers=ops.bearer("admin"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Kingston Port" and body["status"] == "degraded"
    assert body["latitude"] == 18.0 and body["logger"]["model"] == "CR1000X"
    assert body["version"] == 2
    [event] = await ops.outbox("station.updated")
    assert event.data["changed_fields"] == ["install_date", "location", "logger", "name",
                                            "status"]
    assert event.audit["before"]["name"] == "Kingston Harbour"
    assert event.aggregate_version == 2


async def test_an_edit_with_a_stale_version_is_refused(ops):
    station = await ops.station()
    path = f"/api/v1/stations/{station['id']}"
    ok = await ops.http.patch(path, json={"version": 1, "name": "One"},
                              headers=ops.bearer("tech1"))
    assert ok.status_code == 200
    stale = await ops.http.patch(path, json={"version": 1, "name": "Two"},
                                 headers=ops.bearer("tech2"))
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict"


@pytest.mark.req("ORG-2")
async def test_the_owner_never_changes(ops):
    station = await ops.station()
    response = await ops.http.patch(
        f"/api/v1/stations/{station['id']}", json={"version": 1, "owner_org_id": ORG_B},
        headers=ops.bearer("admin"),
    )
    assert response.status_code == 422  # not a field of an edit (BSD B5)


async def test_an_edit_cannot_take_a_code_already_used(ops):
    await ops.station(code="A-1")
    other = await ops.station(code="A-2")
    response = await ops.http.patch(f"/api/v1/stations/{other['id']}",
                                    json={"version": 1, "code": "a-1"},
                                    headers=ops.bearer("admin"))
    assert response.status_code == 409


async def test_edits_need_both_coordinates_and_keep_required_fields(ops):
    station = await ops.station()
    path = f"/api/v1/stations/{station['id']}"
    half = await ops.http.patch(path, json={"version": 1, "latitude": 1.0},
                                headers=ops.bearer("admin"))
    assert half.status_code == 422
    empty = await ops.http.patch(path, json={"version": 1, "name": None},
                                 headers=ops.bearer("admin"))
    assert empty.status_code == 422


async def test_an_unchanged_edit_writes_nothing(ops):
    station = await ops.station()
    response = await ops.http.patch(f"/api/v1/stations/{station['id']}",
                                    json={"version": 1, "name": "Kingston Harbour"},
                                    headers=ops.bearer("admin"))
    assert response.status_code == 200 and response.json()["version"] == 1
    assert await ops.outbox("station.updated") == []


async def test_api_responses_are_never_cached(ops):
    response = await ops.http.get("/api/v1/stations", headers=ops.bearer("tech1"))
    assert response.headers["cache-control"] == "no-store"
