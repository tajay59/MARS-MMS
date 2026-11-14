"""The visits domain, W10 (PRD VIS-1 to VIS-4, VIS-9; ADR-17, ADR-18): the state table, planning,
the lifecycle moves and the request status they derive. Pure functions, no containers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mms_common.errors import Conflict, Forbidden, NotFound, ValidationFailed

from app.domain.requests.recompute import recompute
from app.domain.requests.state import Status
from app.domain.visits import lifecycle, schedule
from app.domain.visits.state import RULES, VAction, VStatus, move

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
ALICE, BEN, CARA = "u-alice", "u-ben", "u-cara"
S1, S2, S3 = "st-1", "st-2", "st-3"


def visit(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ref": "VR-2026-0001-01", "status": "planned", "staff_ids": [ALICE, BEN],
        "lead_staff_id": ALICE, "created_by": ALICE, "notes": None,
        "planned_start": NOW + timedelta(days=1), "planned_end": NOW + timedelta(days=2),
        "stations": [schedule.new_station(S1, ALICE, {}), schedule.new_station(S2, BEN, {})],
    }
    base.update(over)
    return base


# --- the state table ----------------------------------------------------------------------------


@pytest.mark.req("VIS-4")
def test_every_row_of_the_table_is_a_move():
    for (current, action), to in RULES.items():
        assert move(current, action) is to


@pytest.mark.req("VIS-4")
@pytest.mark.parametrize(("current", "action", "code"), [
    (VStatus.CANCELLED, VAction.START, "visit_cancelled"),
    (VStatus.CANCELLED, VAction.END, "visit_cancelled"),
    (VStatus.ENDED, VAction.START, "already_ended"),
    (VStatus.ENDED, VAction.CANCEL, "already_ended"),
    (VStatus.PLANNED, VAction.END, "bad_transition"),
    (VStatus.STARTED, VAction.START, "bad_transition"),
    (VStatus.STARTED, VAction.RESTORE, "bad_transition"),
])
def test_a_move_not_in_the_table_is_a_conflict_with_the_sync_code(current, action, code):
    with pytest.raises(Conflict) as caught:
        move(current, action)
    assert caught.value.extra["code"] == code


# --- planning -----------------------------------------------------------------------------------


@pytest.mark.req("VIS-1")
def test_the_lead_is_the_first_person_unless_named_and_must_attend():
    assert schedule.clean_staff([ALICE, BEN, ALICE], None) == ([ALICE, BEN], ALICE)
    assert schedule.clean_staff([ALICE, BEN], BEN) == ([ALICE, BEN], BEN)
    with pytest.raises(ValidationFailed) as caught:
        schedule.clean_staff([ALICE], BEN)
    assert caught.value.extra["code"] == "lead_not_attending"
    with pytest.raises(ValidationFailed):
        schedule.clean_staff([], None)
    with pytest.raises(ValidationFailed):
        schedule.clean_staff([f"u{i}" for i in range(11)], None)


@pytest.mark.req("VIS-1")
def test_a_station_owner_defaults_to_the_lead_and_must_attend():
    owners = schedule.clean_owners([(S1, None), (S2, BEN), (S1, BEN)], [ALICE, BEN], ALICE,
                                   [S1, S2, S3])
    assert owners == {S1: ALICE, S2: BEN}  # a repeat is ignored, order kept
    with pytest.raises(ValidationFailed) as caught:
        schedule.clean_owners([(S1, CARA)], [ALICE, BEN], ALICE, [S1])
    assert caught.value.extra["code"] == "owner_not_attending"
    with pytest.raises(ValidationFailed) as caught:
        schedule.clean_owners([(S3, None)], [ALICE], ALICE, [S1])
    assert caught.value.extra["code"] == "station_not_on_request"
    with pytest.raises(ValidationFailed):
        schedule.clean_owners([], [ALICE], ALICE, [S1])


@pytest.mark.req("VIS-1")
def test_the_window_must_run_forwards_and_not_too_long():
    schedule.check_window(NOW, NOW + timedelta(days=3))
    with pytest.raises(ValidationFailed):
        schedule.check_window(NOW, NOW)
    with pytest.raises(ValidationFailed):
        schedule.check_window(NOW, NOW + timedelta(days=32))


@pytest.mark.req("VIS-1")
def test_a_station_is_in_one_live_visit_of_a_request_at_a_time():
    other = visit(ref="VR-2026-0001-02", stations=[schedule.new_station(S3, ALICE, {})])
    schedule.check_stations_free([S1, S2], [other])  # different stations: a parallel visit
    with pytest.raises(Conflict) as caught:
        schedule.check_stations_free([S2, S3], [other])
    assert caught.value.extra["code"] == "station_in_other_visit"
    assert caught.value.extra["station_id"] == S3


@pytest.mark.req("VIS-1")
def test_who_may_schedule_and_manage():
    assert schedule.can_schedule(ALICE, False, [ALICE])
    assert schedule.can_schedule("someone", True, [])
    assert not schedule.can_schedule(BEN, False, [ALICE])
    v = visit()
    assert schedule.can_manage(BEN, False, v, [])  # attending
    assert schedule.can_manage(CARA, False, v, [CARA])  # assigned to the request
    assert schedule.can_manage("admin", True, v, [])
    assert not schedule.can_manage(CARA, False, v, [])
    with pytest.raises(Forbidden):
        schedule.require_manage(CARA, False, v, [])


# --- changing a planned visit -------------------------------------------------------------------


@pytest.mark.req("VIS-2")
def test_rescheduling_changes_only_the_dates_and_names_what_changed():
    v = visit()
    edit = schedule.Edit(planned_start=NOW + timedelta(days=3), planned_end=NOW + timedelta(days=4))
    changes = schedule.edit_planned(v, edit, [S1, S2], [])
    assert changes.changed == ["dates"] and set(changes.fields) == {"planned_start", "planned_end"}
    assert changes.owner_changes == []


@pytest.mark.req("VIS-1")
def test_an_owner_who_leaves_hands_the_station_to_the_lead_and_a_missing_lead_is_replaced():
    v = visit(lead_staff_id=ALICE)
    changes = schedule.edit_planned(v, schedule.Edit(staff_ids=[ALICE, CARA]), [S1, S2], [])
    assert changes.fields["staff_ids"] == [ALICE, CARA]
    assert changes.owner_changes == [(S2, BEN, ALICE)]
    assert {s["station_id"]: s["owner_staff_id"] for s in changes.fields["stations"]} == {
        S1: ALICE, S2: ALICE,
    }
    gone = schedule.edit_planned(v, schedule.Edit(staff_ids=[BEN, CARA]), [S1, S2], [])
    assert gone.fields["lead_staff_id"] == BEN and "lead" in gone.changed


@pytest.mark.req("VIS-1")
def test_adding_a_station_keeps_the_others_and_must_be_free():
    v = visit()
    details = {S3: {"code": "C3", "name": "Third", "time_zone": "America/Jamaica"}}
    edit = schedule.Edit(stations=[(S1, None), (S2, BEN), (S3, BEN)])
    changes = schedule.edit_planned(v, edit, [S1, S2, S3], [], details)
    added = changes.fields["stations"][2]
    assert added["station_id"] == S3 and added["station_code"] == "C3"
    assert added["owner_staff_id"] == BEN and added["arrived_at"] is None
    other = visit(stations=[schedule.new_station(S3, ALICE, {})])
    with pytest.raises(Conflict):
        schedule.edit_planned(v, edit, [S1, S2, S3], [other], details)


@pytest.mark.req("VIS-1")
def test_nothing_changed_is_an_empty_result():
    changes = schedule.edit_planned(visit(), schedule.Edit(), [S1, S2], [])
    assert changes.fields == {} and changes.changed == []


@pytest.mark.req("VIS-1")
def test_once_started_only_the_lead_or_an_admin_changes_owners():
    v = visit(status="started")
    changes = schedule.change_owners(v, {S1: BEN}, ALICE, False)
    assert changes.owner_changes == [(S1, ALICE, BEN)]
    assert changes.fields["stations"][0]["owner_staff_id"] == BEN
    assert schedule.change_owners(v, {S1: ALICE}, ALICE, False).fields == {}  # already so
    assert schedule.change_owners(v, {S1: BEN}, "admin", True).owner_changes
    with pytest.raises(Forbidden) as caught:
        schedule.change_owners(v, {S1: BEN}, BEN, False)
    assert caught.value.extra["code"] == "not_lead"
    with pytest.raises(ValidationFailed):
        schedule.change_owners(v, {S1: CARA}, ALICE, False)
    with pytest.raises(ValidationFailed):
        schedule.change_owners(v, {S3: ALICE}, ALICE, False)


# --- the lifecycle ------------------------------------------------------------------------------


@pytest.mark.req("VIS-4")
def test_starting_records_the_time_and_a_repeat_changes_nothing():
    v = visit()
    result = lifecycle.start(v, ALICE, False, None, NOW)
    assert result.fields == {"status": "started", "started_at": NOW}
    again = lifecycle.start({**v, "status": "started"}, ALICE, False, None, NOW)
    assert again.noop
    with pytest.raises(Forbidden) as caught:
        lifecycle.start(v, "stranger", False, None, NOW)
    assert caught.value.extra["code"] == "not_attending"
    assert lifecycle.start(v, "admin", True, None, NOW).fields["status"] == "started"


@pytest.mark.req("VIS-4")
def test_the_devices_time_is_taken_within_limits():
    assert lifecycle.check_at(None, NOW) == NOW
    assert lifecycle.check_at(NOW - timedelta(days=29), NOW)
    assert lifecycle.check_at(NOW + timedelta(minutes=4), NOW)
    for bad in (NOW + timedelta(minutes=6), NOW - timedelta(days=31)):
        with pytest.raises(ValidationFailed) as caught:
            lifecycle.check_at(bad, NOW)
        assert caught.value.extra["code"] == "bad_time"


@pytest.mark.req("VIS-4")
def test_only_the_owner_arrives_and_departs_and_only_in_that_order():
    v = visit(status="started")
    arrived = lifecycle.arrive(v, S1, ALICE, False, None, NOW)
    assert arrived.fields["stations"][0]["arrived_at"] == NOW
    assert arrived.fields["stations"][1]["arrived_at"] is None
    with pytest.raises(Forbidden) as caught:
        lifecycle.arrive(v, S1, BEN, False, None, NOW)  # Ben owns S2
    assert caught.value.extra["code"] == "not_owner"
    assert lifecycle.arrive(v, S1, "admin", True, None, NOW).fields
    with pytest.raises(Conflict) as caught:
        lifecycle.depart(v, S1, ALICE, False, None, NOW)
    assert caught.value.extra["code"] == "not_arrived"
    on_site = visit(status="started")
    on_site["stations"][0]["arrived_at"] = NOW - timedelta(hours=2)
    left = lifecycle.depart(on_site, S1, ALICE, False, NOW - timedelta(hours=1), NOW)
    assert left.fields["stations"][0]["departed_at"] == NOW - timedelta(hours=1)
    on_site["stations"][0]["departed_at"] = NOW
    assert lifecycle.depart(on_site, S1, ALICE, False, None, NOW).noop
    assert lifecycle.arrive(on_site, S1, ALICE, False, None, NOW).noop
    with pytest.raises(ValidationFailed):  # leaving before arriving
        late = visit(status="started")
        late["stations"][0]["arrived_at"] = NOW
        lifecycle.depart(late, S1, ALICE, False, NOW - timedelta(hours=1), NOW)
    with pytest.raises(NotFound):
        lifecycle.arrive(v, "st-unknown", ALICE, False, None, NOW)


@pytest.mark.req("VIS-4")
@pytest.mark.parametrize(("status", "code"), [
    ("planned", "not_started"), ("cancelled", "visit_cancelled"), ("ended", "already_ended"),
])
def test_arriving_needs_a_started_visit(status, code):
    with pytest.raises(Conflict) as caught:
        lifecycle.arrive(visit(status=status), S1, ALICE, False, None, NOW)
    assert caught.value.extra["code"] == code


@pytest.mark.req("VIS-9")
def test_ending_says_whether_another_visit_is_needed_and_what_remains():
    v = visit(status="started")
    done = lifecycle.end(v, ALICE, False, additional_visit_required=False, follow_up_notes=None,
                         at=None, now=NOW)
    assert done.fields["status"] == "ended" and done.fields["additional_visit_required"] is False
    with pytest.raises(ValidationFailed) as caught:
        lifecycle.end(v, ALICE, False, additional_visit_required=True, follow_up_notes="  ",
                      at=None, now=NOW)
    assert caught.value.extra["code"] == "notes_required"
    more = lifecycle.end(v, ALICE, False, additional_visit_required=True,
                         follow_up_notes=" Replace the mast ", at=None, now=NOW)
    assert more.fields["follow_up_notes"] == "Replace the mast"
    ended = {**v, "status": "ended", "additional_visit_required": True}
    assert lifecycle.end(ended, ALICE, False, additional_visit_required=True,
                         follow_up_notes="x", at=None, now=NOW).noop
    with pytest.raises(Conflict) as caught:  # a different answer after it ended
        lifecycle.end(ended, ALICE, False, additional_visit_required=False,
                      follow_up_notes=None, at=None, now=NOW)
    assert caught.value.extra["code"] == "already_ended"
    with pytest.raises(Conflict):  # not started yet
        lifecycle.end(visit(), ALICE, False, additional_visit_required=False,
                      follow_up_notes=None, at=None, now=NOW)


@pytest.mark.req("VIS-2")
def test_cancelling_and_restoring():
    cancelled = lifecycle.cancel(visit(), "Storm", NOW)
    assert cancelled.fields == {
        "status": "cancelled", "cancelled_at": NOW, "cancel_reason": "Storm",
    }
    assert lifecycle.cancel(visit(status="cancelled"), None, NOW).noop
    with pytest.raises(Conflict) as caught:
        lifecycle.cancel(visit(status="started"), None, NOW)
    assert caught.value.extra["code"] == "visit_started"
    with pytest.raises(Conflict) as caught:
        lifecycle.cancel(visit(status="ended"), None, NOW)
    assert caught.value.extra["code"] == "already_ended"
    back = lifecycle.restore(visit(status="cancelled"))
    assert back.fields["status"] == "planned"
    assert lifecycle.restore(visit()).noop
    with pytest.raises(Conflict):
        lifecycle.restore(visit(status="started"))


# --- the request's status from its visits (ADR-17) ---------------------------------------------


def request(status: str = "assigned", **over: Any) -> dict[str, Any]:
    return {"status": status, **over}


@pytest.mark.req("ADR-17")
def test_a_planned_visit_makes_the_request_scheduled_and_a_started_one_in_progress():
    planned = visit()
    assert recompute(request(), [planned]).status is Status.SCHEDULED
    started = visit(status="started", started_at=NOW)
    settled = recompute(request("scheduled"), [started])
    assert settled.status is Status.IN_PROGRESS and settled.first_visit_at == NOW


@pytest.mark.req("ADR-17")
def test_parallel_visits_follow_the_busiest_and_a_cancelled_one_is_ignored():
    planned = visit()
    started = visit(status="started", started_at=NOW)
    cancelled = visit(status="cancelled")
    assert recompute(request("scheduled"), [planned, started]).status is Status.IN_PROGRESS
    assert recompute(request("scheduled"), [planned, cancelled]).status is Status.SCHEDULED
    assert recompute(request("scheduled"), [cancelled]).status is Status.ASSIGNED
    assert recompute(request("scheduled"), []).status is Status.ASSIGNED


@pytest.mark.req("ADR-17")
def test_a_finished_visit_asking_for_another_returns_the_request_to_assigned():
    ended = visit(status="ended", ended_at=NOW, additional_visit_required=True,
                  started_at=NOW - timedelta(hours=2))
    assert recompute(request("in_progress"), [ended]).status is Status.ASSIGNED
    done = {**ended, "additional_visit_required": False}
    # No visit report yet (Phase 6): the request waits in progress for it
    assert recompute(request("in_progress"), [done]).status is Status.IN_PROGRESS
    with_report = {**done, "report_status": "final"}
    assert recompute(request("in_progress"), [with_report]).status is Status.CLIENT_REVIEW


@pytest.mark.req("ADR-17")
@pytest.mark.parametrize("status", ["submitted", "approved", "denied", "reopened", "closed",
                                    "cancelled"])
def test_nothing_is_derived_outside_the_derived_statuses(status):
    settled = recompute(request(status), [visit(status="started", started_at=NOW)])
    assert settled.status.value == status
