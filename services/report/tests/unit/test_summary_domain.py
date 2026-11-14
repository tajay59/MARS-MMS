"""Summary reports without any I/O (PRD SUM-1 to SUM-3; decisions W19-8 to W19-10): the period
in the report's zone, who may ask for what, and each type's tables over made-up rows."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from mms_common.errors import ValidationFailed

from app.domain import summary
from app.domain.summary import Kind

NOW = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
ZONE = "America/Jamaica"  # UTC-5 all year


def at(day: int, hour: int = 12, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


STATIONS = {
    "s1": {"_id": "s1", "code": "JM-KIN-001", "name": "Kingston", "country": "Jamaica",
           "status": "operational"},
    "s2": {"_id": "s2", "code": "BB-BGI-001", "name": "Bridgetown", "country": "Barbados",
           "status": "offline"},
}


def req(n: int, **over):
    base = {"_id": f"r{n}", "ref": f"MR-2026-{n:04d}", "station_ids": ["s1"],
            "category": "fault", "priority": "normal", "status": "closed",
            "submitted_at": at(1), "approved_at": at(1, 19), "assigned_at": at(2),
            "first_visit_at": at(4), "closed_at": at(11), "reopen_count": 0}
    base.update(over)
    return base


def test_a_month_starts_at_midnight_in_the_reports_zone():
    p = summary.period(date(2026, 10, 1), date(2026, 10, 31), ZONE, 1096)
    assert p.start == datetime(2026, 10, 1, 5, 0, tzinfo=UTC)  # 00:00 in Jamaica
    assert p.end == datetime(2026, 11, 1, 5, 0, tzinfo=UTC)


def test_a_period_is_checked():
    with pytest.raises(ValidationFailed) as backwards:
        summary.period(date(2026, 10, 2), date(2026, 10, 1), ZONE, 1096)
    assert backwards.value.extra["code"] == "invalid_period"
    with pytest.raises(ValidationFailed):
        summary.period(date(2020, 1, 1), date(2026, 1, 1), ZONE, 1096)
    assert summary.period(date(2026, 1, 1), date(2026, 1, 1), ZONE, 1).end - summary.period(
        date(2026, 1, 1), date(2026, 1, 1), ZONE, 1).start == timedelta(days=1)


@pytest.mark.req("SUM-3")
def test_a_client_may_run_three_types_and_staff_all():
    client = {k for k in Kind if summary.allowed(k, client=True)}
    assert client == {Kind.STATION_HISTORY, Kind.CLIENT_ACTIVITY, Kind.STATION_ASSET}
    assert not summary.allowed(Kind.TECHNICIAN_WORKLOAD, client=True)
    assert all(summary.allowed(k, client=False) for k in Kind)
    assert set(summary.TYPES) == set(Kind) == set(summary.BUILDERS)


def test_percentiles_and_medians():
    assert summary.nearest_rank([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == 9
    assert summary.nearest_rank([5], 90) == 5
    assert summary.nearest_rank([], 90) is None
    assert summary.median([1, 2, 4]) == 2 and summary.median([1, 2]) == 1.5
    assert summary.median([]) is None


@pytest.mark.req("SUM-1")
def test_turnaround_counts_days_for_each_step_and_by_category():
    doc = summary.build(Kind.REQUEST_TURNAROUND, {"requests": [
        req(1), req(2, category="calibration", closed_at=at(21), reopen_count=1),
        req(3, closed_at=at(31, 12)),
    ]})
    first = doc.main.rows[0]
    assert first[0] == "MR-2026-0001" and first[3:7] == [0.3, 1.0, 3.0, 10.0] and first[7] == 0
    assert doc.kpis[0] == ("Requests closed", "3")
    assert doc.kpis[1] == ("Median, submitted to closed", "20 days")
    by_category = {r[0]: r for r in doc.tables[1].rows}
    assert by_category["fault"][1:] == [2, 20, 30]
    assert by_category["calibration"][1] == 1
    assert "denied or cancelled" in doc.notes[0]


def test_turnaround_with_nothing_closed_says_none_and_does_not_fail():
    doc = summary.build(Kind.REQUEST_TURNAROUND, {"requests": []})
    assert doc.main.rows == [] and doc.kpis[1][1] == "none"


@pytest.mark.req("CAL-4")
def test_calibration_due_separates_overdue_from_due_soon_and_counts_days():
    doc = summary.build(Kind.CALIBRATION_DUE, {"now": NOW, "due_in_days": 30, "stations": STATIONS,
        "units": [{"serial": "A", "station_id": "s1", "due_at": NOW + timedelta(days=10)},
                  {"serial": "B", "station_id": "s2", "due_at": NOW - timedelta(days=3)}]})
    assert [r[2] for r in doc.main.rows] == ["B", "A"]  # the most overdue first
    assert doc.main.rows[0][4:] == [-3.0, "Overdue"] and doc.main.rows[1][4:] == [10.0, "Due soon"]
    assert doc.kpis == [("Overdue", "1"), ("Due in 30 days", "1")]


def test_network_status_lists_every_station_with_its_counts():
    doc = summary.build(Kind.NETWORK_STATUS, {
        "stations": STATIONS, "last_visit": {"s1": at(20)}, "open_requests": {"s1": 2},
        "overdue_units": {"s2": 1}})
    assert [r[0] for r in doc.main.rows] == ["BB-BGI-001", "JM-KIN-001"]  # by country, then code
    assert doc.main.rows[1][4:] == [at(20), 2, 0] and doc.main.rows[0][4:] == [None, 0, 1]
    assert doc.kpis == [("Stations", "2"), ("Operational", "1"), ("Degraded or offline", "1")]


@pytest.mark.req("SUM-1")
def test_station_history_merges_visits_requests_and_calibrations_in_date_order():
    doc = summary.build(Kind.STATION_HISTORY, {
        "stations": STATIONS, "request_refs": {"r1": "MR-2026-0001"},
        "serials": {"u1": "SN-1"},
        "visits": [{"ended_at": at(5), "station_ids": ["s1"], "ref": "VR-1", "request_id": "r1"}],
        "requests": [req(1, submitted_at=at(1))],
        "calibrations": [{"at": at(8), "station_id": "s1", "sensor_unit_id": "u1",
                          "result": "pass", "method": "lab"}],
    })
    assert [(r[2], r[3]) for r in doc.main.rows] == [
        ("Request", "MR-2026-0001"), ("Visit", "VR-1"), ("Calibration", "SN-1")]
    assert doc.main.rows[2][4] == "pass (lab)" and doc.main.rows[1][1] == "JM-KIN-001"


def test_client_activity_counts_visits_and_requests_sent_back():
    doc = summary.build(Kind.CLIENT_ACTIVITY, {
        "requests": [req(1, reopen_count=2), req(2, status="in_progress", closed_at=None)],
        "visits": [{"request_id": "r1"}, {"request_id": "r1"}]})
    assert doc.main.rows[0][6:] == [2, 2]
    assert dict(doc.kpis) == {"Requests": "2", "Closed": "1", "Sent back by the client": "1",
                              "Median days to close": "10"}


def test_the_monthly_and_annual_summaries_group_by_the_reports_zone():
    # 02:00 UTC on 1 November is still 31 October in Jamaica
    late = datetime(2026, 11, 1, 2, tzinfo=UTC)
    data = {"zone": ZONE, "stations": STATIONS,
            "submitted": [req(1, submitted_at=late), req(2, station_ids=["s2"])],
            "closed": [req(3, reopen_count=1)], "visits": [
                {"ended_at": at(3), "station_ids": ["s2"]}], "calibrations": [{"at": at(4)}]}
    annual = summary.build(Kind.ANNUAL_SUMMARY, data)
    assert annual.main.rows == [["2026-10", 2, 1, 1, 1]]
    monthly = summary.build(Kind.MONTHLY_SUMMARY, data)
    assert monthly.tables[0].rows == [["fault", 2, 1, 1]]
    assert monthly.tables[1].rows == [["Barbados", 1, 0, 1], ["Jamaica", 1, 1, 0]]


def test_the_pdf_view_prints_times_in_the_zone_and_says_who_made_it():
    doc = summary.build(Kind.NETWORK_STATUS, {
        "stations": STATIONS, "last_visit": {"s1": datetime(2026, 10, 20, 3, 30, tzinfo=UTC)},
        "open_requests": {}, "overdue_units": {}})
    view = summary.pdf_view(doc, subtitle="s", filters="f", zone=ZONE, generated_at=NOW,
                            generated_by="Andrea Wright")
    assert view["generated"] == "2026-10-28 10:00" and view["generated_by"] == "Andrea Wright"
    assert view["tables"][0]["rows"][1][4] == "2026-10-19 22:30"  # the day before, in Jamaica
    assert view["tables"][0]["right"] == [5, 6] and view["kpis"][0]["label"] == "Stations"


def test_file_names_say_the_report_and_the_period_only():
    p = summary.period(date(2026, 1, 1), date(2026, 9, 30), ZONE, 1096)
    assert summary.file_name(Kind.REQUEST_TURNAROUND, p, "pdf") == (
        "request-turnaround_2026-01-01_2026-09-30.pdf")
    assert summary.file_name(Kind.NETWORK_STATUS, p, "csv") == "network-status.csv"


MODELS = {"m1": {"_id": "m1", "manufacturer": "Vaisala", "model": "HMP155", "kind": "sensor"},
          "m2": {"_id": "m2", "manufacturer": "Campbell", "model": "CS106", "kind": "sensor"}}


@pytest.mark.req("SUM-1")
def test_station_asset_lists_what_is_installed_with_its_calibration_dates():
    doc = summary.build(Kind.STATION_ASSET, {
        "now": NOW, "stations": STATIONS, "models": MODELS,
        "units": {"u1": {"due_at": NOW - timedelta(days=2)}, "u2": {"due_at": NOW + timedelta(days=9)}},
        "last_cal": {"u1": {"at": at(1)}},
        "installs": [
            {"unit_id": "u2", "station_id": "s2", "parameter": "RH", "model_id": "m2",
             "serial": "B-2", "installed_at": at(3)},
            {"unit_id": "u1", "station_id": "s1", "parameter": "AT", "model_id": "m1",
             "serial": "A-1", "installed_at": at(2)},
        ]})
    assert [r[0] for r in doc.main.rows] == ["BB-BGI-001", "JM-KIN-001"]  # by station code
    row = doc.main.rows[1]
    assert row[2:5] == ["AT", "Vaisala HMP155", "A-1"] and row[6] == at(1) and row[7] < NOW
    assert doc.main.rows[0][6] is None  # never calibrated
    assert dict(doc.kpis) == {"Stations": "2", "Sensors installed": "2", "Calibrations overdue": "1"}


@pytest.mark.req("SUM-1")
def test_sensor_reliability_counts_per_model_and_sorts_the_worst_first():
    doc = summary.build(Kind.SENSOR_RELIABILITY, {
        "models": MODELS,
        "units": {"u1": {"model_id": "m1"}, "u2": {"model_id": "m2"}},
        "installed": [{"model_id": "m1"}, {"model_id": "m1"}, {"model_id": "m2"}],
        "removed": [{"model_id": "m1", "installed_at": at(1), "removed_at": at(11)},
                    {"model_id": "m1", "installed_at": at(1), "removed_at": at(21)}],
        "open": [{"model_id": "m2"}, {"model_id": "m1"}],
        "failed": [{"sensor_unit_id": "u2"}, {"sensor_unit_id": "u2"}, {"sensor_unit_id": "u1"}]})
    names = [r[0] for r in doc.main.rows]
    assert names == ["Campbell CS106", "Vaisala HMP155"]  # two failures before one
    campbell, vaisala = doc.main.rows
    assert campbell[2:] == [1, 0, 2, None, 1]
    assert vaisala[2:] == [2, 2, 1, 15.0, 1]
    assert dict(doc.kpis) == {"Models": "2", "Removals": "2", "Failed calibrations": "3"}


def test_a_sensor_of_a_model_nobody_knows_is_still_counted():
    doc = summary.build(Kind.SENSOR_RELIABILITY, {
        "models": {}, "units": {}, "installed": [{"model_id": "gone"}], "removed": [],
        "open": [], "failed": []})
    assert doc.main.rows[0][0] == "Unknown model"


@pytest.mark.req("SUM-1")
def test_configuration_history_names_the_visit_and_orders_by_time():
    doc = summary.build(Kind.CONFIGURATION_HISTORY, {
        "stations": STATIONS, "visit_refs": {"v1": "VR-2026-0001-01"},
        "configs": [
            {"created_at": at(9), "station_id": "s1", "number": 4, "file_count": 3, "visit_id": "v1"},
            {"created_at": at(2), "station_id": "s2", "number": 1, "file_count": 1, "visit_id": None}]})
    assert [r[2] for r in doc.main.rows] == [1, 4]
    assert doc.main.rows[1] == [at(9), "JM-KIN-001", 4, 3, "VR-2026-0001-01"]
    assert dict(doc.kpis) == {"Versions saved": "2", "Stations changed": "2"}


@pytest.mark.req("SUM-1")
def test_technician_workload_adds_up_requests_visits_hours_and_signatures():
    doc = summary.build(Kind.TECHNICIAN_WORKLOAD, {
        "names": {"u1": "Devon Clarke", "u2": "Aisha Mohammed"},
        "open": [{"assigned_ids": ["u1"]}, {"assigned_ids": ["u1", "u2"]}],
        "closed": [{"assigned_ids": ["u1"]}],
        "visits": [
            {"staff_ids": ["u1", "u2"], "lead_staff_id": "u1", "started_at": at(1, 8),
             "ended_at": at(1, 12)},
            {"staff_ids": ["u1"], "lead_staff_id": "u1", "started_at": at(2, 8),
             "ended_at": at(2, 10)},
            {"staff_ids": ["u2"], "lead_staff_id": "u2", "started_at": None, "ended_at": at(3)},
        ],
        "signed": {"u1": 2, "u3": 1}})
    by_name = {r[0]: r for r in doc.main.rows}
    assert by_name["Devon Clarke"][1:] == [2, 1, 2, 2, 6.0, 2]
    assert by_name["Aisha Mohammed"][1:] == [1, 0, 2, 1, 4.0, 0]  # no start time: no hours
    assert by_name["Unknown person"][1:] == [0, 0, 0, 0, 0.0, 1]  # signed, but not on a visit
    assert [r[0] for r in doc.main.rows] == ["Aisha Mohammed", "Devon Clarke", "Unknown person"]
    assert dict(doc.kpis) == {"Technicians": "3", "Visits ended": "3", "Hours on site": "10"}


def test_a_workload_with_nobody_in_it_is_an_empty_table():
    doc = summary.build(Kind.TECHNICIAN_WORKLOAD, {
        "names": {}, "open": [], "closed": [], "visits": [], "signed": {}})
    assert doc.main.rows == [] and doc.kpis[0] == ("Technicians", "0")
