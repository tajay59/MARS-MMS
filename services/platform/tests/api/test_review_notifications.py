"""Notifications of Client Review, the client's answer, client reports and the close-out on real
MongoDB and Redis (PRD REQ-12 to REQ-14, CRP-1, RPT-8, NOT-1, NOT-4; W18 slice 4): who is told, the
email and its button, and the person's choice."""

from __future__ import annotations

from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.testing.seed import ORG_A as ORG
from mms_common.testing.seed import SEED_USERS

from app.repo import emails
from tests.api.notify_support import ALL, REQ, bearer, directory, event, listing, request_data
from tests.api.test_notification_emails import sender_for

TECH, ADMIN = SEED_USERS["tech1"].id, SEED_USERS["admin"].id


def data(**extra: Any) -> dict[str, Any]:
    return request_data(**{"assigned_staff_ids": [TECH], "status": "client_review", **extra})


def operations(type_: str, actor: str | None = None, **extra: Any) -> bytes:
    return event(type_, data(**extra), actor=actor, org=ORG)


async def titles(http, issuer, who: str) -> list[str]:
    return [i["title"] for i in (await listing(http, issuer, who))["items"]]


@pytest.mark.req("REQ-12")
async def test_review_started_tells_every_client_and_the_email_has_its_own_button(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    assert await proc.process(operations("request.client_review_started")) is Outcome.APPLIED
    for who in ("client_a1", "client_a2"):
        [item] = (await listing(http, issuer, who))["items"]
        assert item["type"] == "request.client_review" and item["link"] == f"/requests/{REQ}/review"
    for who in ("admin", "tech1", "tech2", "viewer"):
        assert (await listing(http, issuer, who))["items"] == [], who

    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 2
    assert {m["To"].split("<")[-1].rstrip(">") for m in mailer.sent} == {
        "client.a1@example.org", "client.a2@example.org"}
    mail = mailer.sent[0]
    assert mail["Subject"].startswith("Work ready for your review")
    plain = mail.get_body(("plain",)).get_content()
    assert f"Review the work: https://mms.example.org/requests/{REQ}/review" in plain
    assert "Review the work" in mail.get_body(("html",)).get_content()


@pytest.mark.req("REQ-14")
async def test_a_reminder_is_emailed_unless_the_client_turned_review_emails_off(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, "admin", "tech1", "client_a1", "client_a2")
    await proc.process(operations("request.review_reminder", day=7.0, auto_close_day=30.0))
    off = await http.put("/api/v1/notifications/preferences",
                         json={"email": {"request.client_review": False}},
                         headers=bearer(issuer, "client_a2"))
    assert off.status_code == 200, off.text
    sender, mailer = sender_for(app, clock)
    await sender.send_due()
    assert [m["To"].split("<")[-1].rstrip(">") for m in mailer.sent] == ["client.a1@example.org"]
    assert await emails.counts(app.state.db) == {"sent": 1, "skipped": 1}
    # Still in the app for both (in-app is always on)
    for who in ("client_a1", "client_a2"):
        assert await titles(http, issuer, who) == ["Still waiting for your review"]


@pytest.mark.req("REQ-13")
async def test_a_rejection_reaches_the_team_and_the_admins_with_the_reason(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    raw = operations("request.reopened", "client_a1", comment="The photos show the wrong mast",
                     by_id=SEED_USERS["client_a1"].id)
    assert await proc.process(raw) is Outcome.APPLIED
    for who in ("tech1", "admin"):
        [item] = (await listing(http, issuer, who))["items"]
        assert item["title"] == "The client sent the work back"
        assert item["body"].endswith("The photos show the wrong mast")
    for who in ("tech2", "viewer", "client_a1", "client_a2"):
        assert (await listing(http, issuer, who))["items"] == [], who
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 2


@pytest.mark.req("REQ-13")
async def test_an_acceptance_is_in_the_app_only_and_not_for_the_person_who_signed(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    raw = operations("request.closed", "client_a1", outcome="accepted", auto_closed=False,
                     by_id=SEED_USERS["client_a1"].id, status="closed")
    await proc.process(raw)
    for who in ("client_a2", "tech1", "admin"):
        assert await titles(http, issuer, who) == ["Work accepted"], who
    assert (await listing(http, issuer, "client_a1"))["items"] == []
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 0 and mailer.sent == []


@pytest.mark.req("REQ-14")
async def test_an_automatic_close_tells_everyone_including_both_clients(env):
    _, http, proc, _, issuer, *_ = env
    await directory(proc, *ALL)
    await proc.process(operations("request.closed", None, outcome="auto_closed",
                                  auto_closed=True, by_id=None, status="closed"))
    for who in ("client_a1", "client_a2", "tech1", "admin"):
        assert await titles(http, issuer, who) == ["Closed automatically"], who
    assert await titles(http, issuer, "client_b1") == []


@pytest.mark.req("CRP-1")
async def test_a_client_report_tells_the_team_once_even_if_drawn_again(env):
    _, http, proc, _, issuer, *_ = env
    await directory(proc, *ALL)

    def submitted(attempt: int) -> bytes:
        return operations("client_report.submitted", "client_a1", client_report_id="c1",
                          kind="form", report_title="Gauge check",
                          submitted_by_id=SEED_USERS["client_a1"].id,
                          submitted_by_name="Una Client", attempt=attempt, status="in_progress")

    await proc.process(submitted(1))
    await proc.process(submitted(2))
    for who in ("tech1", "admin"):
        assert await titles(http, issuer, who) == ["Client report added"], who
    assert (await listing(http, issuer, "client_a2"))["items"] == []


def closeout(corrected: bool = False) -> bytes:
    return event("report.closeout_generated", {
        "report_id": "c1", "number": "CO-2026-0042", "version": 2 if corrected else 1,
        "request_id": REQ, "request_ref": "MR-2026-0034", "org_id": ORG,
        "title": "Logger not reporting", "corrected": corrected, "pdf_sha256": "a" * 64,
    }, org=ORG, source="report")


@pytest.mark.req("RPT-8")
async def test_the_first_closeout_is_in_the_app_and_a_corrected_one_is_emailed_too(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    assert await proc.process(closeout()) is Outcome.APPLIED
    for who in ("client_a1", "client_a2"):
        assert await titles(http, issuer, who) == ["Close-out report ready"], who
    assert (await listing(http, issuer, "tech1"))["items"] == []  # staff are not told
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 0

    await proc.process(closeout(corrected=True))
    assert await sender.send_due() == 2
    mail = mailer.sent[0]
    assert mail["Subject"].startswith("Corrected close-out report")
    assert f"Read the report: https://mms.example.org/requests/{REQ}" in \
        mail.get_body(("plain",)).get_content()


@pytest.mark.req("NOT-1")
async def test_a_redelivered_event_makes_one_notification(env):
    _, http, proc, _, issuer, *_ = env
    await directory(proc, *ALL)
    raw = closeout()
    await proc.process(raw)
    await proc.process(raw)
    assert len((await listing(http, issuer, "client_a1"))["items"]) == 1
