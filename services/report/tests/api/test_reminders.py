"""Reminders that a visit report is not finalized (PRD RPT-7; W17-11): the hourly tick, the event it
adds and what keeps it from being sent twice."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from mms_common.testing.seed import SEED_USERS

from app.jobs import reminders as job
from app.jobs.finalize import finalize_report
from tests import visit_facts as vf
from tests.api.test_drafts import one
from tests.api.test_edit_sign import events, ready, sign
from tests.api.test_finalize import final, post, reopen

LEAD, HELPER = SEED_USERS["tech1"].id, SEED_USERS["tech2"].id
# The visit ended on Friday at 16:40 in Jamaica (UTC-5)
ENDED = datetime(2026, 10, 23, 21, 40, tzinfo=UTC)
TWO, FIVE = datetime(2026, 10, 27, 21, 40, tzinfo=UTC), datetime(2026, 10, 30, 21, 40, tzinfo=UTC)


async def friday_draft(report) -> dict:
    await ready(report)
    await report.db["reports"].update_one(
        {}, {"$set": {"ended_at": ENDED, "remind_from": ENDED}})
    return await one(report)


def at(report, moment: datetime) -> None:
    report.clock.set(moment)


@pytest.mark.req("RPT-7")
async def test_nothing_is_sent_before_the_second_working_day(report):
    await friday_draft(report)
    at(report, datetime(2026, 10, 27, 21, 39, tzinfo=UTC))
    assert await job.tick(report.svc) == {"checked": 1, "sent": 0}
    assert await events(report, "report.finalize_reminder") == []


@pytest.mark.req("RPT-7")
async def test_two_working_days_remind_the_people_who_have_not_signed_once(report):
    d = await friday_draft(report)
    await sign(report, d, "tech1")  # the lead signed; the other attending person did not
    at(report, TWO)
    assert await job.tick(report.svc) == {"checked": 1, "sent": 1}
    (event,) = await events(report, "report.finalize_reminder")
    assert event["data"]["working_days"] == 2 and event["data"]["staff_ids"] == [HELPER]
    assert event["data"]["lead_staff_id"] == LEAD and event["data"]["report_id"] == d["_id"]
    assert event["data"]["request_ref"] == "MR-2026-0042" and event["key"] == vf.REQUEST
    assert (await one(report))["reminders_sent"] == [2]
    # The same hour, an hour later: the same reminder is not sent again
    at(report, TWO.replace(hour=22))
    assert (await job.tick(report.svc))["sent"] == 0
    assert len(await events(report, "report.finalize_reminder")) == 1


@pytest.mark.req("RPT-7")
async def test_five_working_days_remind_again_and_the_lead_is_told_when_everyone_has_signed(report):
    d = await friday_draft(report)
    at(report, TWO)
    await job.tick(report.svc)
    await sign(report, d, "tech1")
    await sign(report, d, "tech2")
    at(report, FIVE)
    assert (await job.tick(report.svc))["sent"] == 1
    levels = sorted(e["data"]["working_days"] for e in await events(
        report, "report.finalize_reminder"))
    assert levels == [2, 5]
    last = next(e for e in await events(report, "report.finalize_reminder")
                if e["data"]["working_days"] == 5)
    assert last["data"]["staff_ids"] == [LEAD]  # everyone signed: the lead finalizes
    assert (await one(report))["reminders_sent"] == [2, 5]


async def test_a_draft_found_late_gets_one_reminder_not_two(report):
    await friday_draft(report)
    at(report, FIVE)
    assert (await job.tick(report.svc))["sent"] == 1
    (event,) = await events(report, "report.finalize_reminder")
    assert event["data"]["working_days"] == 5
    assert (await one(report))["reminders_sent"] == [2, 5]
    assert (await job.tick(report.svc))["sent"] == 0


@pytest.mark.req("RPT-7")
async def test_a_report_that_is_finalizing_or_final_is_not_reminded(report):
    d = await friday_draft(report)
    await sign(report, d, "tech1")
    await post(report, d, "finalize")  # finalizing
    at(report, FIVE)
    assert (await job.tick(report.svc)) == {"checked": 0, "sent": 0}
    await finalize_report(report.svc, d["_id"])
    assert (await job.tick(report.svc)) == {"checked": 0, "sent": 0}
    assert await events(report, "report.finalize_reminder") == []


@pytest.mark.req("RPT-6")
async def test_a_reopened_version_is_reminded_from_the_reopen(report):
    done = await final(report)
    at(report, datetime(2026, 11, 2, 15, 0, tzinfo=UTC))  # long after the visit
    await report.db["reports"].update_one({"_id": done["_id"]}, {"$set": {"ended_at": ENDED}})
    new = (await reopen(report, done)).json()
    assert (await job.tick(report.svc))["sent"] == 0  # not the visit's age: the reopen's
    at(report, datetime(2026, 11, 4, 15, 0, tzinfo=UTC))
    assert (await job.tick(report.svc))["sent"] == 1
    (event,) = await events(report, "report.finalize_reminder")
    assert event["data"]["report_id"] == new["id"] and event["data"]["version"] == 2
    assert event["data"]["working_days"] == 2


async def test_a_draft_without_its_facts_is_left_alone(report):
    d = await friday_draft(report)
    await report.db["reports"].update_one({"_id": d["_id"]}, {"$set": {"content.facts": None}})
    at(report, FIVE)
    assert await job.tick(report.svc) == {"checked": 0, "sent": 0}
