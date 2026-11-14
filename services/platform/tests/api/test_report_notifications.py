"""Visit report notifications on real MongoDB and Redis (PRD RPT-5 to RPT-7, NOT-1, NOT-4,
Appendix B; W17 slice 4): who is told, the email and the person's choice."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.testing.seed import ORG_A as ORG
from mms_common.testing.seed import SEED_USERS

from tests.api.notify_support import ALL, REQ, bearer, directory, event, listing
from tests.api.test_notification_emails import sender_for

TECH, TECH2, ADMIN, CLIENT = (
    SEED_USERS["tech1"].id, SEED_USERS["tech2"].id, SEED_USERS["admin"].id,
    SEED_USERS["client_a1"].id,
)
VISIT = "01900000-0000-7000-8000-0000000c0001"
REPORT = "01900000-0000-7000-8000-0000000d0001"


def about(**extra: Any) -> dict[str, Any]:
    return {
        "report_id": REPORT, "number": "VR-2026-0042-01", "version": 1, "visit_id": VISIT,
        "request_id": REQ, "org_id": ORG, **extra,
    }


def finalized(**extra: Any) -> dict[str, Any]:
    return about(
        subject_ref=f"visit:{VISIT}", request_ref="MR-2026-0042",
        title="Rain gauge reads zero",
        staff_ids=[TECH, TECH2], lead_staff_id=TECH,
        finalized_at=datetime(2026, 10, 22, 21, tzinfo=UTC), finalized_by=TECH,
        pdf_sha256="a" * 64, **extra)


def message(type_: str, data: dict[str, Any], actor: str | None = None) -> bytes:
    return event(type_, data, actor=actor, org=ORG, source="report")


@pytest.mark.req("RPT-5")
async def test_a_final_report_tells_the_client_and_the_team_and_emails_the_client(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    assert await proc.process(message("report.finalized", finalized(), "tech1")) is Outcome.APPLIED
    [mine] = (await listing(http, issuer, "client_a1"))["items"]
    assert mine["title"] == "Visit report finalized" and mine["link"] == f"/visits/{VISIT}"
    assert mine["body"] == "VR-2026-0042-01 · Rain gauge reads zero"
    assert mine["entity"] == {"type": "report", "id": REPORT}
    [colleague] = (await listing(http, issuer, "tech2"))["items"]
    assert colleague["link"] == f"/visit-reports/{REPORT}"
    assert (await listing(http, issuer, "tech1"))["items"] == []  # they finalized it
    assert (await listing(http, issuer, "admin"))["items"] == []  # an admin who was not there
    # Only the client (and a colleague of theirs in the same organization) is emailed
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 2
    mail = next(m for m in mailer.sent if "client.a1@example.org" in m["To"])
    assert mail["Subject"].startswith("Visit report finalized: VR-2026-0042-01")
    text = mail.get_body(("plain",)).get_content()
    assert f"Open the report: https://mms.example.org/visits/{VISIT}" in text
    assert "Rain gauge reads zero" in text


@pytest.mark.req("NOT-4")
async def test_a_client_can_turn_the_final_report_email_off_and_still_see_it_in_the_app(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    off = await http.put("/api/v1/notifications/preferences",
                         json={"email": {"report.finalized": False}},
                         headers=bearer(issuer, "client_a1"))
    assert off.status_code == 200
    await proc.process(message("report.finalized", finalized(), "tech1"))
    assert len((await listing(http, issuer, "client_a1"))["items"]) == 1
    sender, mailer = sender_for(app, clock)
    await sender.send_due()
    assert not any("client.a1@example.org" in m["To"] for m in mailer.sent)


@pytest.mark.req("RPT-5")
async def test_a_stopped_finalize_tells_the_lead_and_the_signers_in_the_app_only(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    await proc.process(message("report.finalize_failed", about(
        reason="facts_changed", attempts=1, request_ref="MR-2026-0042",
        title="Rain gauge reads zero", lead_staff_id=TECH, signer_ids=[TECH, TECH2])))
    for who in ("tech1", "tech2"):
        [item] = (await listing(http, issuer, who))["items"]
        assert item["title"] == "Finalizing stopped: the board changed"
        assert item["link"] == f"/visit-reports/{REPORT}"
    assert (await listing(http, issuer, "client_a1"))["items"] == []
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 0 and mailer.sent == []


@pytest.mark.req("RPT-6")
async def test_a_reopen_tells_the_client_only_once_they_were_asked_to_review(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    reopen = about(
        version=2, previous_version=1, reason="The priority was missing", reopened_by=ADMIN,
        request_ref="MR-2026-0042", title="Rain gauge reads zero", staff_ids=[TECH, TECH2],
        lead_staff_id=TECH)
    before = {**reopen, "request_status": "in_progress"}
    await proc.process(message("report.reopened", before, "admin"))
    assert (await listing(http, issuer, "client_a1"))["items"] == []
    assert len((await listing(http, issuer, "tech1"))["items"]) == 1
    review = {**reopen, "request_status": "client_review"}
    await proc.process(message("report.reopened", review, "admin"))
    [mine] = (await listing(http, issuer, "client_a1"))["items"]
    assert mine["title"] == "A corrected report is coming"
    sender, mailer = sender_for(app, clock)
    await sender.send_due()
    assert any("client.a1@example.org" in m["To"] for m in mailer.sent)


@pytest.mark.req("RPT-7")
async def test_a_reminder_emails_who_has_not_signed_and_tells_the_admins_at_five_days(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    reminder = about(request_ref="MR-2026-0042", title="Rain gauge reads zero",
                     staff_ids=[TECH2], lead_staff_id=TECH)
    await proc.process(message("report.finalize_reminder", {**reminder, "working_days": 2}))
    [item] = (await listing(http, issuer, "tech2"))["items"]
    assert item["title"] == "Report not finalized yet" and "2 working days ago" in item["body"]
    assert (await listing(http, issuer, "admin"))["items"] == []
    await proc.process(message("report.finalize_reminder", {**reminder, "working_days": 5}))
    [admin_item] = (await listing(http, issuer, "admin"))["items"]
    assert "5 working days ago" in admin_item["body"]
    sender, mailer = sender_for(app, clock)
    await sender.send_due()
    # Two emails to the one person who has not signed; none to the admin (in-app only)
    assert sum("tech2@example.org" in m["To"] for m in mailer.sent) == 2
    assert not any("admin@example.org" in m["To"] for m in mailer.sent)
