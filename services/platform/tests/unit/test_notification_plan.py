"""Who is told what (PRD NOT-1, NOT-5, Appendix B; W9-10, W9-11), event by event. No I/O."""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.notifications import Audience, plan

ADMIN, ADMIN2 = "admin-1", "admin-2"
TECH, TECH2, VIEWER = "tech-1", "tech-2", "viewer-1"
CLIENT, CLIENT2 = "client-1", "client-2"  # CLIENT made the request; CLIENT2 is a colleague
AUDIENCE = Audience(
    admins=[ADMIN, ADMIN2], staff=[ADMIN, ADMIN2, TECH, TECH2, VIEWER],
    org_clients=[CLIENT, CLIENT2],
)
REQUEST: dict[str, Any] = {
    "request_id": "r1", "ref": "MR-2026-0034", "org_id": "o1", "station_ids": ["s1"],
    "category": "fault", "priority": "high", "status": "approved",
    "title": "Logger not reporting", "created_by": CLIENT, "assigned_staff_ids": [],
}


def who(drafts) -> list[str]:
    return sorted(d.user_id for d in drafts)


def run(event: str, actor: str | None, extra: dict[str, Any], audience: Audience = AUDIENCE,
        **base: Any):
    return plan(event, {**REQUEST, **base, **extra}, actor, "Actor Name", audience)


# --- Accounts ----------------------------------------------------------------------------------


@pytest.mark.req("NOT-1")
def test_a_new_registration_tells_the_admins():
    made = plan("user.registered", {"user_id": "u9", "name": "Samir Khan",
                                    "proposed_org_name": "Authority C"}, None, None, AUDIENCE)
    assert who(made.drafts) == [ADMIN, ADMIN2]
    assert made.drafts[0].type == "account.registered"
    assert made.drafts[0].link == "/admin/registrations/u9"
    assert "Samir Khan" in made.drafts[0].body and made.live == []


# --- Requests ----------------------------------------------------------------------------------


@pytest.mark.req("NOT-1")
def test_a_client_request_tells_the_admins_and_an_admin_made_one_tells_nobody():
    client_made = run("request.submitted", CLIENT, {"by_admin": False}, status="submitted")
    assert who(client_made.drafts) == [ADMIN, ADMIN2]
    admin_made = run("request.submitted", ADMIN, {"by_admin": True})
    assert admin_made.drafts == []


@pytest.mark.req("NOT-1")
def test_the_decision_goes_to_the_client_who_asked():
    assert who(run("request.approved", ADMIN, {}).drafts) == [CLIENT]
    denied = run("request.denied", ADMIN, {"reason": "Out of contract"}, status="denied")
    assert who(denied.drafts) == [CLIENT]
    assert "Out of contract" not in str(denied.drafts)  # the page shows the reason, not a list


@pytest.mark.req("NOT-1")
def test_a_claim_tells_the_client_and_the_admins_but_not_the_claimant():
    claimed = run("request.assigned", TECH, {
        "staff_ids": [TECH], "staff_names": ["Tech One"], "claimed": True, "by_id": TECH,
    }, assigned_staff_ids=[TECH], status="assigned")
    by_user = {d.user_id: d for d in claimed.drafts}
    assert sorted(by_user) == [ADMIN, ADMIN2, CLIENT]
    assert by_user[CLIENT].title == "A technician is on it"
    assert by_user[ADMIN].title == "Actor Name claimed MR-2026-0034"


@pytest.mark.req("NOT-1")
def test_an_admin_assigning_tells_the_staff_and_the_client_not_the_other_admins():
    assigned = run("request.assigned", ADMIN, {
        "staff_ids": [TECH, TECH2], "staff_names": ["A", "B"], "claimed": False, "by_id": ADMIN,
    }, assigned_staff_ids=[TECH, TECH2], status="assigned")
    assert who(assigned.drafts) == [CLIENT, TECH, TECH2]
    mine = next(d for d in assigned.drafts if d.user_id == TECH)
    assert mine.title == "Assigned to you" and mine.link == "/requests/r1"


@pytest.mark.req("NOT-1")
def test_changing_staff_tells_who_was_added_and_who_was_removed():
    changed = run("request.staff_changed", ADMIN, {
        "staff_ids": [TECH2], "staff_names": ["B"], "added": [TECH2], "removed": [TECH],
    }, assigned_staff_ids=[TECH2], status="assigned")
    titles = {d.user_id: d.title for d in changed.drafts}
    assert titles == {TECH2: "Assigned to you", TECH: "Removed from a request"}


@pytest.mark.req("NOT-1")
def test_a_release_tells_the_other_admins_it_is_back_in_the_queue():
    released = run("request.released", TECH, {
        "released_ids": [TECH], "released_names": ["Tech One"], "by_id": TECH,
    })
    assert who(released.drafts) == [ADMIN, ADMIN2]
    assert released.drafts[0].body == "It is back in the queue"


@pytest.mark.req("NOT-1")
def test_a_cancellation_tells_everyone_involved_except_who_did_it():
    by_client = run("request.cancelled", CLIENT, {"reason": None, "cancelled_by": "client"},
                    assigned_staff_ids=[TECH], status="cancelled")
    assert who(by_client.drafts) == [ADMIN, ADMIN2, TECH]
    by_admin = run("request.cancelled", ADMIN, {"reason": "x", "cancelled_by": "admin"},
                   assigned_staff_ids=[TECH], status="cancelled")
    assert who(by_admin.drafts) == [ADMIN2, CLIENT, TECH]


# --- Comments ----------------------------------------------------------------------------------


def comment(author: str, role: str, *, internal: bool, **base: Any):
    return run("comment.added", author, {
        "comment_id": "c1", "author_id": author, "author_name": "Someone", "author_role": role,
        "internal": internal, "attachment_count": 0,
    }, **base)


@pytest.mark.req("NOT-1")
def test_a_client_comment_tells_the_staff_on_the_request():
    made = comment(CLIENT, "client", internal=False, assigned_staff_ids=[TECH, TECH2])
    assert who(made.drafts) == [TECH, TECH2]


@pytest.mark.req("NOT-1")
def test_a_comment_on_a_request_nobody_holds_tells_the_admins():
    assert who(comment(CLIENT, "client", internal=False).drafts) == [ADMIN, ADMIN2]


@pytest.mark.req("NOT-1")
def test_a_staff_comment_tells_the_client_and_the_other_staff():
    made = comment(TECH, "technician", internal=False, assigned_staff_ids=[TECH, TECH2])
    assert who(made.drafts) == [CLIENT, TECH2]


@pytest.mark.req("REQ-10")
def test_an_internal_comment_never_tells_a_client_in_any_way():
    made = comment(TECH, "technician", internal=True, assigned_staff_ids=[TECH, TECH2])
    assert who(made.drafts) == [TECH2]
    assert made.drafts[0].body.endswith("Internal comment")
    assert CLIENT not in who(made.drafts)
    # ... and no live message to a client either, so an open page learns nothing of it
    assert {item.user_id for item in made.live} == set(AUDIENCE.staff)


@pytest.mark.req("REQ-10")
def test_no_notification_carries_a_comment_text():
    # The event has no body field at all (W9-8); even if one slipped in, plan() never reads it
    made = comment(TECH, "technician", internal=True, assigned_staff_ids=[TECH2], body="Secret")
    assert "Secret" not in repr(made)


# --- Live updates (NOT-5) ----------------------------------------------------------------------


@pytest.mark.req("NOT-5")
def test_a_status_change_goes_live_to_all_staff_and_the_organization():
    made = run("request.status_changed", ADMIN, {"from_status": "submitted",
                                                 "to_status": "approved", "reason": None})
    assert {item.user_id for item in made.live} == {*AUDIENCE.staff, CLIENT, CLIENT2}
    assert {item.kind for item in made.live} == {"status"}
    assert made.drafts == []


@pytest.mark.req("NOT-5")
def test_a_comment_made_internal_later_still_reaches_clients_so_their_page_drops_it():
    flipped = run("comment.updated", TECH, {
        "comment_id": "c1", "author_id": TECH, "author_name": "T", "author_role": "technician",
        "internal": True, "attachment_count": 0, "body_changed": False, "internal_changed": True,
    })
    assert CLIENT in {item.user_id for item in flipped.live}
    quiet = run("comment.updated", TECH, {
        "comment_id": "c1", "author_id": TECH, "author_name": "T", "author_role": "technician",
        "internal": True, "attachment_count": 0, "body_changed": True, "internal_changed": False,
    })
    assert CLIENT not in {item.user_id for item in quiet.live}


def test_events_nobody_cares_about_make_nothing():
    assert run("station.updated", ADMIN, {}).drafts == []
    assert run("station.updated", ADMIN, {}).live == []


def test_nobody_is_listed_twice():
    made = run("request.cancelled", ADMIN, {"reason": "x", "cancelled_by": "admin"},
               assigned_staff_ids=[TECH, TECH, ADMIN2], status="cancelled")
    ids = [d.user_id for d in made.drafts]
    assert len(ids) == len(set(ids))
