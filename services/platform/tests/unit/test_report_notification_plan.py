"""Who is told that a draft report is ready (PRD RPT-1, Appendix B "Visit ended (draft report
ready)"; W16-11). No I/O."""

from __future__ import annotations

import pytest

from app.domain.notifications import NOTIFY_EVENTS, Audience, plan

ADMIN, TECH, TECH2, CLIENT = "admin-1", "tech-1", "tech-2", "client-1"
AUDIENCE = Audience(admins=[ADMIN], staff=[ADMIN, TECH, TECH2], org_clients=[CLIENT])
DRAFTED = {
    "report_id": "r1", "number": "VR-2026-0042-02", "version": 1, "visit_id": "v1",
    "request_id": "q1", "request_ref": "MR-2026-0042", "org_id": "o1",
    "title": "Rain gauge not reporting", "staff_ids": [TECH, TECH2], "lead_staff_id": TECH,
}


@pytest.mark.req("RPT-1")
def test_the_people_who_attended_hear_that_the_draft_is_ready_in_the_app_only():
    made = plan("report.drafted", DRAFTED, None, None, AUDIENCE)
    assert sorted(d.user_id for d in made.drafts) == [TECH, TECH2]
    first = made.drafts[0]
    assert first.title == "Draft report ready"
    assert first.body == "VR-2026-0042-02 · Rain gauge not reporting"
    assert first.link == "/visits/v1" and (first.entity_type, first.entity_id) == ("visit", "v1")
    assert first.type == "report.drafted" and not any(d.email for d in made.drafts)


@pytest.mark.req("RPT-1")
def test_no_client_and_no_admin_who_was_not_there_is_told_of_a_draft():
    made = plan("report.drafted", DRAFTED, None, None, AUDIENCE)
    assert CLIENT not in {d.user_id for d in made.drafts}
    assert ADMIN not in {d.user_id for d in made.drafts}


def test_the_event_is_one_the_notification_module_handles_and_holds_no_report_text():
    assert "report.drafted" in NOTIFY_EVENTS
    assert not {"content", "narrative", "facts", "stations"} & set(DRAFTED)
