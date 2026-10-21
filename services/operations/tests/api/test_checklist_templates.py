"""Checklist templates, W10 (PRD VIS-8; W10-11, W10-12), over the real app: admins write, staff
read, every edit is a new version, one active template per station type or sensor model, and which
items a station is given."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from mms_common.ids import new_id
from pymongo import AsyncMongoClient

from app import cli
from tests.conftest import seed_orgs

URL = "/api/v1/checklist-templates"
ITEMS = [{"label": "Mast: guy wires, corrosion"}, {"label": "Battery voltage", "help": "Note it"}]


async def create(ops, who: str = "admin", **fields: Any):
    body = {"name": "Site visit", "station_type": "Synoptic", "items": ITEMS, **fields}
    return await ops.http.post(URL, json=body, headers=ops.bearer(who))


async def patch(ops, family_id: str, who: str = "admin", **fields: Any):
    return await ops.http.patch(f"{URL}/{family_id}", json=fields, headers=ops.bearer(who))


@pytest.mark.req("VIS-8")
async def test_an_admin_creates_a_template_and_staff_read_it(ops):
    r = await create(ops)
    assert r.status_code == 201, r.text
    made = r.json()
    assert made["version"] == 1 and made["is_current"] and made["active"]
    assert made["station_type"] == "Synoptic" and made["sensor_model_id"] is None
    assert [i["label"] for i in made["items"]] == ["Mast: guy wires, corrosion", "Battery voltage"]
    assert all(i["id"] for i in made["items"]) and made["items"][1]["help"] == "Note it"
    for who in ("tech1", "viewer", "admin"):
        listed = (await ops.http.get(URL, headers=ops.bearer(who))).json()["items"]
        assert [t["id"] for t in listed] == [made["id"]]
        one = await ops.http.get(f"{URL}/{made['id']}", headers=ops.bearer(who))
        assert one.status_code == 200 and one.json()["name"] == "Site visit"


@pytest.mark.req("VIS-8")
async def test_only_admins_write_and_clients_never_read(ops):
    assert (await create(ops, "tech1")).status_code == 403
    assert (await create(ops, "viewer")).status_code == 403
    assert (await create(ops, "client_a1")).status_code == 403
    made = (await create(ops)).json()
    assert (await patch(ops, made["id"], "tech1", version=1, name="x")).status_code == 403
    assert (await ops.http.get(URL, headers=ops.bearer("client_a1"))).status_code == 403
    assert (await ops.http.get(f"{URL}/{made['id']}",
                               headers=ops.bearer("client_a1"))).status_code == 403
    assert (await ops.http.get(f"{URL}/{new_id()}", headers=ops.bearer("tech1"))).status_code == 404


@pytest.mark.req("VIS-8")
async def test_a_template_needs_a_name_items_and_exactly_one_scope(ops):
    for fields in (
        {"name": " "}, {"items": []}, {"items": [{"label": " "}]},
        {"station_type": None},  # neither
        {"sensor_model_id": new_id()},  # both
        {"station_type": None, "sensor_model_id": new_id()},  # a model that does not exist
    ):
        r = await create(ops, **fields)
        assert r.status_code == 422, (fields, r.text)


@pytest.mark.req("VIS-8")
async def test_one_active_template_per_station_type_ignoring_case(ops):
    assert (await create(ops)).status_code == 201
    again = await create(ops, name="Another", station_type=" synoptic ")
    assert again.status_code == 409 and again.json()["code"] == "template_exists"
    assert (await create(ops, name="Other", station_type="Radar")).status_code == 201


@pytest.mark.req("VIS-8")
async def test_saving_writes_the_next_version_and_keeps_the_old_one(ops):
    made = (await create(ops)).json()
    first_ids = [i["id"] for i in made["items"]]
    items = [
        {"id": first_ids[0], "label": "Mast: guy wires, corrosion, grounding"},
        {"id": first_ids[1], "label": "Battery voltage", "help": "Note it"},
        {"label": "Datalogger clock"},
    ]
    r = await patch(ops, made["id"], version=1, items=items, name="Site visit (2026)")
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["version"] == 2 and new["id"] == made["id"] and new["name"] == "Site visit (2026)"
    assert [i["id"] for i in new["items"][:2]] == first_ids and new["items"][2]["id"]
    old = (await ops.http.get(f"{URL}/{made['id']}", params={"version": 1},
                              headers=ops.bearer("tech1"))).json()
    assert old["version"] == 1 and old["is_current"] is False and old["name"] == "Site visit"
    assert old["items"][0]["label"] == "Mast: guy wires, corrosion"  # never touched
    current = (await ops.http.get(f"{URL}/{made['id']}", headers=ops.bearer("tech1"))).json()
    assert current["version"] == 2 and current["is_current"]
    listed = (await ops.http.get(URL, headers=ops.bearer("tech1"))).json()["items"]
    assert [t["version"] for t in listed] == [2]
    gone = await ops.http.get(f"{URL}/{made['id']}", params={"version": 9},
                              headers=ops.bearer("tech1"))
    assert gone.status_code == 404


@pytest.mark.req("VIS-8")
async def test_a_stale_version_is_refused_and_no_change_writes_nothing(ops):
    made = (await create(ops)).json()
    ok = await patch(ops, made["id"], version=1, name="Renamed")
    assert ok.status_code == 200 and ok.json()["version"] == 2
    stale = await patch(ops, made["id"], version=1, name="Again")
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    same = await patch(ops, made["id"], version=2, name="Renamed")
    assert same.status_code == 200 and same.json()["version"] == 2
    bad = await patch(ops, made["id"], version=2, items=[{"label": " "}])
    assert bad.status_code == 422


@pytest.mark.req("VIS-8")
async def test_an_inactive_template_is_kept_but_not_given_and_cannot_clash_when_reactivated(ops):
    made = (await create(ops)).json()
    off = await patch(ops, made["id"], version=1, active=False)
    assert off.status_code == 200 and off.json()["active"] is False and off.json()["version"] == 2
    assert (await ops.http.get(URL, headers=ops.bearer("tech1"))).json()["items"] == []
    # Only an admin can ask for the inactive ones
    assert (await ops.http.get(URL, params={"all": True},
                               headers=ops.bearer("tech1"))).json()["items"] == []
    everything = (await ops.http.get(URL, params={"all": True},
                                     headers=ops.bearer("admin"))).json()["items"]
    assert [t["id"] for t in everything] == [made["id"]]
    # The type is free again, and the old one cannot come back beside the new one
    assert (await create(ops, name="Replacement")).status_code == 201
    back = await patch(ops, made["id"], version=2, active=True)
    assert back.status_code == 409 and back.json()["code"] == "template_exists"


@pytest.mark.req("VIS-8")
async def test_a_sensor_model_add_on_is_one_per_model(ops):
    model = await ops.model()
    r = await create(ops, name="HMP155 checks", station_type=None, sensor_model_id=model["id"])
    assert r.status_code == 201, r.text
    assert r.json()["sensor_model_name"] == "Vaisala HMP155"
    again = await create(ops, name="Second", station_type=None, sensor_model_id=model["id"])
    assert again.status_code == 409


@pytest.mark.req("VIS-8")
async def test_a_station_is_given_its_type_template_and_an_add_on_for_each_installed_model(ops):
    station = await ops.station()  # type "Synoptic"
    other = await ops.model(manufacturer="Texas", model="TB4", parameters=["RAIN"])
    hmp = await ops.model()
    unit_a = await ops.unit(hmp["id"], serial="H-1")
    unit_b = await ops.unit(hmp["id"], serial="H-2")
    unit_c = await ops.unit(other["id"], serial="T-1")
    assert (await ops.install(unit_a, station, "AT")).status_code == 200
    assert (await ops.install(unit_b, station, "RH")).status_code == 200
    assert (await ops.install(unit_c, station, "RAIN")).status_code == 200
    spare = await ops.model(manufacturer="Campbell", model="CR1000", parameters=[])
    await ops.unit(spare["id"], serial="C-1")  # in stock: not installed here
    station_template = (await create(ops)).json()
    await create(ops, name="HMP155", station_type=None, sensor_model_id=hmp["id"],
                 items=[{"label": "Radiation shield clean"}])
    await create(ops, name="Rain", station_type=None, sensor_model_id=other["id"],
                 items=[{"label": "Funnel clear"}])
    await create(ops, name="Logger", station_type=None, sensor_model_id=spare["id"],
                 items=[{"label": "Never given"}])

    r = await ops.http.get(f"{URL}/resolve", params={"station_id": station["id"]},
                           headers=ops.bearer("tech1"))
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["station_type"] == "Synoptic"
    assert [(i["group"], i["label"]) for i in got["items"]] == [
        ("Station", "Mast: guy wires, corrosion"), ("Station", "Battery voltage"),
        ("Texas TB4", "Funnel clear"), ("Vaisala HMP155", "Radiation shield clean"),
    ]
    assert got["items"][0]["template_id"] == station_template["id"]
    assert got["items"][0]["template_version"] == 1


@pytest.mark.req("VIS-8")
async def test_resolve_with_nothing_to_give_and_for_a_missing_station(ops):
    station = await ops.station(type="Unusual")
    r = await ops.http.get(f"{URL}/resolve", params={"station_id": station["id"]},
                           headers=ops.bearer("viewer"))
    assert r.status_code == 200 and r.json()["items"] == []
    gone = await ops.http.get(f"{URL}/resolve", params={"station_id": new_id()},
                              headers=ops.bearer("tech1"))
    assert gone.status_code == 404
    client = await ops.http.get(f"{URL}/resolve", params={"station_id": station["id"]},
                                headers=ops.bearer("client_a1"))
    assert client.status_code == 403


def test_the_starter_checklist_is_created_once_by_the_command(mongo_uri, monkeypatch, capsys):
    db_name = f"cli_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("OPS_MONGO_URI", mongo_uri)
    monkeypatch.setenv("OPS_MONGO_DB", db_name)

    async def rows() -> list[dict[str, Any]]:
        client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
        try:
            return [d async for d in client[db_name]["checklist_templates"].find()]
        finally:
            await client.close()

    async def drop() -> None:
        client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
        await seed_orgs(client[db_name])
        await client.drop_database(db_name)
        await client.close()

    try:
        assert cli.main(["seed-checklists"]) == 0
        assert "12 items" in capsys.readouterr().out
        [row] = asyncio.run(rows())
        assert row["station_type"] == "AWS" and row["version"] == 1 and row["is_current"]
        assert len(row["items"]) == 12 and all(i["id"] for i in row["items"])
        assert cli.main(["seed-checklists"]) == 0
        assert "nothing changed" in capsys.readouterr().out
        assert len(asyncio.run(rows())) == 1
        assert cli.main(["seed-checklists", "--station-type", "Radar"]) == 0
        assert len(asyncio.run(rows())) == 2
    finally:
        asyncio.run(drop())
