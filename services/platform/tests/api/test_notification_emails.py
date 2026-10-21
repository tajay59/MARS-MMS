"""The emails that follow notifications, the choices that govern them and the weekly digest, on
real MongoDB and Redis (PRD NOT-3, NOT-4, CAL-5, Appendix B; TRD §3.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.testing.seed import SEED_USERS

from app.jobs import calibration_digest
from app.jobs.account_emails import Link, Sender
from app.repo import emails
from tests.api.notify_support import (
    REQ,
    bearer,
    directory,
    event,
    listing,
    person,
    request_data,
)

TECH, TECH2, ADMIN, CLIENT = (
    SEED_USERS["tech1"].id, SEED_USERS["tech2"].id, SEED_USERS["admin"].id,
    SEED_USERS["client_a1"].id,
)


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class NoLinks:
    async def mint(self, kind: str, link_id: str) -> Link:  # pragma: no cover
        raise AssertionError("a notification email never mints a link")


def sender_for(app, clock) -> tuple[Sender, FakeMailer]:
    mailer = FakeMailer()
    return Sender(db=app.state.db, mailer=mailer, links=NoLinks(), clock=clock,
                  mail_from="MARS-MMS <no-reply@mms.example.org>",
                  app_url="https://mms.example.org"), mailer


def assigned(staff: list[str], *, claimed: bool = False, actor: str = "admin") -> bytes:
    return event("request.assigned", {
        **request_data(assigned_staff_ids=staff, status="assigned"),
        "staff_ids": staff, "staff_names": ["T"], "claimed": claimed,
        "by_id": SEED_USERS[actor].id,
    }, actor=actor, org=request_data()["org_id"])


# --- The email follows the notification --------------------------------------------------------


@pytest.mark.req("NOT-1")
async def test_an_assignment_is_emailed_with_a_link_to_the_request(env):
    app, _, proc, _, _, clock, _ = env
    await directory(proc, "admin", "tech1", "client_a1")
    assert await proc.process(assigned([TECH])) is Outcome.APPLIED
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 1
    [mail] = mailer.sent
    assert mail["To"] == f"{SEED_USERS['tech1'].name} <tech1@example.org>"
    assert mail["Subject"].startswith("Assigned to you: MR-2026-0034")
    assert mail["Auto-Submitted"] == "auto-generated"
    assert f"https://mms.example.org/requests/{REQ}" in mail.get_body(("plain",)).get_content()
    assert await emails.counts(app.state.db) == {"sent": 1}


@pytest.mark.req("NOT-1")
async def test_only_what_appendix_b_marks_as_email_is_queued(env):
    app, _, proc, _, _, clock, _ = env
    await directory(proc, "admin", "tech1", "client_a1")
    # A claim tells the client and the admins in-app only; a comment and a release likewise
    await proc.process(assigned([TECH], claimed=True, actor="tech1"))
    await proc.process(event("request.released", {
        **request_data(), "released_ids": [TECH], "released_names": ["T"], "by_id": TECH,
    }, actor="tech1", org=request_data()["org_id"]))
    await proc.process(event("comment.added", {
        **request_data(assigned_staff_ids=[TECH]), "comment_id": "c1", "author_id": CLIENT,
        "author_name": "Client A1", "author_role": "client", "internal": False,
        "attachment_count": 0,
    }, actor="client_a1", org=request_data()["org_id"]))
    assert await emails.counts(app.state.db) == {}
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 0 and mailer.sent == []


@pytest.mark.req("NOT-1")
async def test_a_decision_is_emailed_to_the_client_and_a_new_request_to_the_admins(env):
    app, _, proc, _, _, clock, _ = env
    await directory(proc, "admin", "client_a1")
    org = request_data()["org_id"]
    await proc.process(event("request.submitted", request_data(status="submitted", by_admin=False),
                             actor="client_a1", org=org))
    await proc.process(event("request.approved", request_data(), actor="admin", org=org))
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 2
    by_to = {m["To"].split("<")[-1].rstrip(">"): m["Subject"] for m in mailer.sent}
    assert by_to["admin@example.org"].startswith("New request MR-2026-0034")
    assert by_to["client.a1@example.org"].startswith("Request approved")


async def test_a_redelivered_event_queues_one_email(env):
    app, _, proc, *_ = env
    await directory(proc, "tech1", "admin")
    raw = assigned([TECH])
    await proc.process(raw)
    await proc.process(raw)
    assert await emails.counts(app.state.db) == {"pending": 1}


# --- The person's choice -----------------------------------------------------------------------


@pytest.mark.req("NOT-4")
async def test_turning_a_type_off_stops_the_email_even_for_one_already_queued(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, "admin", "tech1")
    await proc.process(assigned([TECH]))
    off = await http.put("/api/v1/notifications/preferences",
                         json={"email": {"request.assigned": False}},
                         headers=bearer(issuer, "tech1"))
    assert off.status_code == 200
    sender, mailer = sender_for(app, clock)
    await sender.send_due()
    assert mailer.sent == []
    assert await emails.counts(app.state.db) == {"skipped": 1}
    # ... and the notification is still in the app (in-app is always on)
    assert len((await listing(http, issuer, "tech1"))["items"]) == 1


@pytest.mark.req("NOT-4")
async def test_a_cancellation_reaches_staff_by_email_only_if_they_ask(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, "admin", "tech1", "client_a1")
    cancelled = event("request.cancelled", {
        **request_data(assigned_staff_ids=[TECH], status="cancelled"),
        "reason": None, "cancelled_by": "client",
    }, actor="client_a1", org=request_data()["org_id"])
    await proc.process(cancelled)
    sender, mailer = sender_for(app, clock)
    await sender.send_due()
    assert mailer.sent == []  # off by default for staff
    await http.put("/api/v1/notifications/preferences",
                   json={"email": {"request.cancelled": True}}, headers=bearer(issuer, "tech1"))
    await proc.process(event("request.cancelled", {
        **request_data(assigned_staff_ids=[TECH], status="cancelled"),
        "reason": None, "cancelled_by": "client",
    }, actor="client_a1", org=request_data()["org_id"]))
    await sender.send_due()
    assert [m["To"] for m in mailer.sent] == [f"{SEED_USERS['tech1'].name} <tech1@example.org>"]


async def test_a_disabled_person_gets_no_email(env):
    app, _, proc, _, _, clock, _ = env
    await directory(proc, "admin", "tech1")
    await proc.process(assigned([TECH]))
    await proc.process(event("user.disabled", {**person("tech1"), "status": "disabled"},
                             source="auth", key=TECH, version=9))
    sender, mailer = sender_for(app, clock)
    await sender.send_due()
    assert mailer.sent == [] and await emails.counts(app.state.db) == {"skipped": 1}


# --- The preferences routes --------------------------------------------------------------------


def flat(body: dict[str, Any]) -> dict[str, bool]:
    return {i["key"]: i["email"] for g in body["groups"] for i in g["items"]}


@pytest.mark.req("NOT-4")
async def test_each_role_sees_its_own_choices_with_the_defaults(env):
    _, http, _, _, issuer, *_ = env
    seen = {}
    for key in ("admin", "tech1", "client_a1", "viewer"):
        r = await http.get("/api/v1/notifications/preferences", headers=bearer(issuer, key))
        assert r.status_code == 200
        seen[key] = flat(r.json())
    visits = {"visit.scheduled": True, "visit.cancelled": True}
    assert seen["admin"] == {"request.submitted": True, "request.assigned": True,
                             "request.cancelled": False, "calibration.digest": True, **visits}
    assert seen["tech1"] == {"request.assigned": True, "request.cancelled": False, **visits}
    assert seen["client_a1"] == {"request.decided": True, "request.cancelled": True, **visits}
    assert seen["viewer"] == {}


@pytest.mark.req("NOT-4")
async def test_saving_changes_only_what_was_sent_and_refuses_what_is_not_yours(env):
    _, http, _, _, issuer, *_ = env
    put = await http.put("/api/v1/notifications/preferences",
                         json={"email": {"calibration.digest": False}},
                         headers=bearer(issuer, "admin"))
    assert put.status_code == 200
    assert flat(put.json())["calibration.digest"] is False
    assert flat(put.json())["request.submitted"] is True  # untouched
    again = await http.get("/api/v1/notifications/preferences", headers=bearer(issuer, "admin"))
    assert flat(again.json())["calibration.digest"] is False
    # Not yours: refused whole, and nothing of it is saved
    bad = await http.put("/api/v1/notifications/preferences",
                         json={"email": {"request.assigned": False, "calibration.digest": True}},
                         headers=bearer(issuer, "tech1"))
    assert bad.status_code == 422 and bad.json()["code"] == "unknown_type"
    kept = await http.get("/api/v1/notifications/preferences", headers=bearer(issuer, "tech1"))
    assert flat(kept.json())["request.assigned"] is True
    for body in ({"email": {"request.assigned": "no"}}, {"email": {}, "extra": 1}, {}):
        r = await http.put("/api/v1/notifications/preferences", json=body,
                           headers=bearer(issuer, "tech1"))
        assert r.status_code == 422


async def test_choices_are_per_person(env):
    _, http, _, _, issuer, *_ = env
    await http.put("/api/v1/notifications/preferences",
                   json={"email": {"request.assigned": False}}, headers=bearer(issuer, "tech1"))
    other = await http.get("/api/v1/notifications/preferences", headers=bearer(issuer, "tech2"))
    assert flat(other.json())["request.assigned"] is True


# --- The weekly digest (CAL-5) -----------------------------------------------------------------


class FakeOperations:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items, self.asked = items, 0

    async def due(self, within_days: int) -> list[dict[str, Any]]:
        self.asked += 1
        return self.items


def unit(n: int, state: str, due: str) -> dict[str, Any]:
    return {"unit_id": f"u{n}", "serial": f"SN-{n}", "due_state": state,
            "calibration_due_at": due, "station": {"code": f"JM-{n:03d}"},
            "model": {"manufacturer": "Vaisala", "model": "HMP155"}}


MONDAY_7 = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # Monday 07:00 in Jamaica


async def digest(env, items, now=MONDAY_7):
    app, _, _, fake, _, clock, _ = env
    clock.set(now)
    ops = FakeOperations(items)
    week = await calibration_digest.send_digest(
        client=app.state.mongo, db=app.state.db, redis=fake, operations=ops, clock=clock,
        tz="America/Jamaica", hour=7, within_days=30,
    )
    return week, ops


@pytest.mark.req("CAL-5")
async def test_the_digest_goes_to_every_admin_once_a_week_in_app_and_by_email(env):
    app, http, proc, fake, issuer, clock, _ = env
    await directory(proc, "admin", "tech_admin", "tech1", "client_a1")
    week, ops = await digest(env, [unit(1, "overdue", "2026-10-12T14:00:00Z"),
                                   unit(2, "due_soon", "2026-11-02T14:00:00Z")])
    assert week == "2026-W44" and ops.asked == 1
    for key in ("admin", "tech_admin"):
        [note] = (await listing(http, issuer, key))["items"]
        assert note["title"] == "2 sensors need calibration"
        assert note["body"] == "1 overdue, 1 due in the next 30 days"
        assert note["link"] == "/calibration" and note["type"] == "calibration.digest"
    for key in ("tech1", "client_a1"):
        assert (await listing(http, issuer, key))["items"] == []
    assert len([m for _, m in fake.sent if m["type"] == "notification"]) == 2

    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 2
    subjects = {m["Subject"] for m in mailer.sent}
    assert subjects == {"2 sensors need calibration · weekly digest"}
    body = mailer.sent[0].get_body(("html",)).get_content()
    assert "JM-001" in body and "Overdue (1)" in body and "12 Oct" in body

    # A second look the same week, here or on another instance, sends nothing more
    again, ops2 = await digest(env, [unit(1, "overdue", "2026-10-12T14:00:00Z")])
    assert again is None and ops2.asked == 0


@pytest.mark.req("CAL-5")
async def test_nothing_goes_before_monday_at_seven_and_an_empty_week_is_still_marked(env):
    app, http, proc, _, issuer, *_ = env
    await directory(proc, "admin")
    early, ops = await digest(env, [unit(1, "overdue", "2026-10-12T14:00:00Z")],
                              datetime(2026, 10, 26, 11, 59, tzinfo=UTC))
    assert early is None and ops.asked == 0
    quiet, _ = await digest(env, [])
    assert quiet == "2026-W44"
    assert (await listing(http, issuer, "admin"))["items"] == []
    assert await app.state.db["digest_runs"].count_documents({}) == 1


@pytest.mark.req("NOT-4")
async def test_an_admin_who_turned_the_digest_off_still_sees_it_in_the_app(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, "admin")
    await http.put("/api/v1/notifications/preferences",
                   json={"email": {"calibration.digest": False}}, headers=bearer(issuer, "admin"))
    await digest(env, [unit(1, "overdue", "2026-10-12T14:00:00Z")])
    assert len((await listing(http, issuer, "admin"))["items"]) == 1
    sender, mailer = sender_for(app, clock)
    await sender.send_due()
    assert mailer.sent == [] and await emails.counts(app.state.db) == {"skipped": 1}
