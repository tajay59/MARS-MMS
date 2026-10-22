"""The rules for photos and video on a visit (W11-10, W11-13), with no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mms_common.errors import Conflict, Forbidden, NotFound, ValidationFailed

from app.domain.stations.documents import FileFacts
from app.domain.visits import media as rules

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
V, S, U = "visit-1", "station-1", "user-1"


def facts(**kw) -> FileFacts:
    base = {"owner_ref": rules.owner_ref(V, S, "before"), "kind": "image", "status": "uploaded",
            "uploaded_by": U, "filename": "a.jpg", "size_bytes": 10, "checksum_sha256": "0" * 64}
    return FileFacts(**{**base, **kw})


def visit(status="started", **kw) -> dict:
    return {"status": status, "staff_ids": [U], "stations": [{"station_id": S, "media": []}], **kw}


def test_the_owner_reference_round_trips_and_other_owners_are_not_a_visit_reference():
    ref = rules.owner_ref(V, S, "after")
    assert ref == "visit:visit-1:station:station-1:after"
    assert rules.parse_owner_ref(ref) == (V, S, "after")
    for other in ("visit:x", "document:station:s", f"visit:{V}:station:{S}:later",
                  f"visit:{V}:rack:{S}:before", ""):
        assert rules.parse_owner_ref(other) is None


def test_a_phase_is_before_during_or_after():
    assert [rules.check_phase(p) for p in rules.PHASES] == ["before", "during", "after"]
    with pytest.raises(ValidationFailed):
        rules.check_phase("later")


@pytest.mark.parametrize(("status", "extra", "error"), [
    ("planned", {}, Conflict), ("cancelled", {}, Conflict), ("started", {"locked": True}, Conflict),
])
def test_media_changes_only_while_the_visit_is_open(status, extra, error):
    with pytest.raises(error):
        rules.check_can_change(visit(status, **extra), U, False)


def test_attending_staff_and_admins_may_change_and_nobody_else():
    rules.check_can_change(visit(), U, False)
    rules.check_can_change(visit("ended"), "someone-else", True)
    with pytest.raises(Forbidden):
        rules.check_can_change(visit(), "someone-else", False)


def test_media_is_shared_once_the_visit_has_ended():
    assert rules.shared(visit("ended")) is True
    assert not any(rules.shared(visit(s)) for s in ("planned", "started", "cancelled"))


def test_captions_are_trimmed_cleared_when_blank_and_bounded():
    assert rules.check_caption(None) is None
    assert rules.check_caption("  North mast ") == "North mast"
    assert rules.check_caption("   ") is None
    assert rules.check_caption("x" * rules.MAX_CAPTION) == "x" * rules.MAX_CAPTION
    with pytest.raises(ValidationFailed):
        rules.check_caption("x" * (rules.MAX_CAPTION + 1))


def test_a_capture_time_may_be_a_little_ahead_but_not_next_week():
    assert rules.check_captured_at(None, NOW) is None
    soon = NOW + timedelta(hours=2)
    assert rules.check_captured_at(soon, NOW) == soon
    with pytest.raises(ValidationFailed):
        rules.check_captured_at(NOW + timedelta(days=2), NOW)


@pytest.mark.parametrize(("change", "code"), [
    ({"owner_ref": "visit:x:station:y:before"}, "wrong_owner"),
    ({"uploaded_by": "other"}, "not_yours"),
    ({"kind": "pdf"}, "wrong_kind"),
    ({"status": "pending"}, "file_not_uploaded"),
    ({"status": "failed"}, "file_not_uploaded"),
])
def test_a_file_must_be_the_uploaders_photo_or_video_for_this_place(change, code):
    with pytest.raises(ValidationFailed) as caught:
        rules.check_file(facts(**change), owner=rules.owner_ref(V, S, "before"), user_id=U)
    assert caught.value.extra["code"] == code


def test_a_missing_file_is_unknown_and_a_file_in_progress_is_accepted():
    with pytest.raises(ValidationFailed):
        rules.check_file(None, owner=rules.owner_ref(V, S, "before"), user_id=U)
    for status in ("uploaded", "processing", "ready"):
        for kind in ("image", "video"):
            rules.check_file(facts(status=status, kind=kind),
                             owner=rules.owner_ref(V, S, "before"), user_id=U)


def test_an_entry_names_the_file_the_phase_and_who_added_it():
    entry = rules.new_entry(facts(), media_id="m1", phase="before", caption=None,
                            captured_at=None, by=U, by_name="Una", now=NOW)
    assert entry == {
        "media_id": "m1", "phase": "before", "kind": "image", "filename": "a.jpg",
        "caption": None, "captured_at": None, "added_by": U, "added_by_name": "Una",
        "added_at": NOW, "hidden": False,
    }


def test_a_station_and_an_entry_are_found_or_not_found():
    doc = visit(stations=[{"station_id": S, "media": [{"media_id": "m1"}]}])
    station = rules.station_of(doc, S)
    assert rules.entry_of(station, "m1")["media_id"] == "m1"
    with pytest.raises(NotFound):
        rules.station_of(doc, "other")
    with pytest.raises(NotFound):
        rules.entry_of(station, "m2")


def test_the_end_shares_what_was_not_hidden_on_every_station():
    doc = {"stations": [
        {"station_id": "a", "media": [{"media_id": "m1"}, {"media_id": "m2", "hidden": True}]},
        {"station_id": "b", "media": [{"media_id": "m3", "hidden": False}]},
        {"station_id": "c"},
    ]}
    assert rules.shared_ids(doc) == ["m1", "m3"]
