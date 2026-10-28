"""When a draft is reminded and who is told (PRD RPT-7; W17-11). Pure rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain import drafts, reminders
from tests import visit_facts as vf

JAMAICA = ZoneInfo("America/Jamaica")  # UTC-5, no daylight saving
FRIDAY_END = datetime(2026, 10, 23, 21, 40, tzinfo=UTC)  # Friday 16:40 in Jamaica


def draft(ended_at: datetime = FRIDAY_END, **over):
    doc = drafts.new_draft(
        report_id="r1", number="VR-2026-0042-02", subject_ref="visit:v", visit_id=vf.VISIT,
        request_id=vf.REQUEST, org_id=vf.ORG, staff_ids=[vf.LEAD, vf.OTHER],
        lead_staff_id=vf.LEAD, ended_at=ended_at, now=ended_at)
    doc["content"] = {"facts": vf.facts(), "narrative": {}, "media_selection": []}
    doc.update(over)
    return doc


@pytest.mark.parametrize(("start", "days", "expected"), [
    # Friday 16:40 + 2 working days: Monday is the first, Tuesday the second, same time of day
    (FRIDAY_END, 2, datetime(2026, 10, 27, 21, 40, tzinfo=UTC)),
    (FRIDAY_END, 5, datetime(2026, 10, 30, 21, 40, tzinfo=UTC)),
    # Monday morning + 2 working days: Wednesday
    (datetime(2026, 10, 19, 9, 0, tzinfo=UTC), 2, datetime(2026, 10, 21, 9, 0, tzinfo=UTC)),
    # Saturday counts nothing: Monday is the first working day, Tuesday the second
    (datetime(2026, 10, 24, 15, 0, tzinfo=UTC), 2, datetime(2026, 10, 27, 15, 0, tzinfo=UTC)),
    (datetime(2026, 10, 19, 9, 0, tzinfo=UTC), 5, datetime(2026, 10, 26, 9, 0, tzinfo=UTC)),
])
def test_working_days_skip_the_weekend_and_keep_the_time_of_day(start, days, expected):
    assert reminders.add_working_days(start, days, JAMAICA) == expected


def test_the_zone_decides_which_day_it_is():
    # Friday 23:30 in Jamaica is already Saturday in UTC: counted from the station's Friday, the
    # first working day is Monday 23:30 there (Tuesday 04:30 UTC); counted in UTC it is Monday 04:30
    late = datetime(2026, 10, 24, 4, 30, tzinfo=UTC)
    assert reminders.add_working_days(late, 1, JAMAICA) == datetime(2026, 10, 27, 4, 30, tzinfo=UTC)
    assert reminders.add_working_days(late, 1, ZoneInfo("UTC")) == datetime(
        2026, 10, 26, 4, 30, tzinfo=UTC)
    # A zone with daylight saving keeps the wall-clock time across the change (Sun 1 Nov 2026)
    ny = ZoneInfo("America/New_York")
    start = datetime(2026, 10, 30, 21, 0, tzinfo=UTC)  # Friday 17:00 EDT
    assert reminders.add_working_days(start, 1, ny) == datetime(2026, 11, 2, 22, 0, tzinfo=UTC)


def test_the_stations_zone_is_the_first_one_with_a_zone_else_utc():
    assert reminders.zone_of(draft()) == JAMAICA
    nothing = draft()
    nothing["content"]["facts"]["stations"] = [{"station_id": "s", "time_zone": None}]
    assert reminders.zone_of(nothing) == ZoneInfo("UTC")
    odd = draft()
    odd["content"]["facts"]["stations"][0]["time_zone"] = "Not/A_Zone"
    assert reminders.zone_of(odd) == ZoneInfo("UTC")
    assert reminders.zone_of(draft(content={"facts": None})) == ZoneInfo("UTC")


@pytest.mark.req("RPT-7")
def test_each_level_is_due_once_its_working_day_has_come_and_only_if_not_sent():
    doc = draft()
    two, five = datetime(2026, 10, 27, 21, 40, tzinfo=UTC), datetime(2026, 10, 30, 21, 40, tzinfo=UTC)
    assert reminders.due_levels(doc, two - timedelta(minutes=1)) == []
    assert reminders.due_levels(doc, two) == [2]
    assert reminders.due_levels(doc, five - timedelta(minutes=1)) == [2]
    assert reminders.due_levels(doc, five) == [2, 5]
    assert reminders.due_levels({**doc, "reminders_sent": [2]}, five) == [5]
    assert reminders.due_levels({**doc, "reminders_sent": [2, 5]}, five + timedelta(days=30)) == []


def test_a_corrected_version_counts_from_the_reopen_not_from_the_visit():
    reopened = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
    doc = draft(remind_from=reopened)
    assert reminders.anchor(doc) == reopened
    assert reminders.due_levels(doc, reopened + timedelta(days=1)) == []
    assert reminders.due_levels(doc, datetime(2026, 11, 4, 15, 0, tzinfo=UTC)) == [2]
    # A draft made before this existed has no `remind_from`: the visit's end counts
    old = draft()
    del old["remind_from"]
    assert reminders.anchor(old) == FRIDAY_END


def test_the_people_who_have_not_signed_are_told_and_the_lead_when_everyone_has():
    doc = draft()
    assert reminders.recipients(doc, set()) == [vf.LEAD, vf.OTHER]
    assert reminders.recipients(doc, {vf.LEAD}) == [vf.OTHER]
    assert reminders.recipients(doc, {vf.LEAD, vf.OTHER}) == [vf.LEAD]


def test_a_draft_found_after_a_long_gap_gets_the_latest_reminder_once():
    assert reminders.reminder_levels([2]) == (2, [2])
    assert reminders.reminder_levels([2, 5]) == (5, [2, 5])
