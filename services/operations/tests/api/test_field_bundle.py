"""The field bundle over the real app (PRD OFF-1; TRD §3.2.1, §7.1; AFD J5 step 4; W13-9;
rules 3 to 6): who may prepare a visit and when, what the bundle holds and what it must not,
and the record of where a visit is prepared."""

from __future__ import annotations

from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import SEED_USERS

from app.domain.visits import bundle as rules
from tests.api.test_config_and_owner_check import new_version
from tests.api.test_documents import make_doc
from tests.api.test_visit_board import added, two_techs
from tests.api.test_visits import TECH1, a_request, move, plan

DEVICE = "01990000-0000-7000-8000-000000000001"
OTHER_DEVICE = "01990000-0000-7000-8000-000000000002"


async def prepare(ops, who: str, visit, device: str = DEVICE):
    return await ops.http.get(
        f"/api/v1/visits/{visit['id']}/field-bundle", params={"device_id": device},
        headers=ops.bearer(who),
    )


async def prepared(ops, who: str, visit, device: str = DEVICE) -> dict[str, Any]:
    r = await prepare(ops, who, visit, device)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


async def read(ops, who: str, visit) -> dict[str, Any]:
    r = await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer(who))
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


@pytest.mark.req("OFF-1")
async def test_the_bundle_holds_the_request_the_stations_and_their_boards(ops):
    visit, request, [one, two] = await two_techs(ops)
    note = await added(ops, "tech2", visit, one, title="Rust on the mast")
    bundle = await prepared(ops, "tech1", visit)

    assert bundle["bundle_version"] == rules.BUNDLE_VERSION == 1
    assert bundle["prepared_at"]
    assert bundle["visit"]["id"] == visit["id"]
    assert bundle["request"]["id"] == request["id"] and bundle["request"]["title"]
    assert [s["station"]["id"] for s in bundle["stations"]] == [one["id"], two["id"]]
    first, second = bundle["stations"]
    assert [e["id"] for e in first["board"]] == [note["id"]] and second["board"] == []
    assert first["can_add"] is True
    # Staff-only fields a phone needs offline: the label's token
    assert first["station"]["qr_token"] == one["qr_token"]
    assert first["calibrations"] == [] and first["config_version"] is None
    assert first["documents"] == {"station": [], "models": []}


@pytest.mark.req("OFF-1")
async def test_the_latest_configuration_files_are_required_and_documents_are_not(ops):
    visit, _, [one, two] = await two_techs(ops)
    await new_version(ops, one["id"], ["old.json"], content="a")
    newest, _, files = await new_version(ops, one["id"], ["logger.cfg", "mast.json"], content="b")
    assert newest.status_code == 201, newest.text
    made, _ = await make_doc(ops, two["id"])
    assert made.status_code == 201, made.text

    bundle = await prepared(ops, "tech1", visit)
    assert bundle["stations"][0]["config_version"]["version"] == 2
    config = [f for f in bundle["files"] if f["kind"] == "config"]
    assert {f["media_id"] for f in config} == set(files)  # the newest version only
    assert all(f["required"] and f["station_id"] == one["id"] and f["sha256"] for f in config)
    documents = [f for f in bundle["files"] if f["kind"] == "document"]
    assert [f["media_id"] for f in documents] == [made.json()["media_id"]]
    assert documents[0]["required"] is False and documents[0]["station_id"] == two["id"]
    ids = [f["media_id"] for f in bundle["files"]]
    assert len(ids) == len(set(ids))  # each file once


@pytest.mark.req("OFF-1")
async def test_preparing_records_where_the_visit_is_prepared_with_its_event(ops):
    visit, _, _ = await two_techs(ops)
    await prepared(ops, "tech1", visit)
    after = await read(ops, "tech1", visit)
    assert [(p["user"]["id"], p["user"]["name"]) for p in after["prepared_on"]] == [
        (TECH1, SEED_USERS["tech1"].name)]
    assert after["version"] == visit["version"]  # not a change to the visit

    [event] = await ops.outbox("visit.prepared")
    assert event.data["user_id"] == TECH1 and event.data["device_id"] == DEVICE
    assert event.key == visit["request_id"]


@pytest.mark.req("OFF-1")
async def test_preparing_again_from_the_same_phone_replaces_its_entry(ops):
    visit, _, _ = await two_techs(ops)
    await prepared(ops, "tech1", visit)
    await prepared(ops, "tech1", visit)
    await prepared(ops, "tech1", visit, OTHER_DEVICE)
    await prepared(ops, "tech2", visit)
    assert len((await read(ops, "tech1", visit))["prepared_on"]) == 3
    assert len(await ops.outbox("visit.prepared")) == 4  # each time is audited


@pytest.mark.req("OFF-1")
async def test_a_planned_visit_can_be_prepared_before_it_starts(ops):
    request, stations = await a_request(ops)
    r = await plan(ops, "tech1", request, stations)
    assert r.status_code == 201, r.text
    bundle = await prepared(ops, "tech1", r.json())
    assert bundle["visit"]["status"] == "planned"


@pytest.mark.req("OFF-1")
async def test_only_the_people_attending_and_admins_prepare(ops):
    request, stations = await a_request(ops, staff=("tech1", "tech2"))
    visit = (await plan(ops, "tech1", request, stations, staff=(TECH1,))).json()
    other = await prepare(ops, "tech2", visit)
    assert other.status_code == 403 and other.json()["code"] == "not_attending"
    assert (await prepare(ops, "admin", visit)).status_code == 200
    assert (await prepare(ops, "tech1", visit)).status_code == 200


@pytest.mark.req("NFR-6")
async def test_viewers_and_clients_do_not_prepare(ops):
    visit, _, _ = await two_techs(ops)
    assert (await prepare(ops, "viewer", visit)).status_code == 403
    assert (await prepare(ops, "client_a1", visit)).status_code in (403, 404)
    assert await ops.outbox("visit.prepared") == []


@pytest.mark.req("OFF-1")
async def test_an_ended_visit_is_not_prepared(ops):
    visit, _, _ = await two_techs(ops)
    ended = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert ended.status_code == 200, ended.text
    r = await prepare(ops, "tech1", visit)
    assert r.status_code == 409 and r.json()["code"] == "visit_not_preparable"
    assert await ops.outbox("visit.prepared") == []


@pytest.mark.req("OFF-1")
async def test_a_cancelled_visit_is_not_prepared(ops):
    request, stations = await a_request(ops)
    planned = (await plan(ops, "tech1", request, stations)).json()
    cancelled = await move(ops, "tech1", planned["id"], "cancel", reason="Wrong day")
    assert cancelled.status_code == 200, cancelled.text
    assert (await prepare(ops, "tech1", planned)).status_code == 409
    assert await ops.outbox("visit.prepared") == []


async def test_the_device_id_is_required_and_checked(ops):
    visit, _, _ = await two_techs(ops)
    url = f"/api/v1/visits/{visit['id']}/field-bundle"
    assert (await ops.http.get(url, headers=ops.bearer("tech1"))).status_code == 422
    r = await ops.http.get(url, params={"device_id": "not-an-id"}, headers=ops.bearer("tech1"))
    assert r.status_code == 422


async def test_a_visit_that_is_not_there_is_not_found(ops):
    r = await ops.http.get(
        f"/api/v1/visits/{new_id()}/field-bundle", params={"device_id": DEVICE},
        headers=ops.bearer("tech1"),
    )
    assert r.status_code == 404


async def test_a_client_never_sees_who_prepared_a_visit(ops):
    visit, _, _ = await two_techs(ops)
    await prepared(ops, "tech1", visit)
    mine = await read(ops, "client_a1", visit)
    assert mine["prepared_on"] == []
