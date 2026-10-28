"""Who is told of Client Review, the client's answer, client reports and the close-out (PRD
REQ-12 to REQ-14, CRP-1, RPT-8, Appendix B; W18-13), event by event. No I/O."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.domain.notifications import REVIEW_EVENTS, Audience, plan

ADMIN, ADMIN2 = "admin-1", "admin-2"
TECH, TECH2, VIEWER = "tech-1", "tech-2", "viewer-1"
CLIENT, CLIENT2 = "client-1", "client-2"  # two users of the same organization
AUDIENCE = Audience(
    admins=[ADMIN, ADMIN2], staff=[ADMIN, ADMIN2, TECH, TECH2, VIEWER],
    org_clients=[CLIENT, CLIENT2],
)
REQUEST: dict[str, Any] = {
    "request_id": "r1", "ref": "MR-2026-0042", "org_id": "o1", "station_ids": ["s1"],
    "category": "fault", "priority": "high", "status": "client_review",
    "title": "Rain gauge not reporting", "created_by": CLIENT, "assigned_staff_ids": [TECH],
}


def run(event: str, actor: str | None = None, **extra: Any):
    return plan(event, {**REQUEST, **extra}, actor, "Actor Name", AUDIENCE)


def who(drafts) -> list[str]:
    return sorted(d.user_id for d in drafts)


@pytest.mark.req("REQ-12")
def test_every_client_of_the_organization_is_asked_to_review_by_app_and_email():
    made = run("request.client_review_started")
    assert who(made.drafts) == [CLIENT, CLIENT2]
    first = made.drafts[0]
    assert first.type == "request.client_review" and first.title == "Work ready for your review"
    assert first.body == "MR-2026-0042 · Rain gauge not reporting"
    assert first.link == "/requests/r1/review" and first.entity_id == "r1"
    assert all(d.email for d in made.drafts)


@pytest.mark.req("REQ-14")
def test_a_reminder_says_how_long_and_when_it_closes_by_itself():
    made = run("request.review_reminder", day=7.0, auto_close_day=30.0)
    assert who(made.drafts) == [CLIENT, CLIENT2] and all(d.email for d in made.drafts)
    assert made.drafts[0].title == "Still waiting for your review"
    assert "waiting 7 days, closes by itself after 30" in made.drafts[0].body
    assert made.drafts[0].link == "/requests/r1/review" and "7.0" not in made.drafts[0].body
    short = run("request.review_reminder", day=0.5, auto_close_day=1.5)
    assert "waiting 0.5 days, closes by itself after 1.5" in short.drafts[0].body


@pytest.mark.req("REQ-13")
def test_a_rejection_tells_the_people_on_the_request_and_the_admins_with_the_reason():
    made = run("request.reopened", CLIENT, comment="The mast photo is the wrong site", by_id=CLIENT,
               status="assigned")
    assert who(made.drafts) == [ADMIN, ADMIN2, TECH]  # not the client who did it, not a bystander
    assert all(d.email and d.type == "request.reopened" for d in made.drafts)
    assert made.drafts[0].title == "The client sent the work back"
    assert made.drafts[0].body.endswith("The mast photo is the wrong site")
    assert made.drafts[0].link == "/requests/r1"
    assert TECH2 not in who(made.drafts) and VIEWER not in who(made.drafts)


@pytest.mark.req("REQ-13")
def test_an_acceptance_tells_the_colleagues_the_team_and_the_admins_but_not_the_person_who_signed():
    made = run("request.closed", CLIENT, outcome="accepted", auto_closed=False, by_id=CLIENT,
               status="closed")
    assert who(made.drafts) == [ADMIN, ADMIN2, CLIENT2, TECH]
    assert made.drafts[0].title == "Work accepted" and not any(d.email for d in made.drafts)


@pytest.mark.req("REQ-14")
def test_an_automatic_close_tells_every_client_the_team_and_the_admins_in_the_app():
    made = run("request.closed", None, outcome="auto_closed", auto_closed=True, by_id=None,
               status="closed")
    assert who(made.drafts) == [ADMIN, ADMIN2, CLIENT, CLIENT2, TECH]
    assert made.drafts[0].title == "Closed automatically" and not any(d.email for d in made.drafts)


@pytest.mark.req("CRP-1")
def test_a_client_report_tells_the_team_and_the_admins_in_the_app_only():
    made = run("client_report.submitted", CLIENT, client_report_id="c1", kind="form",
               report_title="Gauge check", submitted_by_id=CLIENT, submitted_by_name="Una Client",
               attempt=1, status="in_progress")
    assert who(made.drafts) == [ADMIN, ADMIN2, TECH]
    assert made.drafts[0].title == "Client report added"
    assert made.drafts[0].body.endswith("Gauge check by Una Client")
    assert not any(d.email for d in made.drafts)


@pytest.mark.req("CRP-1")
def test_trying_again_to_draw_a_report_is_not_a_new_report():
    made = run("client_report.submitted", CLIENT, client_report_id="c1", kind="form",
               report_title="Gauge check", submitted_by_id=CLIENT, submitted_by_name="Una Client",
               attempt=2)
    assert made.drafts == []


CLOSEOUT = {
    "report_id": "c1", "number": "CO-2026-0042", "version": 1, "request_id": "r1",
    "request_ref": "MR-2026-0042", "org_id": "o1", "title": "Rain gauge not reporting",
    "corrected": False, "pdf_sha256": "a" * 64,
}


@pytest.mark.req("RPT-8")
def test_the_first_closeout_tells_the_clients_in_the_app_only():
    made = plan("report.closeout_generated", CLOSEOUT, None, None, AUDIENCE)
    assert who(made.drafts) == [CLIENT, CLIENT2] and not any(d.email for d in made.drafts)
    first = made.drafts[0]
    assert first.title == "Close-out report ready" and first.type == "report.closeout"
    assert first.body == "CO-2026-0042 · Rain gauge not reporting" and first.link == "/requests/r1"


@pytest.mark.req("RPT-6")
def test_a_corrected_closeout_is_also_emailed():
    made = plan("report.closeout_generated", {**CLOSEOUT, "version": 2, "corrected": True},
                None, None, AUDIENCE)
    assert who(made.drafts) == [CLIENT, CLIENT2] and all(d.email for d in made.drafts)
    assert made.drafts[0].title == "Corrected close-out report"
    assert made.drafts[0].body.endswith("version 2")


def test_no_staff_member_and_no_other_organization_is_told_of_a_closeout():
    made = plan("report.closeout_generated", CLOSEOUT, None, None, AUDIENCE)
    assert not {ADMIN, TECH, VIEWER} & set(who(made.drafts))
    elsewhere = plan("report.closeout_generated", CLOSEOUT, None, None, Audience(admins=[ADMIN]))
    assert elsewhere.drafts == []


def test_the_events_are_known_and_hold_no_report_text():
    assert {"request.client_review_started", "request.review_reminder", "request.reopened",
            "request.closed", "client_report.submitted", "report.closeout_generated"} \
        <= REVIEW_EVENTS
    assert not {"content", "narrative", "form", "summary", "observations"} & set(CLOSEOUT)


def test_the_notification_group_reads_the_report_services_topic():
    """`report.closeout_generated` (and the visit report events) are only heard if the group
    consumes the topic they are on."""
    assert "mms.report.events" in Settings().notification_topics
