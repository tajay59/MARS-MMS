"""The station import from the existing system's `site` export (decision W5-8; TRD T4).
The sites and devices here are made up: the repo is public."""

from __future__ import annotations

import json
from datetime import date

import pytest
from mms_common.testing.seed import ORG_A, ORG_B

from app.domain.stations import importing
from app.domain.stations.importing import STATIONS

TODAY = date(2026, 10, 18)
ENT_A = "ENT" + "a" * 32
ENT_B = "ENT" + "b" * 32
ORGS_BY_EXTERNAL = {
    ENT_A: {"_id": ORG_A, "name": "Organization A", "country": "JM", "external_id": ENT_A},
    ENT_B: {"_id": ORG_B, "name": "Organization B", "country": "TT", "external_id": ENT_B},
}


def param(code: str, *, base_only: bool = False) -> dict:
    p = {"base": code, "unitname": "Unit", "unitID": 0, "units": "u", "index": 0, "name": code}
    return p if base_only else {**p, "param": code}


def device(n: int, name: str, *, tz: str = "America/Jamaica", params=("RAIN", "BV")) -> dict:
    return {
        "account": "ACC" + "0" * 32, "name": name, "longname": f"{name.title()} Station",
        "stationid": f"9000{n}", "project": "", "description": "",
        "lat": 18.0 + n / 100, "lon": -77.0 - n / 100, "timezone": tz,
        "processor": "aws", "resolution": "5min",
        "params": [param(p) for p in params], "id": f"DEV{n:032x}", "dashboard": [],
    }


def sites() -> list[dict]:
    return [
        {"_id": {"$oid": "1" * 24}, "type": "site", "id": "SITE" + "1" * 32, "name": "SITE ONE",
         "lat": 18.0, "lon": -77.0, "entity": ENT_A, "radius": 200, "enabled": True,
         "devices": [device(1, "HILLTOP"), device(2, "RIVERSIDE", params=("WL", "ITEMP"))]},
        {"_id": {"$oid": "2" * 24}, "type": "site", "id": "SITE" + "2" * 32, "name": "SITE TWO",
         "lat": 10.6, "lon": -61.5, "entity": ENT_B, "radius": 200, "enabled": False,
         "devices": [device(3, "BAYFRONT", tz="America/Port_of_Spain")]},
        {"_id": {"$oid": "3" * 24}, "type": "site", "id": "SITE" + "3" * 32, "name": "EMPTY",
         "entity": ENT_A, "devices": []},
    ]


def plan_sites(docs, **existing):
    tables = importing.read_file("sites.json", json.dumps(docs).encode())
    return importing.plan(
        tables[STATIONS], [], orgs_by_key={}, orgs_by_external=ORGS_BY_EXTERNAL,
        existing_codes=existing.get("codes", {}),
        existing_external_ids=existing.get("external_ids", {}),
        models_by_key={}, units_by_model_serial={}, today=TODAY,
    )


@pytest.mark.req("STN-8")
def test_each_device_becomes_a_station_owned_through_the_site_entity():
    plan = plan_sites(sites())
    assert plan.errors == [] and plan.skipped == []
    by_code = {row.fields["code"]: row.fields for row in plan.stations}
    assert list(by_code) == ["HILLTOP", "RIVERSIDE", "BAYFRONT"]
    hilltop = by_code["HILLTOP"]
    assert hilltop["name"] == "Hilltop Station"
    assert hilltop["external_id"] == f"DEV{1:032x}"
    assert (hilltop["owner_org_id"], hilltop["country"]) == (ORG_A, "JM")  # country from the org
    assert hilltop["time_zone"] == "America/Jamaica"
    assert hilltop["location"]["coordinates"] == [-77.01, 18.01]
    assert hilltop["parameters"] == ["RAIN", "BV"]
    assert hilltop["status"] == "operational"
    bayfront = by_code["BAYFRONT"]
    assert (bayfront["owner_org_id"], bayfront["country"]) == (ORG_B, "TT")
    assert bayfront["status"] == "decommissioned"  # its site is disabled


def test_only_the_mapped_fields_are_read():
    [row] = importing.read_sites(json.dumps(sites()[:1]).encode())[:1]
    assert set(row[1]) == {
        "code", "name", "externalid", "organizationexternalid", "timezone", "latitude",
        "longitude", "parameters", "status",
    }


def test_json_lines_and_the_base_parameter_are_read():
    doc = sites()[0]
    doc["devices"][0]["params"] = [param("RAIN", base_only=True)]
    lines = "\n".join(json.dumps(d) for d in [doc, sites()[1]]).encode()
    table = importing.read_file("sites.json", lines)[STATIONS]
    assert [n for n, _ in table] == [1, 2, 3]
    assert table[0][1]["parameters"] == "RAIN"


@pytest.mark.req("STN-8")
def test_a_device_with_many_parameters_imports_up_to_the_limit():
    codes = [f"PARAMETER_{n:02}" for n in range(22)]  # joins to over 200 characters
    docs = sites()
    docs[0]["devices"][0]["params"] = [param(c) for c in codes]
    docs[0]["devices"][1]["params"] = [param(f"P{n}") for n in range(41)]
    plan = plan_sites(docs)
    assert [(p.row, p.column) for p in plan.errors] == [(2, "parameters")]
    assert "at most 40 parameters" in plan.errors[0].message
    hilltop = next(r for r in plan.stations if r.fields["code"] == "HILLTOP")
    assert hilltop.fields["parameters"] == codes


def test_an_unknown_entity_or_a_repeated_device_is_an_error():
    docs = sites()
    docs[0]["entity"] = "ENT-NOT-IMPORTED"
    docs[1]["devices"].append({**device(4, "COPY"), "id": f"DEV{3:032x}"})
    plan = plan_sites(docs)
    assert {(p.row, p.column) for p in plan.errors} == {
        (1, "organization"), (2, "organization"), (4, "external_id"),
    }
    assert "import the organizations first" in plan.errors[0].message
    assert [row.fields["code"] for row in plan.stations] == ["BAYFRONT"]


def test_devices_already_imported_are_skipped():
    plan = plan_sites(sites(), external_ids={f"DEV{1:032x}": {"code": "OLD-NAME"}},
                      codes={"BAYFRONT": {"_id": "x"}})
    assert [(p.row, p.column) for p in plan.skipped] == [(1, "external_id"), (3, "code")]
    assert "already imported as station OLD-NAME" in plan.skipped[0].message
    assert [row.fields["code"] for row in plan.stations] == ["RIVERSIDE"]


@pytest.mark.parametrize("content", [b"{not json", b"[]", json.dumps([{"name": "x"}]).encode()])
def test_files_without_sites_and_devices_are_refused(content):
    with pytest.raises(importing.SheetError):
        importing.read_file("sites.json", content)
