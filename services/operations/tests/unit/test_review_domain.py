"""The client's answer and the review clock as pure rules (PRD REQ-13, REQ-14; W18-2, W18-6,
W18-7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mms_common.errors import Conflict

from app.config import Settings
from app.domain.requests import review

START = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
REMIND = (7.0, 21.0, 28.0)


def at(days: float) -> datetime:
    return START + timedelta(days=days)


def due(days: float, sent: tuple[float, ...] = (), close: float = 30.0) -> review.Due:
    return review.due(at(days), START, sent, REMIND, close)


# --- Which review the client answered -----------------------------------------------------------


def test_the_time_the_page_read_matches_what_mongo_keeps():
    stored = START.replace(microsecond=123_456)  # the clock has microseconds, Mongo keeps millis
    kept = START.replace(microsecond=123_000)
    assert review.same_review(stored, kept)
    naive = kept.astimezone(UTC).replace(tzinfo=None)  # a naive time is read as UTC
    assert review.same_review(kept, naive)
    assert not review.same_review(kept, kept + timedelta(milliseconds=1))
    assert not review.same_review(None, kept)


def test_an_answer_for_an_older_review_is_refused():
    review.check_reviewing(START, START)
    with pytest.raises(Conflict) as refused:
        review.check_reviewing(at(3), START)
    assert refused.value.extra["code"] == "review_changed"


def test_a_repeat_is_the_same_person_the_same_answer_and_the_same_review():
    current = {"client_verification": review.decision(
        "accepted", user_id="u1", name="Una", at=at(2), reviewing=START, reports=[])}
    assert review.is_repeat(current, "u1", "accepted", START)
    assert not review.is_repeat(current, "u2", "accepted", START)  # someone else at the client
    assert not review.is_repeat(current, "u1", "rejected", START)  # the other answer
    assert not review.is_repeat(current, "u1", "accepted", at(1))  # an older review
    assert not review.is_repeat({}, "u1", "accepted", START)
    assert not review.is_repeat({"client_verification": None}, "u1", "accepted", START)


# --- The clock ----------------------------------------------------------------------------------


@pytest.mark.parametrize("days", [0, 3, 6.99])
def test_nothing_happens_before_the_first_reminder(days):
    assert due(days).action is None


def test_a_reminder_is_due_on_each_configured_day():
    assert due(7) == review.Due("remind", 7.0, (7.0,))
    assert due(20.9) == review.Due("remind", 7.0, (7.0,))  # not yet sent: still owed
    assert due(21, sent=(7.0,)) == review.Due("remind", 21.0, (21.0,))
    assert due(28.5, sent=(7.0, 21.0)) == review.Due("remind", 28.0, (28.0,))


def test_a_reminder_already_sent_is_not_sent_again():
    assert due(10, sent=(7.0,)).action is None
    assert due(29.9, sent=(7.0, 21.0, 28.0)).action is None


def test_after_an_outage_only_the_latest_reminder_goes_and_all_are_marked():
    step = due(22)  # the job did not run on day 7 or day 21
    assert step.action == "remind" and step.day == 21.0
    assert step.mark == (7.0, 21.0)


def test_the_request_closes_when_the_last_day_passes():
    assert due(29.99, sent=REMIND).action is None
    assert due(30) == review.Due("close")
    assert due(45, sent=(7.0,)) == review.Due("close")  # closing wins over a reminder owed


def test_the_periods_follow_the_settings_and_may_be_fractions():
    started = START
    soon = review.due(started + timedelta(minutes=6), started, (), (0.002, 0.004), 0.01)
    assert soon.action == "remind" and soon.day == 0.004
    late = review.due(started + timedelta(minutes=15), started, (), (0.002,), 0.01)
    assert late.action == "close"


def test_the_auto_close_time_is_the_start_plus_the_period():
    assert review.auto_close_at(START, 30) == at(30)


def test_the_reports_in_force_are_the_final_ones():
    visits = [
        {"_id": "v1", "ref": "VR-1-01", "report_status": "final", "report_id": "r1",
         "report_version": 2},
        {"_id": "v2", "ref": "VR-1-02", "report_status": "draft", "report_id": "r2",
         "report_version": 1},
        {"_id": "v3", "ref": "VR-1-03", "report_status": "none"},
    ]
    assert review.final_reports(visits) == [
        {"visit_id": "v1", "ref": "VR-1-01", "report_id": "r1", "report_version": 2}]


# --- Settings -----------------------------------------------------------------------------------


def settings(**over) -> Settings:
    return Settings(**over)


def test_reminder_days_are_read_sorted_and_without_repeats():
    assert settings(review_reminder_days="28, 7,21,7").reminder_days == (7.0, 21.0, 28.0)
    assert settings(review_reminder_days="").reminder_days == ()


@pytest.mark.parametrize("over", [
    {"auto_close_days": 0},
    {"review_reminder_days": "0,7"},
    {"review_reminder_days": "7,31"},  # after the auto-close day
    {"review_reminder_days": "7,30"},  # on it
    {"environment": "production", "auto_close_days": 0.01, "review_reminder_days": "0.002"},
    {"environment": "production", "review_reminder_days": "0.5"},
])
def test_unusable_review_periods_are_refused(over):
    with pytest.raises(ValueError):
        settings(**over)


def test_staging_may_use_minutes_and_production_a_day_or_more():
    ok = settings(environment="staging", auto_close_days=0.01, review_reminder_days="0.004")
    assert ok.reminder_days == (0.004,)
    assert settings(environment="production", auto_close_days=1, review_reminder_days="") \
        .auto_close_days == 1
