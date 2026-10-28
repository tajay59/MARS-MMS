"""The read model's rows (TRD 5.4, 8.6): one builder for an event and a snapshot item."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain import readmodel as rm

REQUEST = {
    "request_id": "r1", "ref": "MR-2026-0042", "org_id": "o1", "station_ids": ["s1", "s2"],
    "category": "fault", "priority": "high", "status": "assigned",
    "milestones": {
        "submitted_at": "2026-10-01T09:00:00Z", "approved_at": "2026-10-02T09:30:00+00:00",
        "other": "ignored",
    },
    "reopen_count": None,
}


def test_a_request_row_reads_milestones_from_strings_and_datetimes():
    row = rm.request_row(REQUEST, 4)
    assert row["_id"] == "r1" and row["aggregate_version"] == 4
    assert row["submitted_at"] == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert row["approved_at"] == datetime(2026, 10, 2, 9, 30, tzinfo=UTC)
    assert row["closed_at"] is None
    assert row["reopen_count"] == 0 and row["auto_closed"] is False
    assert "other" not in row
    naive = datetime(2026, 10, 3, 8, 0)  # a time with no zone is taken as UTC
    assigned = rm.request_row({**REQUEST, "milestones": {"assigned_at": naive}}, 1)["assigned_at"]
    assert assigned.tzinfo is UTC


def test_a_request_without_milestones_still_has_a_row():
    row = rm.request_row({k: v for k, v in REQUEST.items() if k != "milestones"}, 1)
    assert all(row[m] is None for m in rm.MILESTONES)


def test_a_visit_row_from_an_event_and_from_a_snapshot_agree():
    event = {
        "visit_id": "v1", "ref": "VR-2026-0042-01", "request_id": "r1", "org_id": "o1",
        "status": "ended", "staff_ids": ["u1"], "lead_staff_id": "u1", "station_ids": ["s1"],
        "planned_start": datetime(2026, 10, 5, 8, tzinfo=UTC),
        "planned_end": datetime(2026, 10, 5, 12, tzinfo=UTC),
        "started_at": datetime(2026, 10, 5, 8, 5, tzinfo=UTC),
        "ended_at": datetime(2026, 10, 5, 11, 40, tzinfo=UTC),
        "additional_visit_required": False, "time_zone": "America/Jamaica",
    }
    snapshot = {
        **event, "planned_start": "2026-10-05T08:00:00Z", "planned_end": "2026-10-05T12:00:00Z",
        "started_at": "2026-10-05T08:05:00Z", "ended_at": "2026-10-05T11:40:00Z",
    }
    assert rm.visit_row(event, 3) == rm.visit_row(snapshot, 3)


def test_kept_fields_fill_only_what_the_new_row_lacks():
    stored = {"started_at": "S", "ended_at": "E", "element_counts": {"note": 2}}
    row = {"started_at": None, "ended_at": "NEW", "element_counts": None, "status": "ended"}
    kept = rm.keep_from(stored, row, rm.VISIT_KEEP)
    assert kept["started_at"] == "S" and kept["ended_at"] == "NEW"
    assert kept["element_counts"] == {"note": 2}


def test_a_calibration_row_and_a_station_row():
    cal = rm.calibration_row({
        "calibration_id": "c1", "unit_id": "u1", "station_id": "s1", "method": "lab",
        "at": "2026-09-01T00:00:00Z", "result": "pass", "due_at": None, "org_id": "o1",
    }, 2)
    assert cal["_id"] == "c1" and cal["org_id"] == "o1" and cal["voided"] is False
    station = rm.station_row({
        "station_id": "s1", "code": "A", "name": "Alpha", "org_id": "o1", "country": "JM",
        "status": "operational",
    }, 1)
    assert station["type"] is None and station["_id"] == "s1"


def test_a_unit_row_and_who_is_on_a_request():
    unit = rm.unit_row({
        "unit_id": "u1", "serial": "SN-1", "model_id": "m1", "status": "installed",
        "current_station_id": "s1", "calibration_due_at": "2027-01-01T00:00:00Z",
    }, 3)
    assert (unit["_id"], unit["station_id"], unit["aggregate_version"]) == ("u1", "s1", 3)
    assert unit["due_at"].year == 2027
    assert rm.unit_row({"unit_id": "u2", "serial": "x", "model_id": "m", "status": "in_stock"},
                       1)["due_at"] is None
    request = rm.request_row({
        "request_id": "r1", "ref": "MR-1", "org_id": "o1", "station_ids": ["s1"],
        "category": "fault", "priority": "normal", "status": "assigned",
        "assigned_staff_ids": ["u1", "u2"],
    }, 2)
    assert request["assigned_ids"] == ["u1", "u2"]


def test_every_event_and_snapshot_entity_has_a_builder():
    wanted = set(rm.REQUEST_EVENTS) | set(rm.VISIT_EVENTS) | set(rm.STATION_EVENTS)
    assert set(rm.BUILDERS) >= wanted
    assert set(rm.UNIT_EVENTS) <= set(rm.BUILDERS)
    assert set(rm.SNAPSHOT_ENTITIES) == {
        "stations", "requests", "visits", "calibrations", "sensor_units",
    }
    assert not any(t.startswith("visit.element") for t in rm.BUILDERS)
