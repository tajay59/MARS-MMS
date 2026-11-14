"""operations' copy of organizations (TRD §3.2 "Consumes", §8.5, §8.6) and its snapshot
endpoints for read-model backfill."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from mms_common.auth.service_client import ServiceTokens
from mms_common.consumer import Outcome
from mms_common.events import Envelope, Resource
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A

from app.events import org_consumer
from app.jobs import org_backfill
from app.repo.stations import orgs

NEW_ORG = "01900000-0000-7000-8000-00000000d000"


def org_event(type_: str, version: int, name: str, org_id: str = ORG_A, **extra) -> bytes:
    data = {"org_id": org_id, "name": name, "country": "JM", "status": "active", **extra}
    if type_ == "org.updated":
        data.setdefault("changed_fields", ["name"])
    return Envelope(
        event_id=new_id(), type=type_, occurred_at=datetime.now(UTC), source="auth",
        key=org_id, aggregate_version=version, resource=Resource(type="organization", id=org_id),
        org_id=org_id, data=data,
    ).model_dump_json().encode()


async def test_org_events_keep_the_copy_and_the_station_names(ops):
    station = await ops.station()
    dead: list[str] = []

    async def dlq(raw: bytes, reason: str) -> None:
        dead.append(reason)

    processor = org_consumer.processor(ops.app.state.mongo, ops.app.state.db, dlq, ops.clock)
    renamed = org_event("org.updated", 2, "Organization A Ltd")
    assert await processor.process(renamed) is Outcome.APPLIED
    assert await processor.process(renamed) is Outcome.DUPLICATE
    # An older event that arrives late changes nothing (aggregate_version guard).
    assert await processor.process(org_event("org.updated", 1, "Old Name")) is Outcome.APPLIED
    assert await processor.process(org_event("org.created", 1, "New Org", NEW_ORG)) is (
        Outcome.APPLIED
    )
    assert await processor.process(b"{not json") is Outcome.DEAD_LETTERED
    assert len(dead) == 1

    copy = await ops.db["organizations"].find_one({"_id": ORG_A})
    assert copy["name"] == "Organization A Ltd" and copy["aggregate_version"] == 2
    detail = (await ops.http.get(f"/api/v1/stations/{station['id']}",
                                 headers=ops.bearer("tech1"))).json()
    assert detail["owner_org_name"] == "Organization A Ltd"
    assert await ops.db["organizations"].find_one({"_id": NEW_ORG}) is not None


async def test_backfill_pages_through_auths_snapshot(ops):
    pages = {
        None: {"items": [{"org_id": ORG_A, "name": "Renamed A", "country": "JM",
                          "status": "active", "aggregate_version": 5}],
               "next_after": ORG_A},
        ORG_A: {"items": [{"org_id": NEW_ORG, "name": "Org D", "country": "BB",
                           "status": "inactive", "aggregate_version": 1}],
                "next_after": None},
    }
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/service-token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        assert request.headers["Authorization"] == "Bearer t"
        after = request.url.params.get("after")
        seen.append(after)
        return httpx.Response(200, json=pages[after])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        tokens = ServiceTokens("http://auth:8000", "operations", "s", ops.clock, http)
        count = await org_backfill.backfill_orgs(ops.app.state.db, http, tokens,
                                                 "http://auth:8000")
    assert count == 2 and seen == [None, ORG_A]
    copy = await ops.db["organizations"].find_one({"_id": NEW_ORG})
    assert copy["status"] == "inactive"
    # An inactive organization can't be given a new station.
    from tests.conftest import station_body

    response = await ops.http.post("/api/v1/stations", json=station_body(owner_org_id=NEW_ORG),
                                   headers=ops.bearer("admin"))
    assert response.status_code == 422


async def test_snapshots_for_backfill(ops):
    station = await ops.station()
    model = await ops.model()
    unit = await ops.unit(model["id"])
    await ops.install(unit, station, "AT")
    for entity, key in (("stations", "station_id"), ("sensor_units", "unit_id")):
        response = await ops.http.get(f"/internal/snapshot/{entity}",
                                      headers=ops.service("report"))
        assert response.status_code == 200, response.text
        [item] = response.json()["items"]
        assert item[key] and item["aggregate_version"] >= 1
    stations = (await ops.http.get("/internal/snapshot/stations",
                                   headers=ops.service("platform"))).json()
    assert stations["items"][0]["code"] == "JM-KIN-001" and stations["next_after"] is None
    empty = await ops.http.get("/internal/snapshot/calibrations", headers=ops.service("report"))
    assert empty.json() == {"items": [], "next_after": None}


async def test_snapshots_of_models_installations_and_configuration_versions(ops):
    """The report service rebuilds its summaries' inputs from these (W19-6)."""
    station = await ops.station()
    model = await ops.model()
    unit = await ops.unit(model["id"])
    await ops.install(unit, station, "AT")
    snapshots = {}
    for entity in ("sensor_models", "installations", "config_versions"):
        response = await ops.http.get(f"/internal/snapshot/{entity}", headers=ops.service("report"))
        assert response.status_code == 200, response.text
        snapshots[entity] = response.json()["items"]
    [made] = snapshots["sensor_models"]
    assert made["model_id"] == model["id"] and made["aggregate_version"] >= 1
    [put] = snapshots["installations"]
    assert put["unit_id"] == unit["id"] and put["station_id"] == station["id"]
    assert put["serial"] == unit["serial"] and put["model_id"] == model["id"]
    assert put["installed_at"] and put["removed_at"] is None and put["parameter"] == "AT"
    assert snapshots["config_versions"] == []  # none made yet
    # only the report and platform services may read them
    denied = await ops.http.get("/internal/snapshot/installations", headers=ops.bearer("admin"))
    assert denied.status_code in (401, 403)


async def test_the_copy_keeps_the_short_name_and_external_id(ops):
    """Decision W5-8: the station import matches a site's entity to the external ID."""
    processor = org_consumer.processor(ops.app.state.mongo, ops.app.state.db, _no_dlq, ops.clock)
    event = org_event("org.created", 1, "Imported Met Service", NEW_ORG,
                      short_name="IMS", external_id="ENT" + "c" * 32)
    assert await processor.process(event) is Outcome.APPLIED
    copy = await ops.db["organizations"].find_one({"_id": NEW_ORG})
    assert (copy["short_name"], copy["external_id"]) == ("IMS", "ENT" + "c" * 32)
    assert set(await orgs.active_by_external_id(ops.db)) == {"ENT" + "c" * 32}


async def _no_dlq(raw: bytes, reason: str) -> None:
    raise AssertionError(reason)
