"""Email choices and the emails that follow notifications (PRD NOT-3, NOT-4, CAL-5). No I/O."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from mms_common.errors import ValidationFailed

from app.domain import notification_emails as copy
from app.domain import preferences
from app.jobs.calibration_digest import digest_items, week_due

ADMIN, TECH, CLIENT, VIEWER = (
    frozenset({"admin"}), frozenset({"technician"}), frozenset({"client"}), frozenset({"viewer"}),
)


# --- Choices -----------------------------------------------------------------------------------


@pytest.mark.req("NOT-4")
def test_each_person_can_choose_only_what_they_can_be_emailed_about():
    keys = lambda roles: {t.key for t in preferences.types_for(roles)}  # noqa: E731
    visits = {"visit.scheduled", "visit.cancelled"}
    assert keys(ADMIN) == {"request.submitted", "request.assigned", "request.cancelled",
                           "calibration.digest"} | visits
    assert keys(TECH) == {"request.assigned", "request.cancelled"} | visits
    assert keys(CLIENT) == {"request.decided", "request.cancelled"} | visits
    assert keys(VIEWER) == set()
    assert keys(ADMIN | TECH) == keys(ADMIN)


@pytest.mark.req("NOT-4")
def test_the_defaults_follow_appendix_b_and_the_choice_wins():
    on = preferences.is_on
    assert on({}, "request.submitted", ADMIN) is True
    assert on({}, "request.assigned", TECH) is True
    assert on({}, "request.decided", CLIENT) is True
    assert on({}, "calibration.digest", ADMIN) is True
    # A cancellation is emailed to the client, and offered to staff but starts off
    assert on({}, "request.cancelled", CLIENT) is True
    assert on({}, "request.cancelled", TECH) is False
    assert on({"request.cancelled": True}, "request.cancelled", TECH) is True
    assert on({"request.assigned": False}, "request.assigned", TECH) is False
    # A visit that is planned or cancelled is emailed to everyone it concerns, until they say no
    for roles in (ADMIN, TECH, CLIENT):
        assert on({}, "visit.scheduled", roles) is True
        assert on({}, "visit.cancelled", roles) is True
    assert on({"visit.scheduled": False}, "visit.scheduled", CLIENT) is False
    # Ended and owner changes are in-app only: not something to choose
    assert on({}, "visit.ended", TECH) is False
    assert on({}, "visit.owner_changed", TECH) is False


@pytest.mark.req("NOT-4")
def test_nothing_is_emailed_that_the_person_cannot_receive():
    assert preferences.is_on({"calibration.digest": True}, "calibration.digest", TECH) is False
    assert preferences.is_on({"request.submitted": True}, "request.submitted", CLIENT) is False
    assert preferences.is_on({}, "comment.added", ADMIN) is False  # in-app only (Appendix B)
    assert preferences.is_on({}, "account.registered", ADMIN) is False
    assert preferences.is_on({}, "no.such.type", ADMIN) is False


@pytest.mark.req("NOT-4")
def test_a_choice_for_something_else_is_refused():
    ok = preferences.check_choices({"request.assigned": False}, TECH)
    assert ok == {"request.assigned": False}
    with pytest.raises(ValidationFailed) as caught:
        preferences.check_choices({"calibration.digest": False}, TECH)
    assert caught.value.extra["code"] == "unknown_type"
    with pytest.raises(ValidationFailed):
        preferences.check_choices({"request.assigned": False}, VIEWER)


# --- The emails --------------------------------------------------------------------------------


def test_a_notification_email_says_what_happened_and_links_to_it():
    mail = copy.render_notification(
        title="Assigned to you", body="MR-2026-0034 · Logger not reporting",
        name="Devon Brown", url="https://mms.example.org/requests/r1",
    )
    assert mail.subject == "Assigned to you: MR-2026-0034 · Logger not reporting"
    assert "Hello Devon," in mail.text and "https://mms.example.org/requests/r1" in mail.text
    assert "Email preferences" in mail.text
    assert 'href="https://mms.example.org/requests/r1"' in mail.html


def test_nothing_from_an_event_gets_into_the_html_unescaped():
    mail = copy.render_notification(
        title="<script>alert(1)</script>", body='"><img src=x onerror=y>', name="<b>Eve</b>",
        url='https://x.example/"><script>',
    )
    assert "<script>" not in mail.html and "<img" not in mail.html and "<b>" not in mail.html
    assert "&lt;script&gt;" in mail.html


def test_a_long_subject_is_cut():
    mail = copy.render_notification(title="T", body="x" * 300, name="A", url="https://x")
    assert len(mail.subject) <= 120 and mail.subject.endswith("...")


def items(n_overdue: int, n_soon: int) -> list[dict]:
    rows = []
    for i in range(n_overdue):
        rows.append({"serial": f"O{i}", "model": "Vaisala HMP155", "station_code": f"JM-{i % 2}",
                     "due_state": "overdue", "due_label": "12 Oct"})
    for i in range(n_soon):
        rows.append({"serial": f"S{i}", "model": "Gill WindSonic", "station_code": f"TT-{i}",
                     "due_state": "due_soon", "due_label": "2 Nov"})
    return rows


@pytest.mark.req("CAL-5")
def test_the_digest_counts_overdue_and_soon_and_the_stations():
    counts = copy.digest_counts(items(3, 9))
    assert (counts.overdue, counts.soon, counts.stations) == (3, 9, 11)
    assert copy.digest_title(counts) == "12 sensors need calibration"
    assert copy.digest_body(counts, 30) == "3 overdue, 9 due in the next 30 days"
    one = copy.digest_counts(items(0, 1))
    assert copy.digest_title(one) == "1 sensor needs calibration"
    assert copy.digest_body(one, 30) == "1 due in the next 30 days"


@pytest.mark.req("CAL-5")
def test_the_digest_email_has_both_tables_and_stops_at_a_screenful():
    mail = copy.render_digest(name="Andrea Ortiz", items=items(3, 20), within_days=30,
                              url="https://mms.example.org/calibration", when="26 Oct")
    assert mail.subject == "23 sensors need calibration · weekly digest"
    assert "Overdue (3)" in mail.html and "Due in the next 30 days (20)" in mail.html
    assert "and 5 more" in mail.html and "and 5 more" in mail.text  # 15 rows, 5 left
    assert "S0" in mail.html and "S19" not in mail.html
    assert "https://mms.example.org/calibration" in mail.text
    assert "Hello Andrea," in mail.text


def test_a_digest_with_only_overdue_sensors_has_one_table():
    mail = copy.render_digest(name="A", items=items(2, 0), within_days=30, url="https://x",
                              when="26 Oct")
    assert "Overdue (2)" in mail.html and "Due in the next" not in mail.html


# --- When the digest is due --------------------------------------------------------------------


@pytest.mark.req("CAL-5")
def test_the_digest_is_due_from_monday_7_in_the_chosen_zone():
    zone = "America/Jamaica"  # UTC-5 all year
    before = datetime(2026, 10, 26, 11, 59, tzinfo=UTC)  # Monday 06:59 there
    at = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # Monday 07:00
    assert week_due(before, zone, 7) is None
    assert week_due(at, zone, 7) == "2026-W44"
    assert week_due(datetime(2026, 10, 28, 3, 0, tzinfo=UTC), zone, 7) == "2026-W44"  # Wednesday
    # Sunday night there is still the old week, whose Monday has long passed
    assert week_due(datetime(2026, 11, 2, 4, 59, tzinfo=UTC), zone, 7) == "2026-W44"
    assert week_due(datetime(2026, 11, 2, 12, 0, tzinfo=UTC), zone, 7) == "2026-W45"


def test_the_items_keep_what_the_email_needs_in_the_chosen_zone():
    made = digest_items([{
        "unit_id": "u1", "serial": "S1", "due_state": "overdue",
        "calibration_due_at": "2026-10-12T02:00:00Z",
        "station": {"code": "KGN-009"}, "model": {"manufacturer": "Gill", "model": "WindSonic"},
    }, {
        "unit_id": "u2", "serial": "S2", "due_state": "due_soon",
        "calibration_due_at": "2026-11-02T12:00:00Z", "station": None, "model": None,
    }], "America/Jamaica")
    assert made[0]["due_label"] == "11 Oct"  # 02:00 UTC is still the 11th in Jamaica
    assert (made[0]["model"], made[0]["station_code"]) == ("Gill WindSonic", "KGN-009")
    assert (made[1]["model"], made[1]["station_code"], made[1]["due_label"]) == (
        "Sensor", None, "2 Nov")
