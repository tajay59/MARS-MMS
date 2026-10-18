"""The station import's planning (STN-8; TP "Station import bad-rows fixture"). No I/O: the
organizations, stations and inventory that exist are passed in."""

from __future__ import annotations

import io
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from mms_common.testing.seed import ORG_A, ORG_B
from openpyxl import Workbook

from app.domain.stations import importing
from app.domain.stations.importing import SENSORS, STATIONS

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TODAY = date(2026, 10, 18)
ORGS = {
    "organization a": {"_id": ORG_A, "name": "Organization A"},
    "organization b": {"_id": ORG_B, "name": "Organization B"},
}


def plan_fixture(**existing):
    stations = importing.read_file("s.csv", (FIXTURES / "stations_bad_rows.csv").read_bytes())
    sensors = importing.read_file("s.csv", (FIXTURES / "sensors_bad_rows.csv").read_bytes())
    return importing.plan(
        stations[STATIONS], sensors[STATIONS],
        orgs_by_key=ORGS,
        existing_codes=existing.get("codes", {"TT-OLD-009": {"_id": "x"}}),
        models_by_key=existing.get("models", {}),
        units_by_model_serial=existing.get("units", {}),
        today=TODAY,
    )


def problems(rows, sheet):
    return {(p.row, p.column) for p in rows if p.sheet == sheet}


@pytest.mark.req("STN-8")
def test_bad_rows_are_reported_by_row_number():
    plan = plan_fixture()
    assert problems(plan.errors, STATIONS) == {
        (4, "code"),
        (5, "organization"),
        (6, "country"), (6, "latitude"),
        (7, "code"),
        (8, "time_zone"),
        (9, "status"), (9, "install_date"),
    }
    assert problems(plan.errors, SENSORS) == {
        (4, "parameter"),  # AT at JM-KIN-001 is on row 2
        (7, "serial"),  # V-1 is on row 2
        (8, "station_code"),  # JM-BAD-004 has errors
        (9, "station_code"),  # no such station
        (10, "serial"), (10, "installed_at"),
        (11, "kind"),  # WindSonic is a sensor on row 6
    }
    messages = {(p.sheet, p.row): p.message for p in plan.errors}
    assert messages[(STATIONS, 7)] == "Code JM-KIN-001 is also on row 2"
    assert messages[(SENSORS, 8)] == "Station JM-BAD-004 has errors on row 5"
    assert "Organization Z" in messages[(STATIONS, 5)]


@pytest.mark.req("STN-8")
def test_valid_rows_are_planned_and_existing_codes_skipped():
    plan = plan_fixture()
    assert plan.station_rows == 9  # rows 2 to 11 less the empty row 10
    assert [s.fields["code"] for s in plan.stations] == ["JM-KIN-001", "JM-MBJ-002"]
    kingston = plan.stations[0].fields
    assert kingston["country"] == "JM"  # from the English name
    assert kingston["time_zone"] == "America/Jamaica"  # Jamaica has one zone
    assert kingston["parameters"] == ["AT", "RH", "RAIN"]
    assert kingston["status"] == "operational"
    assert kingston["install_date"] == "2019-03-14"
    assert kingston["location"] == {"type": "Point", "coordinates": [-76.79, 17.97]}
    assert kingston["owner_org_id"] == ORG_A
    assert [s.serial for s in plan.sensors] == ["V-1", "V-2", "B-1", "G-1"]
    assert problems(plan.skipped, STATIONS) == {(11, "code")}
    assert problems(plan.skipped, SENSORS) == {(12, "station_code")}


def test_a_sensor_parameter_missing_from_a_new_station_is_added_with_a_warning():
    plan = plan_fixture()
    montego = plan.stations[1].fields
    assert montego["parameters"] == ["AT", "RH", "WS"]
    assert problems(plan.warnings, SENSORS) == {(6, "parameter")}


def test_dates_become_the_stations_local_midnight():
    plan = plan_fixture()
    v1 = plan.sensors[0]
    # Jamaica is UTC-5 all year.
    assert v1.installed_at == datetime(2019, 3, 14, 5, tzinfo=UTC)
    assert v1.last_calibrated_at == datetime(2026, 1, 10, 5, tzinfo=UTC)
    assert v1.default_calibration_interval_days == 365


def test_an_existing_unit_must_be_in_stock_and_kinds_must_match_the_catalogue():
    from app.domain.stations import sensors

    key = sensors.model_key("Vaisala", "HMP155")
    plan = plan_fixture(
        models={key: {"_id": "m1", "kind": "sensor"},
                sensors.model_key("Trojan", "SCS200"): {"_id": "m2", "kind": "sensor"}},
        units={("m1", "V-2"): {"_id": "u2", "status": "installed"}},
    )
    messages = {(p.sheet, p.row): p.message for p in plan.errors}
    assert messages[(SENSORS, 3)] == "Unit V-2 exists and is installed"
    assert messages[(SENSORS, 5)] == "Trojan SCS200 is a sensor in the catalogue"


def test_missing_required_columns_stop_the_plan():
    table = importing.read_csv(b"code,name\nA1,One\n")
    plan = importing.plan(table, [], orgs_by_key=ORGS, existing_codes={}, models_by_key={},
                          units_by_model_serial={}, today=TODAY)
    # The country defaults to the organization's (W5-8), so it is not a required column
    assert {p.column for p in plan.errors} == {"organization", "latitude", "longitude"}
    assert plan.stations == []


def test_semicolon_csv_and_windows_encoding_are_read():
    content = "code;name\nAB-1;Café Hill\n".encode("cp1252")
    assert importing.read_csv(content) == [(2, {"code": "AB-1", "name": "Café Hill"})]


def test_xlsx_with_stations_and_sensors_sheets():
    book = Workbook()
    sheet = book.active
    sheet.title = "Stations"
    sheet.append(["Code", "Name", "Organization", "Country", "Latitude", "Longitude",
                  "Install date", "Elevation (m)"])
    sheet.append(["BB-CHR-014", "Christ Church", "Organization B", "BB", 13.07, -59.53,
                  datetime(2020, 5, 1), 12.0])
    sensors = book.create_sheet("sensors")
    sensors.append(["Station code", "Manufacturer", "Model", "Serial", "Parameter"])
    sensors.append(["BB-CHR-014", "Vaisala", "HMP155", 12345, "AT"])
    buffer = io.BytesIO()
    book.save(buffer)
    tables = importing.read_file("Export.XLSX", buffer.getvalue())
    plan = importing.plan(tables[STATIONS], tables[SENSORS], orgs_by_key=ORGS,
                          existing_codes={}, models_by_key={}, units_by_model_serial={},
                          today=TODAY)
    assert plan.errors == []
    station = plan.stations[0].fields
    assert station["install_date"] == "2020-05-01"
    assert station["elevation_m"] == 12.0
    assert station["time_zone"] == "America/Barbados"
    assert plan.sensors[0].serial == "12345"  # a number cell becomes text
    assert station["parameters"] == ["AT"]


def test_unreadable_files_are_refused():
    with pytest.raises(importing.SheetError):
        importing.read_file("stations.pdf", b"%PDF")
    with pytest.raises(importing.SheetError):
        importing.read_file("stations.xlsx", b"not a zip")


def test_too_many_rows_are_refused():
    table = [(i, {"code": f"A{i}"}) for i in range(importing.MAX_STATION_ROWS + 1)]
    with pytest.raises(importing.SheetError):
        importing.plan(table, [], orgs_by_key=ORGS, existing_codes={}, models_by_key={},
                       units_by_model_serial={}, today=TODAY)
