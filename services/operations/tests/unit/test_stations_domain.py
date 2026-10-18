"""Stations module rules (STN-1, STN-2, SEN-1 to SEN-3, CAL-3, CAL-6). No I/O."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mms_common.errors import ValidationFailed

from app.domain.stations import places, sensors
from app.domain.stations import stations as rules

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


# --- Places ----------------------------------------------------------------------------------


def test_countries_and_zones_come_from_the_tz_database():
    assert places.valid_country("JM") and places.valid_country("TT")
    assert not places.valid_country("XX")
    assert places.valid_time_zone("America/Barbados")
    assert not places.valid_time_zone("Mars/Olympus_Mons")


def test_a_one_zone_country_suggests_its_zone():
    assert places.default_time_zone("JM") == "America/Jamaica"
    assert places.default_time_zone("BB") == "America/Barbados"
    assert places.default_time_zone("US") is None  # several zones: the user chooses


def test_country_code_accepts_codes_and_english_names():
    assert places.country_code(" jm ") == "JM"
    assert places.country_code("Trinidad  and Tobago") == "TT"
    assert places.country_code("Saint Kitts and Nevis") == "KN"
    assert places.country_code("UK") == "GB"
    assert places.country_code("Atlantis") is None


# --- Stations --------------------------------------------------------------------------------


@pytest.mark.req("STN-1")
def test_code_is_upper_cased_and_checked():
    assert rules.check_code(" bb-chr-014 ") == "BB-CHR-014"
    for bad in ("X", "has space", "-starts-with-dash", "A" * 33):
        with pytest.raises(ValidationFailed):
            rules.check_code(bad)


@pytest.mark.req("STN-1")
def test_parameters_are_codes_deduplicated_in_order():
    assert rules.check_parameters(["at", "RH", "AT", "soil_t"]) == ["AT", "RH", "SOIL_T"]
    with pytest.raises(ValidationFailed):
        rules.check_parameters(["air temp"])
    longest = "L" * rules.PARAMETER_MAX_LENGTH
    found = rules.check_parameters(["soil_moisture_10cm", longest])
    assert found == ["SOIL_MOISTURE_10CM", longest]
    with pytest.raises(ValidationFailed):
        rules.check_parameters([longest + "X"])
    many = [f"P{n}" for n in range(rules.MAX_PARAMETERS)]
    assert rules.check_parameters(many) == many
    with pytest.raises(ValidationFailed) as exc:
        rules.check_parameters([*many, "ONE_MORE"])
    assert exc.value.extra["field"] == "parameters"


def test_place_is_checked():
    rules.check_place("BB", "America/Barbados")
    with pytest.raises(ValidationFailed) as exc:
        rules.check_place("ZZ", "America/Barbados")
    assert exc.value.extra["field"] == "country"
    with pytest.raises(ValidationFailed) as exc:
        rules.check_place("BB", "Barbados")
    assert exc.value.extra["field"] == "time_zone"


def test_location_is_geojson_longitude_first():
    assert rules.point(13.1, -59.6) == {"type": "Point", "coordinates": [-59.6, 13.1]}
    with pytest.raises(ValidationFailed):
        rules.point(91, 0)


@pytest.mark.req("STN-2")
def test_station_statuses():
    assert [s.value for s in rules.Status] == [
        "operational", "degraded", "offline", "decommissioned",
    ]


def test_qr_tokens_are_long_and_unique():
    tokens = {rules.new_qr_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(t) >= 20 for t in tokens)


def test_changed_fields_keeps_only_real_changes():
    assert rules.changed_fields({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": None}) == {"b": 3}


# --- Units -----------------------------------------------------------------------------------

STATION = {"_id": "s1", "status": "operational", "parameters": ["AT", "RH"]}
SENSOR = {"_id": "m1", "kind": "sensor", "parameters": ["AT", "RH"]}
BATTERY = {"_id": "m2", "kind": "battery", "parameters": []}


@pytest.mark.req("SEN-2")
@pytest.mark.parametrize(("current", "wanted", "ok"), [
    ("in_stock", "in_repair", True),
    ("in_stock", "retired", True),
    ("in_repair", "in_stock", True),
    ("retired", "in_stock", True),
    ("retired", "in_repair", False),
    ("in_stock", "in_stock", True),
])
def test_status_edits(current, wanted, ok):
    if ok:
        sensors.check_status_edit(current, wanted)
    else:
        with pytest.raises(ValidationFailed):
            sensors.check_status_edit(current, wanted)


def test_an_installed_unit_changes_status_only_by_removal():
    with pytest.raises(sensors.UnitInstalled):
        sensors.check_status_edit("installed", "retired")


@pytest.mark.req("SEN-3")
def test_install_checks():
    unit = {"status": "in_stock"}
    sensors.check_install(unit, SENSOR, STATION, "AT", set())
    sensors.check_install(unit, BATTERY, STATION, None, {"AT"})  # components share nothing
    with pytest.raises(sensors.ParameterTaken):
        sensors.check_install(unit, SENSOR, STATION, "AT", {"AT"})
    with pytest.raises(ValidationFailed, match="parameter"):
        sensors.check_install(unit, SENSOR, STATION, None, set())
    with pytest.raises(ValidationFailed, match="doesn't measure"):
        sensors.check_install(unit, {**SENSOR, "parameters": ["RH"]}, STATION, "AT", set())
    with pytest.raises(ValidationFailed, match="doesn't list"):
        sensors.check_install(unit, {**SENSOR, "parameters": []}, STATION, "BP", set())
    with pytest.raises(sensors.UnitInstalled):
        sensors.check_install({"status": "installed"}, SENSOR, STATION, "AT", set())
    with pytest.raises(sensors.UnitNotInStock):
        sensors.check_install({"status": "in_repair"}, SENSOR, STATION, "AT", set())
    with pytest.raises(sensors.StationDecommissioned):
        sensors.check_install(unit, SENSOR, {**STATION, "status": "decommissioned"}, "AT", set())


def test_dates_cannot_be_in_the_future_or_before_installation():
    sensors.check_when(NOW + timedelta(minutes=4), NOW)  # a phone's clock a little ahead
    with pytest.raises(ValidationFailed):
        sensors.check_when(NOW + timedelta(hours=1), NOW)
    with pytest.raises(ValidationFailed):
        sensors.check_when(NOW - timedelta(days=2), NOW, not_before=NOW - timedelta(days=1))


def test_model_key_ignores_case_and_spacing():
    assert sensors.model_key(" Kipp &  Zonen", "SMP3 ") == sensors.model_key("kipp & zonen", "smp3")


# --- Calibration -----------------------------------------------------------------------------


@pytest.mark.req("CAL-3")
def test_the_unit_override_beats_the_model_default():
    assert sensors.interval_days({"calibration_interval_days": 180}, {"default_calibration_interval_days": 365}) == 180  # noqa: E501
    assert sensors.interval_days({}, {"default_calibration_interval_days": 365}) == 365
    assert sensors.interval_days({}, None) is None


@pytest.mark.req("CAL-3")
def test_due_is_last_calibration_plus_interval():
    assert sensors.due_at(NOW, 30) == NOW + timedelta(days=30)
    assert sensors.due_at(None, 30) is None
    assert sensors.due_at(NOW, None) is None


@pytest.mark.req("CAL-4")
def test_due_state():
    assert sensors.due_state(NOW - timedelta(days=1), NOW) is sensors.DueState.OVERDUE
    assert sensors.due_state(NOW + timedelta(days=29), NOW) is sensors.DueState.DUE_SOON
    assert sensors.due_state(NOW + timedelta(days=31), NOW) is sensors.DueState.OK
    assert sensors.due_state(NOW + timedelta(days=31), NOW, within_days=60) is (
        sensors.DueState.DUE_SOON
    )
    assert sensors.due_state(None, NOW) is None


@pytest.mark.req("CAL-6")
def test_a_failed_calibration_flags_the_unit_and_a_pass_clears_it():
    model = {"default_calibration_interval_days": 365}
    failed = sensors.unit_after_calibration({"flags": ["other"]}, model, NOW, "fail")
    assert failed["flags"] == ["other", "calibration_failed"]
    assert failed["calibration_due_at"] == NOW + timedelta(days=365)
    later = NOW + timedelta(days=10)
    passed = sensors.unit_after_calibration(
        {"flags": failed["flags"], "last_calibrated_at": NOW}, model, later, "pass"
    )
    assert passed["flags"] == ["other"]
    assert passed["last_calibrated_at"] == later


@pytest.mark.req("CAL-3")
def test_an_older_record_joins_the_history_only():
    unit = {"last_calibrated_at": NOW, "flags": []}
    assert sensors.unit_after_calibration(unit, None, NOW - timedelta(days=1), "fail") == {}


def test_a_reading_needs_a_value():
    sensors.check_readings([{"reference": 20.0, "before": None, "after": None}])
    with pytest.raises(ValidationFailed):
        sensors.check_readings([{"reference": None, "before": None, "after": None, "unit": "C"}])
