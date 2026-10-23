"""Who is told about a visit, event by event (PRD VIS-11, NOT-1, NOT-5, Appendix B; W10 slice 4).
No I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.notifications import LIVE_EVENTS, NOTIFY_EVENTS, Audience, plan, when_text

ADMIN, TECH, TECH2, TECH3, VIEWER = "admin-1", "tech-1", "tech-2", "tech-3", "viewer-1"
CLIENT, CLIENT2, OTHER_ORG = "client-1", "client-2", "client-9"  # CLIENT made the request
AUDIENCE = Audience(
    admins=[ADMIN], staff=[ADMIN, TECH, TECH2, TECH3, VIEWER], org_clients=[CLIENT, CLIENT2],
)
START = datetime(2026, 10, 22, 13, 0, tzinfo=UTC)
VISIT: dict[str, Any] = {
    "visit_id": "v1", "ref": "VR-2026-0042-01", "request_id": "r1", "request_ref": "MR-2026-0042",
    "org_id": "o1", "title": "Rain gauge reads zero", "created_by": CLIENT, "status": "planned",
    "planned_start": START, "planned_end": datetime(2026, 10, 23, 21, 0, tzinfo=UTC),
    "staff_ids": [TECH, TECH2], "lead_staff_id": TECH2, "station_ids": ["s1", "s2"],
    "station_owners": [], "time_zone": "America/Jamaica",
}


def run(event: str, actor: str | None, extra: dict[str, Any] | None = None, **base: Any):
    return plan(event, {**VISIT, **base, **(extra or {})}, actor, "Andrea Clarke", AUDIENCE)


def who(drafts) -> list[str]:
    return sorted(d.user_id for d in drafts)


@pytest.mark.req("VIS-11")
def test_a_planned_visit_tells_the_client_and_everyone_attending_by_name_of_the_day():
    made = run("visit.scheduled", ADMIN)
    assert who(made.drafts) == sorted([CLIENT, TECH, TECH2])
    first = made.drafts[0]
    assert first.title == "Visit planned"
    assert first.body == "VR-2026-0042-01 · Rain gauge reads zero · Thu 22 Oct, 08:00 EST"
    assert first.link == "/visits/v1"
    assert (first.entity_type, first.entity_id, first.type) == ("visit", "v1", "visit.scheduled")


@pytest.mark.req("NOT-1")
def test_the_person_who_planned_it_is_not_told_and_a_colleague_is():
    made = run("visit.scheduled", TECH)
    assert who(made.drafts) == sorted([CLIENT, TECH2])


@pytest.mark.req("NOT-1")
def test_planned_new_dates_and_cancelled_are_the_ones_worth_an_email():
    for event in ("visit.scheduled", "visit.rescheduled"):
        assert all(d.email for d in run(event, ADMIN).drafts)
        assert {d.type for d in run(event, ADMIN).drafts} == {"visit.scheduled"}
    cancelled = run("visit.cancelled", ADMIN, {"reason": "Storm warning", "by_request": False})
    assert all(d.email for d in cancelled.drafts)
    assert {d.type for d in cancelled.drafts} == {"visit.cancelled"}
    assert not any(d.email for d in run("visit.ended", ADMIN, {"ended_at": START}).drafts)


@pytest.mark.req("VIS-2")
def test_new_dates_say_when():
    made = run("visit.rescheduled", ADMIN, {"changed_fields": ["dates"]},
               planned_start=datetime(2026, 10, 26, 13, 0, tzinfo=UTC))
    assert made.drafts[0].title == "Visit rescheduled"
    assert made.drafts[0].body.endswith("now Mon 26 Oct, 08:00 EST")


@pytest.mark.req("VIS-2")
def test_a_cancelled_visit_does_not_repeat_the_text_of_its_reason():
    made = run("visit.cancelled", ADMIN, {"reason": "Secret reason", "by_request": False},
               status="cancelled")
    assert who(made.drafts) == sorted([CLIENT, TECH, TECH2])
    assert "Secret reason" not in repr(made)


@pytest.mark.req("VIS-2")
def test_a_visit_cancelled_with_its_request_leaves_the_news_to_the_request():
    made = run("visit.cancelled", ADMIN, {"reason": None, "by_request": True}, status="cancelled")
    assert made.drafts == []
    assert {item.user_id for item in made.live} >= {CLIENT, TECH}  # open pages still look again


@pytest.mark.req("VIS-9")
def test_an_ended_visit_tells_the_staff_attending_not_the_client():
    made = run("visit.ended", TECH, {
        "ended_at": START, "additional_visit_required": True, "follow_up_notes": "Panel",
        "overrides": [], "sensor_actions": [], "config_versions": [],
    }, status="ended")
    assert who(made.drafts) == [TECH2]
    assert made.drafts[0].title == "Visit ended"
    assert made.drafts[0].body == "VR-2026-0042-01 · another visit needed"
    assert "Panel" not in repr(made)  # the notes stay on the page


@pytest.mark.req("VIS-3")
def test_a_new_owner_and_the_old_one_both_hear_not_the_person_who_changed_it():
    changed = run("visit.station_owner_changed", TECH2, {
        "station_id": "s1", "from_staff_id": TECH, "to_staff_id": TECH3,
        "station_name": "Kingston Harbour", "station_code": "JM-KIN-001",
    }, status="started")
    titles = {d.user_id: d.title for d in changed.drafts}
    assert titles == {TECH3: "You now own Kingston Harbour",
                      TECH: "You no longer own Kingston Harbour"}
    assert all(d.type == "visit.owner_changed" and not d.email for d in changed.drafts)
    assert changed.drafts[0].body == "VR-2026-0042-01 · changed by Andrea Clarke"
    # ... and the lead who changes their own station tells only the other person
    own = run("visit.station_owner_changed", TECH, {
        "station_id": "s1", "from_staff_id": TECH, "to_staff_id": TECH3,
    }, status="started")
    assert who(own.drafts) == [TECH3]
    assert own.drafts[0].title == "You now own a station"


@pytest.mark.req("NOT-5")
def test_every_visit_event_goes_live_to_staff_and_the_organization_with_its_request():
    for event in ("visit.scheduled", "visit.rescheduled", "visit.cancelled", "visit.restored",
                  "visit.started", "visit.ended", "visit.station_owner_changed",
                  "visit.station_arrived", "visit.station_departed", "visit.media_changed",
                  "visit.element_added", "visit.element_updated", "visit.element_deleted"):
        assert event in LIVE_EVENTS
        made = run(event, ADMIN, {"station_id": "s1", "from_staff_id": TECH, "to_staff_id": TECH2,
                                  "by_request": False, "additional_visit_required": False})
        assert {item.user_id for item in made.live} == {*AUDIENCE.staff, CLIENT, CLIENT2}
        assert {(i.entity, i.entity_id, i.request_id, i.kind) for i in made.live} == {
            ("visit", "v1", "r1", "visit"),
        }


@pytest.mark.req("NOT-5")
def test_arriving_and_starting_are_live_only():
    for event in ("visit.started", "visit.station_arrived", "visit.station_departed",
                  "visit.restored", "visit.media_changed", "visit.element_added",
                  "visit.element_updated", "visit.element_deleted"):
        assert event not in NOTIFY_EVENTS
        assert run(event, TECH, {"station_id": "s1"}).drafts == []


@pytest.mark.req("NOT-1")
def test_nobody_is_listed_twice_when_the_client_also_attends():
    made = run("visit.scheduled", ADMIN, created_by=TECH, staff_ids=[TECH, TECH2, TECH])
    ids = [d.user_id for d in made.drafts]
    assert len(ids) == len(set(ids)) == 2


def test_the_day_is_written_in_the_zone_of_the_visit():
    assert when_text({"planned_start": START, "time_zone": "America/Jamaica"}) == (
        "Thu 22 Oct, 08:00 EST")
    assert when_text({"planned_start": START, "time_zone": "Europe/London"}) == (
        "Thu 22 Oct, 14:00 BST")
    # No zone, or one the server doesn't know: UTC, said plainly
    assert when_text({"planned_start": START}) == "Thu 22 Oct, 13:00 UTC"
    assert when_text({"planned_start": START, "time_zone": "Mars/Olympus"}) == (
        "Thu 22 Oct, 13:00 UTC")
    assert when_text({"planned_start": START.isoformat()}) == "Thu 22 Oct, 13:00 UTC"


@pytest.mark.req("OFF-11")
def test_a_phones_work_that_came_back_tells_the_lead_and_the_admins_not_the_clients():
    assert "visit.sync_conflict" in NOTIFY_EVENTS
    made = run("visit.sync_conflict", TECH, {
        "user_id": TECH, "reason": "not_owner", "op_types": ["station.arrive"],
    })
    assert who(made.drafts) == sorted([ADMIN, TECH2])  # the lead (TECH2) and the admin
    assert all(d.type == "visit.sync_conflict" and not d.email for d in made.drafts)
    assert made.drafts[0].title == "Work came back: the owner changed"
    assert made.drafts[0].body.startswith("VR-2026-0042-01 · Andrea Clarke: ")
    assert made.drafts[0].link == "/visits/v1"
    # the technician whose phone it was is not told by the platform, and the client never is
    assert TECH not in who(made.drafts) and CLIENT not in who(made.drafts)


def test_a_conflict_that_needs_nobody_is_not_announced():
    for reason in ("locked", "element_changed", "element_deleted", "already_ended"):
        assert run("visit.sync_conflict", TECH, {"user_id": TECH, "reason": reason,
                                                 "op_types": ["element.update"]}).drafts == []


def test_a_cancelled_visit_asks_for_a_restore():
    made = run("visit.sync_conflict", TECH, {"user_id": TECH, "reason": "visit_cancelled",
                                             "op_types": ["visit.start"]}, status="cancelled")
    assert made.drafts[0].title == "Work recorded on a cancelled visit"
    assert "restore the visit" in made.drafts[0].body
