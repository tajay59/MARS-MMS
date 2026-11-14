"""Who is told about a visit report (PRD RPT-1, RPT-5 to RPT-7, Appendix B; W16-11, W17). No I/O."""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.notifications import NOTIFY_EVENTS, Audience, plan

ADMIN, TECH, TECH2, CLIENT, CLIENT2 = "admin-1", "tech-1", "tech-2", "client-1", "client-2"
AUDIENCE = Audience(admins=[ADMIN], staff=[ADMIN, TECH, TECH2], org_clients=[CLIENT, CLIENT2])
BASE = {
    "report_id": "r1", "number": "VR-2026-0042-02", "version": 1, "visit_id": "v1",
    "request_id": "q1", "request_ref": "MR-2026-0042", "org_id": "o1",
    "title": "Rain gauge not reporting", "staff_ids": [TECH, TECH2], "lead_staff_id": TECH,
}
LINE = "VR-2026-0042-02 · Rain gauge not reporting"


def data(**extra: Any) -> dict[str, Any]:
    return {**BASE, **extra}


def told(made, user: str):
    return [d for d in made.drafts if d.user_id == user]


# --- the draft (W16) ----------------------------------------


@pytest.mark.req("RPT-1")
def test_the_people_who_attended_hear_that_the_draft_is_ready_in_the_app_only():
    made = plan("report.drafted", data(), None, None, AUDIENCE)
    assert sorted(d.user_id for d in made.drafts) == [TECH, TECH2]
    first = made.drafts[0]
    assert first.title == "Draft report ready" and first.body == LINE
    assert first.link == "/visit-reports/r1"
    assert (first.entity_type, first.entity_id) == ("report", "r1")
    assert first.type == "report.drafted" and not any(d.email for d in made.drafts)


@pytest.mark.req("RPT-1")
def test_no_client_and_no_admin_who_was_not_there_is_told_of_a_draft():
    made = plan("report.drafted", data(), None, None, AUDIENCE)
    assert not {CLIENT, CLIENT2, ADMIN} & {d.user_id for d in made.drafts}


# --- final (W17) ----------------------------------------


@pytest.mark.req("RPT-5")
def test_a_final_report_tells_the_team_in_the_app_and_the_client_in_the_app_and_by_email():
    made = plan("report.finalized", data(), TECH, "Test Lead", AUDIENCE)
    # The person who finalized is not told
    assert sorted(d.user_id for d in made.drafts) == [CLIENT, CLIENT2, TECH2]
    [colleague] = told(made, TECH2)
    assert colleague.title == "Visit report finalized" and colleague.body == LINE
    assert colleague.link == "/visit-reports/r1" and colleague.email is False
    for client in (CLIENT, CLIENT2):
        [mine] = told(made, client)
        assert mine.title == "Visit report finalized" and mine.email is True
        assert mine.link == "/visits/v1"  # a client has no report page
        assert mine.type == "report.finalized"
    assert ADMIN not in {d.user_id for d in made.drafts}  # an admin who did not attend


@pytest.mark.req("RPT-6")
def test_a_corrected_report_says_so():
    made = plan("report.finalized", data(version=2), TECH, "Test Lead", AUDIENCE)
    assert {d.title for d in made.drafts} == {"Corrected report final"}


# --- stopped (W17) ----------------------------------------


@pytest.mark.req("RPT-5")
@pytest.mark.parametrize(("reason", "title"), [
    ("facts_changed", "Finalizing stopped: the board changed"),
    ("lock_failed", "Finalizing stopped: the visit could not be locked"),
    ("render_failed", "Finalizing stopped: the PDF could not be made"),
])
def test_a_stopped_finalize_tells_the_lead_and_the_signers_with_the_reason(reason, title):
    made = plan("report.finalize_failed", data(reason=reason, attempts=3, signer_ids=[TECH, TECH2]),
                None, None, AUDIENCE)
    assert sorted(d.user_id for d in made.drafts) == [TECH, TECH2]  # each once
    assert {d.title for d in made.drafts} == {title}
    assert all(d.body.startswith(LINE) and d.link == "/visit-reports/r1" for d in made.drafts)
    assert not any(d.email for d in made.drafts) and not told(made, CLIENT)


def test_an_unknown_reason_still_tells_the_lead():
    made = plan("report.finalize_failed", data(reason="new_reason", signer_ids=[]), None, None,
                AUDIENCE)
    assert [d.user_id for d in made.drafts] == [TECH]


# --- reopened (W17) ----------------------------------------


@pytest.mark.req("RPT-6")
@pytest.mark.parametrize("status", ["client_review", "closed"])
def test_a_reopen_after_the_client_was_asked_to_review_tells_the_client_too(status):
    made = plan("report.reopened", data(version=2, previous_version=1, reason="Priority missing",
                                         reopened_by=ADMIN, request_status=status),
                ADMIN, "Test Admin", AUDIENCE)
    assert sorted(d.user_id for d in made.drafts) == [CLIENT, CLIENT2, TECH, TECH2]
    [team] = told(made, TECH)
    assert team.title == "Report reopened for correction" and team.email is False
    assert team.body == f"{LINE} · Priority missing"
    [client] = told(made, CLIENT)
    assert client.title == "A corrected report is coming" and client.email is True
    assert client.link == "/visits/v1"


@pytest.mark.req("RPT-6")
@pytest.mark.parametrize("status", ["in_progress", "assigned", None])
def test_a_reopen_before_the_client_was_asked_tells_only_the_team(status):
    made = plan("report.reopened", data(version=2, previous_version=1, reason="Priority missing",
                                         reopened_by=ADMIN, request_status=status),
                ADMIN, "Test Admin", AUDIENCE)
    assert sorted(d.user_id for d in made.drafts) == [TECH, TECH2]


# --- reminders (W17) ----------------------------------------


@pytest.mark.req("RPT-7")
def test_after_two_working_days_who_has_not_signed_hears_in_the_app_and_by_email():
    made = plan("report.finalize_reminder", data(working_days=2, staff_ids=[TECH2]), None, None,
                AUDIENCE)
    [only] = made.drafts
    assert only.user_id == TECH2 and only.email is True and only.link == "/visit-reports/r1"
    assert only.title == "Report not finalized yet"
    assert "2 working days ago" in only.body


@pytest.mark.req("RPT-7")
def test_after_five_working_days_the_admins_hear_too_in_the_app_only():
    made = plan("report.finalize_reminder", data(working_days=5, staff_ids=[TECH]), None, None,
                AUDIENCE)
    assert sorted(d.user_id for d in made.drafts) == [ADMIN, TECH]
    assert told(made, TECH)[0].email is True and told(made, ADMIN)[0].email is False
    assert "5 working days ago" in told(made, ADMIN)[0].body
    assert not told(made, CLIENT)


def test_the_events_are_handled_and_carry_no_report_text():
    assert {"report.drafted", "report.finalized", "report.finalize_failed", "report.reopened",
            "report.finalize_reminder"} <= NOTIFY_EVENTS
    assert not {"content", "narrative", "facts", "stations", "image"} & set(BASE)
