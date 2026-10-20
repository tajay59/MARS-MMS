"""The request state machine (PRD §5.1, REQ-5, REQ-6, REQ-7, REQ-11): a test for every allowed
and every blocked move, so adding a row to `RULES` can't open a door by accident. No I/O."""

from __future__ import annotations

import itertools

import pytest
from mms_common.errors import Conflict, Forbidden, ValidationFailed

from app.domain.requests import rules
from app.domain.requests.state import (
    CLIENT_EDITABLE,
    DERIVED,
    MILESTONES,
    RULES,
    TERMINAL,
    Action,
    Status,
    Who,
    transition,
)

ALLOWED = {
    # (from, action): (to, who may, reason needed)
    (Status.SUBMITTED, Action.APPROVE): (Status.APPROVED, {Who.ADMIN}, False),
    (Status.SUBMITTED, Action.DENY): (Status.DENIED, {Who.ADMIN}, True),
    (Status.APPROVED, Action.ASSIGN): (Status.ASSIGNED, {Who.ADMIN, Who.TECHNICIAN}, False),
    (Status.SUBMITTED, Action.CANCEL): (Status.CANCELLED, {Who.CLIENT, Who.ADMIN}, False),
    (Status.APPROVED, Action.CANCEL): (Status.CANCELLED, {Who.CLIENT, Who.ADMIN}, False),
    (Status.ASSIGNED, Action.CANCEL): (Status.CANCELLED, {Who.CLIENT, Who.ADMIN}, False),
    (Status.SCHEDULED, Action.CANCEL): (Status.CANCELLED, {Who.ADMIN}, True),
    (Status.IN_PROGRESS, Action.CANCEL): (Status.CANCELLED, {Who.ADMIN}, True),
    (Status.CLIENT_REVIEW, Action.CANCEL): (Status.CANCELLED, {Who.ADMIN}, True),
    (Status.CLIENT_REVIEW, Action.ACCEPT): (Status.CLOSED, {Who.CLIENT}, False),
    (Status.CLIENT_REVIEW, Action.REJECT): (Status.REOPENED, {Who.CLIENT}, True),
    (Status.CLIENT_REVIEW, Action.AUTO_CLOSE): (Status.CLOSED, {Who.SYSTEM}, False),
    (Status.REOPENED, Action.RETURN): (Status.ASSIGNED, {Who.SYSTEM}, False),
}


def test_the_table_is_exactly_the_documented_moves():
    assert {k: (r.to, set(r.who), r.reason) for k, r in RULES.items()} == ALLOWED


@pytest.mark.req("REQ-5")
@pytest.mark.parametrize(("key", "expected"), list(ALLOWED.items()))
def test_every_allowed_move_works_for_the_right_people(key, expected):
    status, action = key
    to, who_may, reason_needed = expected
    for who in who_may:
        got = transition(
            status, action, who, reason="because" if reason_needed else None, staff_count=1
        )
        assert got is to


@pytest.mark.req("REQ-5")
@pytest.mark.parametrize(("key", "expected"), list(ALLOWED.items()))
def test_every_allowed_move_is_refused_to_everyone_else(key, expected):
    status, action = key
    _, who_may, _ = expected
    for who in set(Who) - who_may:
        with pytest.raises(Forbidden):
            transition(status, action, who, reason="because", staff_count=1)


@pytest.mark.req("REQ-5")
@pytest.mark.parametrize(
    ("status", "action"),
    [pair for pair in itertools.product(Status, Action) if pair not in ALLOWED],
)
def test_every_other_move_is_blocked_for_everyone(status, action):
    """The other 67 of the 80 status and action pairs are impossible: Conflict, whoever asks."""
    for who in Who:
        with pytest.raises(Conflict) as caught:
            transition(status, action, who, reason="because", staff_count=1)
        assert caught.value.extra["code"] == "bad_transition"


@pytest.mark.parametrize("status", sorted(TERMINAL))
def test_nothing_leaves_a_finished_request(status):
    for action, who in itertools.product(Action, Who):
        with pytest.raises(Conflict):
            transition(status, action, who, reason="because", staff_count=1)


@pytest.mark.req("REQ-6")
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_a_denial_needs_a_reason(reason):
    with pytest.raises(ValidationFailed) as caught:
        transition(Status.SUBMITTED, Action.DENY, Who.ADMIN, reason=reason)
    assert caught.value.extra["field"] == "reason"


@pytest.mark.req("REQ-11")
def test_an_admin_cancels_planned_work_only_with_a_reason():
    for status in (Status.SCHEDULED, Status.IN_PROGRESS, Status.CLIENT_REVIEW):
        with pytest.raises(ValidationFailed):
            transition(status, Action.CANCEL, Who.ADMIN)
        assert transition(status, Action.CANCEL, Who.ADMIN, reason="Station decommissioned") \
            is Status.CANCELLED


@pytest.mark.req("REQ-11")
def test_a_client_cancels_only_up_to_assigned_and_only_their_own():
    for status in CLIENT_EDITABLE:
        assert transition(status, Action.CANCEL, Who.CLIENT) is Status.CANCELLED
        with pytest.raises(Forbidden):
            transition(status, Action.CANCEL, Who.CLIENT, own=False)
    for status in (Status.SCHEDULED, Status.IN_PROGRESS, Status.CLIENT_REVIEW):
        with pytest.raises(Forbidden):
            transition(status, Action.CANCEL, Who.CLIENT, reason="no")


@pytest.mark.req("REQ-7")
def test_assigning_needs_someone_to_assign():
    with pytest.raises(ValidationFailed) as caught:
        transition(Status.APPROVED, Action.ASSIGN, Who.ADMIN, staff_count=0)
    assert caught.value.extra["field"] == "staff_ids"


def test_derived_statuses_are_set_by_visits_not_by_actions():
    """Nothing in the table moves a request into Scheduled or In progress (ADR-17)."""
    assert not {Status.SCHEDULED, Status.IN_PROGRESS} & {r.to for r in RULES.values()}
    # Assigned and Client Review are reached by an action only from where visits don't decide
    assert {k[0] for k, r in RULES.items() if r.to is Status.ASSIGNED} == {
        Status.APPROVED, Status.REOPENED,
    }
    assert DERIVED == {Status.ASSIGNED, Status.SCHEDULED, Status.IN_PROGRESS, Status.CLIENT_REVIEW}


@pytest.mark.req("REQ-16")
def test_milestones_name_the_timestamps_turnaround_is_measured_from():
    assert MILESTONES[Status.SUBMITTED] == "submitted_at"
    assert MILESTONES[Status.CLOSED] == "closed_at"
    assert set(MILESTONES) <= set(Status)


# --- Creating and editing (REQ-1, REQ-4, REQ-11) ----------------------------------------------


@pytest.mark.req("REQ-4")
def test_a_reference_is_the_year_and_a_four_digit_number():
    assert rules.format_ref(2026, 42) == "MR-2026-0042"
    assert rules.format_ref(2026, 12345) == "MR-2026-12345"
    assert rules.counter_key(2026) == "MR-2026"


@pytest.mark.req("REQ-1")
def test_stations_are_unique_in_order_and_at_least_one():
    assert rules.clean_stations(["a", "b", "a", "c"]) == ["a", "b", "c"]
    with pytest.raises(ValidationFailed):
        rules.clean_stations([])
    with pytest.raises(ValidationFailed):
        rules.clean_stations([str(i) for i in range(rules.MAX_STATIONS + 1)])


@pytest.mark.req("REQ-1")
def test_text_is_trimmed_required_and_bounded():
    assert rules.clean_text("  Wind sensor stuck ", "title", maximum=200) == "Wind sensor stuck"
    with pytest.raises(ValidationFailed):
        rules.clean_text("   ", "title", maximum=200)
    assert rules.clean_text("", "description", maximum=10, required=False) == ""
    with pytest.raises(ValidationFailed):
        rules.clean_text("x" * 11, "description", maximum=10)


def test_every_station_must_belong_to_the_requests_organization():
    mine = {"owner_org_id": "org-a"}
    rules.check_stations_belong("org-a", [mine, mine], ["s1", "s2"])
    with pytest.raises(ValidationFailed):
        rules.check_stations_belong("org-a", [mine, {"owner_org_id": "org-b"}], ["s1", "s2"])
    with pytest.raises(ValidationFailed):  # one the person can't see is simply not there
        rules.check_stations_belong("org-a", [mine, None], ["s1", "s2"])


@pytest.mark.req("REQ-11")
def test_who_may_edit_when():
    for status in Status:
        if status in CLIENT_EDITABLE:
            rules.check_can_edit(status, Who.CLIENT)
        else:
            with pytest.raises(ValidationFailed):
                rules.check_can_edit(status, Who.CLIENT)
        if status in TERMINAL:
            with pytest.raises(ValidationFailed):
                rules.check_can_edit(status, Who.ADMIN)
        else:
            rules.check_can_edit(status, Who.ADMIN)
        for who in (Who.TECHNICIAN, Who.SYSTEM):
            with pytest.raises(Forbidden):
                rules.check_can_edit(status, who)


def test_changed_fields_lists_only_editable_fields_that_differ():
    before = {"title": "a", "description": "d", "category": "fault", "priority": "low",
              "station_ids": ["s1"], "status": "submitted"}
    after = {**before, "title": "b", "station_ids": ["s1", "s2"], "status": "approved"}
    assert rules.changed_fields(before, after) == ["title", "station_ids"]
