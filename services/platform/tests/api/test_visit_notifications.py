"""Visit notifications on real MongoDB and Redis (PRD VIS-11, NOT-1, NOT-4, NOT-5, Appendix B;
W10 slice 4): who is told, the push after the commit, the email and the person's choice."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A as ORG
from mms_common.testing.seed import SEED_USERS

from app.repo import emails
from tests.api.notify_support import ALL, REQ, bearer, directory, event, listing
from tests.api.test_notification_emails import sender_for

TECH, TECH2, ADMIN, CLIENT = (
    SEED_USERS["tech1"].id, SEED_USERS["tech2"].id, SEED_USERS["admin"].id,
    SEED_USERS["client_a1"].id,
)
VISIT = "01900000-0000-7000-8000-0000000c0001"


def visit_data(**extra: Any) -> dict[str, Any]:
    return {
        "visit_id": VISIT, "ref": "VR-2026-0042-01", "request_id": REQ,
        "request_ref": "MR-2026-0042", "org_id": ORG, "title": "Rain gauge reads zero",
        "created_by": CLIENT, "status": "planned",
        "planned_start": datetime(2026, 10, 22, 13, 0, tzinfo=UTC),
        "planned_end": datetime(2026, 10, 23, 21, 0, tzinfo=UTC),
        "staff_ids": [TECH, TECH2], "lead_staff_id": TECH2, "station_ids": ["s1"],
        "station_owners": [{"station_id": "s1", "owner_staff_id": TECH}],
        "time_zone": "America/Jamaica", **extra,
    }


def visit_event(type_: str, actor: str = "admin", **extra: Any) -> bytes:
    return event(type_, visit_data(**extra), actor=actor, org=ORG)


@pytest.mark.req("VIS-11")
async def test_a_planned_visit_tells_the_client_and_the_team_and_pushes_after_the_commit(env):
    _, http, proc, fake, issuer, *_ = env
    await directory(proc, *ALL)
    assert await proc.process(visit_event("visit.scheduled")) is Outcome.APPLIED
    for who in ("client_a1", "tech1", "tech2"):
        [item] = (await listing(http, issuer, who))["items"]
        assert item["type"] == "visit.scheduled" and item["title"] == "Visit planned"
        assert item["link"] == f"/visits/{VISIT}"
        assert item["entity"] == {"type": "visit", "id": VISIT}
        assert item["body"] == "VR-2026-0042-01 · Rain gauge reads zero · Thu 22 Oct, 08:00 EST"
    assert (await listing(http, issuer, "client_a2"))["items"] == []  # a colleague of the client
    assert (await listing(http, issuer, "admin"))["items"] == []  # the person who did it
    live = {c.split(":")[-1]: m for c, m in fake.sent if m["type"] == "entity.updated"}
    assert set(live) == {SEED_USERS[k].id for k in ALL if k != "client_b1"}
    assert next(iter(live.values())) == {
        "type": "entity.updated", "entity": "visit", "id": VISIT, "request_id": REQ,
        "status": "planned", "kind": "visit",
    }


@pytest.mark.req("VIS-11")
async def test_another_organizations_client_hears_of_no_visit(env):
    _, http, proc, fake, issuer, *_ = env
    await directory(proc, "admin", "tech1", "client_a1", "client_b1")
    await proc.process(visit_event("visit.scheduled"))
    assert (await listing(http, issuer, "client_b1"))["items"] == []
    assert SEED_USERS["client_b1"].id not in {c.split(":")[-1] for c, _ in fake.sent}


async def test_a_redelivered_visit_event_makes_nothing_twice(env):
    _, http, proc, _, issuer, *_ = env
    await directory(proc, "admin", "tech1", "client_a1")
    raw = visit_event("visit.scheduled")
    assert await proc.process(raw) is Outcome.APPLIED
    assert await proc.process(raw) is Outcome.DUPLICATE
    assert len((await listing(http, issuer, "tech1"))["items"]) == 1


@pytest.mark.req("VIS-3")
async def test_changing_an_owner_tells_the_old_and_the_new_owner(env):
    _, http, proc, _, issuer, *_ = env
    await directory(proc, *ALL)
    await proc.process(visit_event(
        "visit.station_owner_changed", actor="tech2", status="started", station_id="s1",
        from_staff_id=TECH, to_staff_id=TECH2, station_name="Kingston Harbour",
        station_code="JM-KIN-001",
    ))
    [gone] = (await listing(http, issuer, "tech1"))["items"]
    assert gone["title"] == "You no longer own Kingston Harbour"
    assert (await listing(http, issuer, "tech2"))["items"] == []  # they made the change
    assert (await listing(http, issuer, "client_a1"))["items"] == []  # not the client's news


@pytest.mark.req("VIS-9")
async def test_an_ended_visit_tells_staff_in_the_app_only(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    await proc.process(visit_event(
        "visit.ended", actor="tech1", status="ended",
        ended_at=datetime(2026, 10, 22, 21, tzinfo=UTC),
        additional_visit_required=True, follow_up_notes="Replace the panel", overrides=[],
    ))
    [item] = (await listing(http, issuer, "tech2"))["items"]
    assert item["title"] == "Visit ended" and "another visit needed" in item["body"]
    assert "Replace the panel" not in item["body"]
    assert (await listing(http, issuer, "client_a1"))["items"] == []
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 0 and mailer.sent == []  # nothing for email


@pytest.mark.req("NOT-1")
async def test_the_email_has_the_day_and_a_link_to_the_visit(env):
    app, _, proc, _, _, clock, _ = env
    await directory(proc, *ALL)
    await proc.process(visit_event("visit.scheduled"))
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 3  # the client and both on the team; not who planned it
    to = sorted(m["To"] for m in mailer.sent)
    assert any("client.a1@example.org" in t for t in to)
    mail = next(m for m in mailer.sent if "client.a1@example.org" in m["To"])
    assert mail["Subject"].startswith("Visit planned: VR-2026-0042-01")
    text = mail.get_body(("plain",)).get_content()
    assert f"View the visit: https://mms.example.org/visits/{VISIT}" in text
    assert "Thu 22 Oct, 08:00 EST" in text
    html = mail.get_body(("html",)).get_content()
    assert "View the visit" in html
    assert await emails.counts(app.state.db) == {"sent": 3}


@pytest.mark.req("NOT-4")
async def test_a_person_can_turn_visit_emails_off_and_still_see_them_in_the_app(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    off = await http.put("/api/v1/notifications/preferences",
                         json={"email": {"visit.scheduled": False}},
                         headers=bearer(issuer, "client_a1"))
    assert off.status_code == 200
    await proc.process(visit_event("visit.scheduled"))
    sender, mailer = sender_for(app, clock)
    await sender.send_due()  # the client's row is skipped: they turned it off
    assert len(mailer.sent) == 2  # the two on the team
    assert all("client.a1@example.org" not in m["To"] for m in mailer.sent)
    assert len((await listing(http, issuer, "client_a1"))["items"]) == 1


@pytest.mark.req("NOT-1")
async def test_a_cancelled_visit_is_emailed_and_one_cancelled_with_its_request_is_not(env):
    app, http, proc, _, issuer, clock, _ = env
    await directory(proc, *ALL)
    await proc.process(visit_event("visit.cancelled", status="cancelled", reason="Storm",
                                   by_request=False))
    sender, mailer = sender_for(app, clock)
    assert await sender.send_due() == 3
    assert all(m["Subject"].startswith("Visit cancelled:") for m in mailer.sent)
    # A request's own cancellation tells them; the visit adds no second notification
    again = visit_event("visit.cancelled", status="cancelled", reason=None, by_request=True,
                        visit_id=new_id())
    await proc.process(again)
    assert len((await listing(http, issuer, "client_a1"))["items"]) == 1


async def test_a_visit_event_the_module_only_follows_makes_no_notification(env):
    _, http, proc, fake, issuer, *_ = env
    await directory(proc, *ALL)
    assert await proc.process(visit_event("visit.started", started_at=datetime(
        2026, 10, 22, 13, tzinfo=UTC), status="started")) is Outcome.APPLIED
    assert (await listing(http, issuer, "client_a1"))["items"] == []
    assert fake.sent and all(m["type"] == "entity.updated" for _, m in fake.sent)
