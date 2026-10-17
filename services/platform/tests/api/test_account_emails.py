"""Account emails on a real MongoDB replica set: queued once per event, sent at least once,
links minted on send (PRD NOT-3; TRD §3.5, §6.2, §8.5; TP "Event backbone")."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
import pytest_asyncio
from mms_common import migrations, mongo
from mms_common.consumer import Outcome
from mms_common.events import Actor, Envelope, Resource
from mms_common.ids import new_id
from mms_common.time import ManualClock

from app import migrations as app_migrations
from app.events.notification_consumer import processor
from app.jobs.account_emails import Link, LinkGone, Sender
from app.repo import emails

USER = "01900000-0000-7000-8000-000000000081"


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail_next = 0

    async def send(self, message: EmailMessage) -> None:
        if self.fail_next:
            self.fail_next -= 1
            raise ConnectionRefusedError("relay down")
        self.sent.append(message)


class FakeLinks:
    def __init__(self) -> None:
        self.minted: list[tuple[str, str]] = []
        self.gone: set[str] = set()

    async def mint(self, kind: str, link_id: str) -> Link:
        if link_id in self.gone:
            raise LinkGone(kind)
        self.minted.append((kind, link_id))
        path = "invite" if kind == "invitation" else "reset-password"
        return Link(url=f"https://mms.example.org/{path}/tok-{len(self.minted)}",
                    email="new.address@example.org", name="Maria Lopez")


@pytest_asyncio.fixture
async def env(mongo_uri):
    client = mongo.connect(mongo_uri)
    db = client[f"notification_{uuid.uuid4().hex[:8]}"]
    clock = ManualClock(datetime(2026, 10, 17, 9, tzinfo=UTC))
    await migrations.run(db, app_migrations, clock)
    dead: list[tuple[bytes, str]] = []

    async def to_dlq(raw: bytes, reason: str) -> None:
        dead.append((raw, reason))

    mailer, links = FakeMailer(), FakeLinks()
    sender = Sender(db=db, mailer=mailer, links=links, clock=clock,
                    mail_from="MARS-MMS <no-reply@mms.example.org>",
                    app_url="https://mms.example.org")
    yield processor(client, db, to_dlq, clock), sender, mailer, links, db, clock, dead
    await client.drop_database(db.name)
    await client.close()


def event(type_: str, data: dict) -> bytes:
    return Envelope(
        event_id=new_id(),
        type=type_,
        occurred_at=datetime(2026, 10, 17, 9, tzinfo=UTC),
        source="auth",
        key=USER,
        aggregate_version=2,
        actor=Actor(user_id="admin-1", name="Andrea Campbell", roles=["admin"]),
        resource=Resource(type="user", id=USER),
        correlation_id="req-1",
        data=data,
    ).model_dump_json().encode()


def user(status: str, **extra) -> dict:
    return {"user_id": USER, "email": "maria@example.org", "name": "Maria Lopez",
            "roles": ["client"], "status": status, "org_id": None, **extra}


@pytest.mark.req("NOT-3")
async def test_approval_is_emailed_once_even_if_the_event_comes_twice(env):
    proc, sender, mailer, _, db, _, _ = env
    raw = event("user.approved", user("active"))
    assert await proc.process(raw) is Outcome.APPLIED
    assert await proc.process(raw) is Outcome.DUPLICATE
    assert await sender.send_due() == 1
    assert await sender.send_due() == 0
    [message] = mailer.sent
    assert message["To"] == "Maria Lopez <maria@example.org>"
    assert message["Subject"] == "Your MARS-MMS account is approved"
    assert "https://mms.example.org/login" in message.get_body(("plain",)).get_content()
    assert message.get_body(("html",)) is not None
    assert await emails.counts(db) == {"sent": 1}


@pytest.mark.req("NOT-3")
async def test_reset_link_is_minted_at_send_time_and_uses_auth_address(env):
    proc, sender, mailer, links, _, _, _ = env
    await proc.process(event("auth.password_reset_requested",
                             {"user_id": USER, "reset_id": "reset-1"}))
    assert links.minted == []  # nothing minted while queueing
    await sender.send_due()
    assert links.minted == [("reset", "reset-1")]
    [message] = mailer.sent
    assert message["To"] == "Maria Lopez <new.address@example.org>"
    text = message.get_body(("plain",)).get_content()
    assert "https://mms.example.org/reset-password/tok-1" in text


@pytest.mark.req("NOT-3")
async def test_invitation_and_rejection_are_emailed(env):
    proc, sender, mailer, links, _, _, _ = env
    await proc.process(event("user.invited", user("invited", invitation_id="inv-1")))
    await proc.process(event("user.rejected", user("rejected", reason="Unknown organization")))
    assert await sender.send_due() == 2
    subjects = sorted(m["Subject"] for m in mailer.sent)
    assert subjects == ["You're invited to MARS-MMS", "Your MARS-MMS registration"]
    assert links.minted == [("invitation", "inv-1")]


async def test_events_without_an_email_queue_nothing(env):
    proc, sender, mailer, _, db, _, _ = env
    for type_, data in [("user.registered", user("pending", proposed_org_name="X")),
                        ("auth.login_succeeded", {"user_id": USER, "email_hash": "ab" * 32})]:
        assert await proc.process(event(type_, data)) is Outcome.APPLIED
    assert await sender.send_due() == 0
    assert await db["email_queue"].count_documents({}) == 0


async def test_a_link_auth_no_longer_issues_is_skipped(env):
    proc, sender, mailer, links, db, _, _ = env
    links.gone.add("reset-used")
    await proc.process(event("auth.password_reset_requested",
                             {"user_id": USER, "reset_id": "reset-used"}))
    await sender.send_due()
    assert mailer.sent == []
    row = await db["email_queue"].find_one()
    assert row["status"] == "skipped" and row["last_error"] == "link no longer valid"


async def test_a_relay_failure_retries_with_backoff_then_sends(env):
    proc, sender, mailer, _, db, clock, _ = env
    mailer.fail_next = 2
    await proc.process(event("user.approved", user("active")))
    await sender.send_due()
    row = await db["email_queue"].find_one()
    assert row["status"] == "pending" and row["attempts"] == 1
    assert row["next_attempt_at"].replace(tzinfo=UTC) == clock.now() + timedelta(minutes=1)
    assert "relay down" in row["last_error"]
    assert await sender.send_due() == 0  # not due yet
    clock.advance(minutes=1)
    await sender.send_due()
    clock.advance(minutes=2)
    await sender.send_due()
    assert len(mailer.sent) == 1
    assert (await db["email_queue"].find_one())["status"] == "sent"


async def test_after_the_last_attempt_the_email_is_marked_failed(env):
    proc, sender, mailer, _, db, clock, _ = env
    mailer.fail_next = 100
    await proc.process(event("user.approved", user("active")))
    for _ in range(12):
        await sender.send_due()
        clock.advance(hours=1)
    row = await db["email_queue"].find_one()
    assert row["status"] == "failed" and row["attempts"] == 10
    assert row["done_at"] is not None


async def test_a_sender_that_died_mid_send_hands_the_row_on(env):
    proc, sender, mailer, _, db, clock, _ = env
    await proc.process(event("user.approved", user("active")))
    assert await emails.claim(db, clock.now()) is not None  # claimed, then the process died
    assert await sender.send_due() == 0
    clock.advance(seconds=emails.LEASE.total_seconds() + 1)
    assert await sender.send_due() == 1
    assert len(mailer.sent) == 1


async def test_two_senders_never_send_the_same_email(env):
    proc, sender, mailer, _, _, _, _ = env
    for _ in range(10):
        await proc.process(event("user.approved", user("active")))
    handled = await asyncio.gather(sender.send_due(), sender.send_due(), sender.send_due())
    assert sum(handled) == 10
    assert len(mailer.sent) == 10
