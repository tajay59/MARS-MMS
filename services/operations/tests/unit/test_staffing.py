"""Assigning, claiming and releasing (PRD REQ-7, W9-1 to W9-4): who ends up on a request and
which status follows. No I/O."""

from __future__ import annotations

import itertools

import pytest
from mms_common.errors import Conflict, Forbidden, ValidationFailed

from app.domain.requests import staffing
from app.domain.requests.staffing import Person
from app.domain.requests.state import Action, Status, Who

DEVON = Person("d", "Devon Brown")
MAYA = Person("m", "Maya Clarke")
KOFI = Person("k", "Kofi Osei")


def user(roles: list[str], status: str = "active", name: str = "Someone") -> dict[str, object]:
    return {"roles": roles, "status": status, "name": name}


# --- Choosing people ---------------------------------------------------------------------------


@pytest.mark.req("REQ-7")
def test_at_least_one_and_no_more_than_ten_people_each_once():
    assert staffing.clean_staff_ids(["a", "b", "a"]) == ["a", "b"]
    with pytest.raises(ValidationFailed) as caught:
        staffing.clean_staff_ids([])
    assert caught.value.extra["field"] == "staff_ids"
    with pytest.raises(ValidationFailed) as caught:
        staffing.clean_staff_ids([str(i) for i in range(11)])
    assert caught.value.extra["code"] == "too_many_staff"


@pytest.mark.req("REQ-7")
def test_only_active_technicians_and_admins_can_be_assigned_in_the_order_given():
    found = {
        "t": user(["technician"], name="Tess"), "a": user(["admin"], name="Ann"),
        "ta": user(["technician", "admin"], name="Both"),
    }
    people = staffing.check_assignable(["a", "t", "ta"], found)
    assert [p.name for p in people] == ["Ann", "Tess", "Both"]
    for bad in (
        {"x": user(["viewer"])}, {"x": user(["client"])}, {"x": user(["technician"], "disabled")},
        {"x": user(["admin"], "pending")}, {},
    ):
        with pytest.raises(ValidationFailed) as caught:
            staffing.check_assignable(["x"], bad)
        assert caught.value.extra["code"] == "not_assignable"


# --- Assigning ---------------------------------------------------------------------------------


@pytest.mark.req("REQ-7")
def test_an_admin_assigning_an_approved_request_makes_it_assigned():
    change = staffing.assign(Status.APPROVED, Who.ADMIN, [], [DEVON, MAYA])
    assert change.to is Status.ASSIGNED and change.action is Action.ASSIGN
    assert [p.id for p in change.staff] == ["d", "m"] and change.added == ("d", "m")


@pytest.mark.req("REQ-7")
def test_an_admin_changes_the_staff_of_an_assigned_request_without_a_status_change():
    change = staffing.assign(Status.ASSIGNED, Who.ADMIN, [DEVON, MAYA], [MAYA, KOFI])
    assert change.to is None and change.action is None
    assert change.added == ("k",) and change.removed == ("d",)
    assert [p.id for p in change.staff] == ["m", "k"]


@pytest.mark.req("REQ-7")
def test_assigning_the_same_people_again_changes_nothing():
    with pytest.raises(Conflict) as caught:
        staffing.assign(Status.ASSIGNED, Who.ADMIN, [DEVON, MAYA], [MAYA, DEVON])
    assert caught.value.extra["code"] == "no_change"


@pytest.mark.parametrize(
    "status", [s for s in Status if s not in (Status.APPROVED, Status.ASSIGNED)],
)
def test_staff_are_set_only_while_the_request_is_approved_or_assigned(status):
    """From Scheduled on, visits decide who is on the work (Phase 4)."""
    with pytest.raises(Conflict) as caught:
        staffing.assign(status, Who.ADMIN, [], [DEVON])
    assert caught.value.extra["code"] == "bad_transition"


def test_a_technician_cannot_assign_others():
    with pytest.raises(Forbidden):
        staffing.assign(Status.APPROVED, Who.CLIENT, [], [DEVON])
    with pytest.raises(Forbidden):
        staffing.assign(Status.ASSIGNED, Who.TECHNICIAN, [DEVON], [MAYA])


# --- Claiming ----------------------------------------------------------------------------------


@pytest.mark.req("REQ-7")
@pytest.mark.parametrize("who", [Who.TECHNICIAN, Who.ADMIN])
def test_staff_claim_an_approved_request_for_themselves(who):
    change = staffing.claim(Status.APPROVED, who, DEVON, [])
    assert change.to is Status.ASSIGNED and [p.id for p in change.staff] == ["d"]


@pytest.mark.req("REQ-7")
def test_a_request_someone_else_has_claimed_says_who():
    with pytest.raises(Conflict) as caught:
        staffing.claim(Status.ASSIGNED, Who.TECHNICIAN, KOFI, [DEVON])
    assert caught.value.extra["code"] == "already_assigned"
    assert caught.value.extra["claimed_by"] == ["Devon Brown"]


@pytest.mark.parametrize(
    "status", [s for s in Status if s not in (Status.APPROVED, Status.ASSIGNED)],
)
def test_nothing_else_can_be_claimed(status):
    with pytest.raises(Conflict) as caught:
        staffing.claim(status, Who.TECHNICIAN, DEVON, [])
    assert caught.value.extra["code"] == "bad_transition"


def test_a_client_cannot_claim():
    with pytest.raises(Forbidden):
        staffing.claim(Status.APPROVED, Who.CLIENT, DEVON, [])


# --- Releasing ---------------------------------------------------------------------------------


@pytest.mark.req("REQ-7")
def test_the_only_person_releasing_puts_the_request_back_in_the_queue():
    change = staffing.release(Status.ASSIGNED, Who.TECHNICIAN, DEVON, [DEVON])
    assert change.to is Status.APPROVED and change.action is Action.RELEASE
    assert change.staff == () and change.removed == ("d",)


@pytest.mark.req("REQ-7")
def test_one_of_two_releasing_leaves_the_other_on_the_request():
    change = staffing.release(Status.ASSIGNED, Who.TECHNICIAN, DEVON, [DEVON, MAYA])
    assert change.to is None and change.action is None
    assert [p.id for p in change.staff] == ["m"] and change.removed == ("d",)


@pytest.mark.req("REQ-7")
def test_an_admin_unassigns_everyone():
    change = staffing.release(Status.ASSIGNED, Who.ADMIN, KOFI, [DEVON, MAYA])
    assert change.to is Status.APPROVED and change.removed == ("d", "m")


def test_a_technician_cannot_release_someone_elses_claim():
    with pytest.raises(Forbidden):
        staffing.release(Status.ASSIGNED, Who.TECHNICIAN, KOFI, [DEVON])
    with pytest.raises(Forbidden):
        staffing.release(Status.ASSIGNED, Who.CLIENT, DEVON, [DEVON])


@pytest.mark.parametrize("status", [s for s in Status if s is not Status.ASSIGNED])
def test_only_an_assigned_request_can_be_released(status):
    with pytest.raises(Conflict):
        staffing.release(status, Who.ADMIN, DEVON, [DEVON])


# --- What the page offers ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "who", "staff", "expected"),
    [
        (Status.APPROVED, Who.TECHNICIAN, [], ["claim"]),
        (Status.APPROVED, Who.ADMIN, [], ["claim", "assign"]),
        (Status.ASSIGNED, Who.ADMIN, ["d"], ["assign", "release"]),
        (Status.ASSIGNED, Who.TECHNICIAN, ["d"], ["release"]),   # d is the viewer: see `me`
        (Status.ASSIGNED, Who.TECHNICIAN, ["k"], []),
        (Status.APPROVED, Who.CLIENT, [], []),
        (Status.APPROVED, None, [], []),
        (Status.SUBMITTED, Who.ADMIN, [], []),
        (Status.SCHEDULED, Who.ADMIN, ["d"], []),
    ],
)
def test_the_buttons_offered(status, who, staff, expected):
    assert staffing.actions_for(status, who, "d", staff) == expected


def test_every_status_and_person_gets_a_list():
    for status, who in itertools.product(Status, [*Who, None]):
        assert isinstance(staffing.actions_for(status, who, "d", ["d"]), list)
