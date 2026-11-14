"""What each reader sees of an audit record, and how a search or a History tab is filtered
(AUD-4, AUD-6; W19-1, W19-2). No I/O."""

import re
from datetime import UTC, datetime

import pytest

from app.domain.audit import to_record
from app.domain.audit_view import (
    admin_view,
    export_header,
    export_row,
    own_record,
    staff_view,
    words,
)
from app.repo.audit import history_filter, match

AT = datetime(2026, 10, 28, 14, 38, 12, tzinfo=UTC)
ADMIN = "01900000-0000-7000-8000-000000000001"


def record(**over):
    base = {
        "_id": "e1", "seq": 7, "at": AT, "received_at": AT,
        "actor": {"user_id": ADMIN, "name": "Andrea Wright", "roles": ["admin"],
                  "ip": "203.0.113.24", "user_agent": "Chrome", "device_id": "d1"},
        "action": "request.assigned", "resource": {"type": "request", "id": "r1"},
        "org_id": "o1", "before": {"status": "approved", "assigned_to": None},
        "after": {"status": "assigned", "assigned_to": "u2"}, "metadata": {"request_id": "r1"},
        "correlation_id": "req-1", "source_service": "operations", "hash": "h" * 64,
        "prev_hash": "p" * 64,
    }
    base.update(over)
    return base


@pytest.mark.req("AUD-6")
def test_staff_see_who_what_when_and_the_names_of_fields_only():
    view = staff_view(record())
    assert view["actor_name"] == "Andrea Wright"
    assert view["actor_role"] == "admin"
    assert view["summary"] == "assigned the request"
    assert view["changed_fields"] == ["assigned_to", "status"]
    assert view["at"] == "2026-10-28T14:38:12.000Z"
    flat = repr(view)
    for secret in ("203.0.113.24", "Chrome", "d1", "req-1", "approved", "u2", "h" * 64):
        assert secret not in flat


@pytest.mark.req("AUD-4")
def test_an_admin_sees_the_whole_record():
    view = admin_view(record())
    assert view["actor"]["ip"] == "203.0.113.24"
    assert view["correlation_id"] == "req-1"
    assert view["changes"] == [
        {"field": "assigned_to", "before": None, "after": "u2"},
        {"field": "status", "before": "approved", "after": "assigned"},
    ]
    assert view["hash"] == "h" * 64 and view["prev_hash"] == "p" * 64


def test_changed_fields_fall_back_to_the_events_own_list():
    only_data = record(before=None, after=None, metadata={"changed_fields": ["title", "title"]})
    assert staff_view(only_data)["changed_fields"] == ["title"]
    assert staff_view(record(before=None, after=None, metadata={}))["changed_fields"] == []


def test_an_internal_comment_is_said_to_be_internal():
    internal = record(action="comment.added", metadata={"internal": True})
    assert words("comment.added", internal) == "added an internal comment"
    assert words("comment.added", record(action="comment.added")) == "added a comment"


def test_an_action_without_words_is_still_readable():
    assert words("sensor_model.created") == "sensor model: created"


def test_the_role_shown_is_the_most_senior():
    assert staff_view(record(actor={"name": "X", "roles": ["technician", "admin"]}))[
        "actor_role"] == "admin"
    assert staff_view(record(actor={"name": "System", "roles": []}))["actor_role"] is None


def test_the_csv_row_matches_its_header_and_keeps_json_as_text():
    row = export_row(record())
    assert len(row) == len(export_header())
    assert row[export_header().index("before")] == '{"assigned_to": null, "status": "approved"}'


def test_own_records_use_whole_milliseconds_like_every_other():
    at = datetime(2026, 10, 28, 14, 38, 12, 987654, tzinfo=UTC)
    own = own_record(action="audit.exported", at=at, actor={}, correlation_id=None,
                     metadata={}, event_id="x")
    assert own["at"].microsecond == 987000
    assert own["resource"] == {"type": "audit_log", "id": "audit"}
    assert set(own) == set(to_record_fields())


def to_record_fields():
    from mms_common.events import Actor, Envelope, Resource

    return to_record(Envelope(
        event_id="e", type="x.y", occurred_at=AT, source="s", key="k", aggregate_version=1,
        actor=Actor(), resource=Resource(type="t", id="i")), AT)


@pytest.mark.req("AUD-4")
def test_a_search_is_values_only():
    flt = match(actor="Andrea (Wright)", action="request.approved", org_id="o1",
                since=AT, until=AT)
    # a person's name is escaped, so a pattern typed into the box matches itself and nothing else
    assert flt["actor.name"] == {"$regex": r"Andrea\ \(Wright\)", "$options": "i"}
    assert flt["action"] == "request.approved" and flt["org_id"] == "o1"
    assert flt["at"] == {"$gte": AT, "$lt": AT}
    assert match(actor=ADMIN) == {"actor.user_id": ADMIN}
    assert match() == {}


def test_a_request_history_lists_its_visits_and_leaves_out_the_board_noise():
    flt = history_filter("request", "r1")
    own, named = flt["$and"][0]["$or"]
    assert own == {"resource.type": "request", "resource.id": "r1"}
    assert named == {"metadata.request_id": "r1"}
    pattern = flt["$and"][1]["action"]["$not"].pattern
    for noisy in ("visit.element_added", "visit.media_changed", "media.uploaded"):
        assert re.match(pattern, noisy)
    assert not re.match(pattern, "visit.ended")


def test_a_station_history_lists_the_station_and_not_its_visits():
    flt = history_filter("station", "s1")
    assert flt["$and"][0]["$or"][1] == {"metadata.station_id": "s1"}
    pattern = flt["$and"][1]["action"]["$regex"]
    for kept in ("station.updated", "qr.regenerated", "sensor.installed", "calibration.recorded",
                 "config.version_created", "document.uploaded"):
        assert re.match(pattern, kept)
    for left in ("visit.element_added", "request.assigned", "visit.ended"):
        assert not re.match(pattern, left)
