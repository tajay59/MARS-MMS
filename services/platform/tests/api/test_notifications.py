"""Notifications on real MongoDB and Redis (PRD NOT-1, NOT-2, NOT-5; TRD §3.5, §8.5, §13.4):
the directory, who is told, the push after the commit, the list with catch-up, and the socket."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
import redis as sync_redis
from mms_common.consumer import Outcome
from mms_common.events import Actor, Envelope, Resource
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A as ORG
from mms_common.testing.seed import SEED_USERS, TestIssuer
from mms_common.time import ManualClock
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.events.notification_consumer import processor
from app.main import create_app

REQ = "01900000-0000-7000-8000-0000000b0001"
BASE = "https://mms.test"


class FakeRedis:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.down = False

    async def publish(self, channel: str, payload: str) -> int:
        if self.down:
            raise ConnectionError("redis down")
        self.sent.append((channel, json.loads(payload)))
        return 1


def person(key: str, **extra: Any) -> dict[str, Any]:
    u = SEED_USERS[key]
    return {"user_id": u.id, "email": u.email, "name": u.name, "roles": list(u.roles),
            "status": u.status, "org_id": u.org_id, **extra}


def event(type_: str, data: dict[str, Any], *, actor: str | None = None, org: str | None = None,
          key: str = REQ, version: int = 1, source: str = "operations") -> bytes:
    seed = SEED_USERS[actor] if actor else None
    return Envelope(
        event_id=new_id(), type=type_, occurred_at=datetime(2026, 10, 21, 9, tzinfo=UTC),
        source=source, key=key, aggregate_version=version,
        actor=Actor(user_id=seed.id if seed else None, name=seed.name if seed else None,
                    roles=list(seed.roles) if seed else []),
        org_id=org, resource=Resource(type="request", id=key), correlation_id="r",
        data=data,
    ).model_dump_json().encode()


def request_data(**extra: Any) -> dict[str, Any]:
    return {"request_id": REQ, "ref": "MR-2026-0034", "org_id": ORG, "station_ids": [],
            "category": "fault", "priority": "high", "status": "approved",
            "title": "Logger not reporting", "created_by": SEED_USERS["client_a1"].id,
            "assigned_staff_ids": [], **extra}


@pytest_asyncio.fixture
async def env(mongo_uri, redis_url):
    clock = ManualClock(datetime(2026, 10, 21, 9, tzinfo=UTC))
    issuer = TestIssuer(clock)
    suffix = uuid.uuid4().hex[:8]
    settings = Settings(
        mongo_uri=mongo_uri, mongo_db=f"notification_{suffix}", audit_mongo_uri=mongo_uri,
        audit_db=f"audit_{suffix}", redis_url=redis_url, run_background=False,
        ws_heartbeat_s=0.2,
    )
    app = create_app(settings, ready_checks={}, clock=clock, keys=issuer.keys)
    async with app.router.lifespan_context(app):
        dead: list[tuple[bytes, str]] = []

        async def to_dlq(raw: bytes, reason: str) -> None:
            dead.append((raw, reason))

        fake = FakeRedis()
        proc = processor(app.state.mongo, app.state.db, to_dlq, clock, fake)  # type: ignore[arg-type]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
            yield app, http, proc, fake, issuer, clock, dead
        await app.state.mongo.drop_database(settings.mongo_db)
        await app.state.audit_mongo.drop_database(settings.audit_db)


async def directory(proc, *keys: str) -> None:
    """Put people in the directory the way auth's events do."""
    for key in keys:
        raw = event("user.created", {**person(key), "via": "test"}, source="auth",
                    key=SEED_USERS[key].id)
        assert await proc.process(raw) is Outcome.APPLIED


def bearer(issuer: TestIssuer, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {issuer.token(key)}"}


async def listing(http, issuer, key: str, query: str = "") -> dict[str, Any]:
    r = await http.get(f"/api/v1/notifications{query}", headers=bearer(issuer, key))
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


ALL = ("admin", "tech1", "tech2", "viewer", "client_a1", "client_a2")


# --- The directory and who is told ------------------------------------------------------------


@pytest.mark.req("NOT-1")
async def test_a_registration_tells_the_active_admins_and_pushes_after_the_commit(env):
    _, http, proc, fake, issuer, *_ = env
    await directory(proc, "admin", "tech1")
    raw = event("user.registered", {**person("client_b1"), "status": "pending",
                                    "proposed_org_name": "Authority C"},
                source="auth", key=SEED_USERS["client_b1"].id)
    assert await proc.process(raw) is Outcome.APPLIED
    got = await listing(http, issuer, "admin")
    [item] = got["items"]
    assert item["type"] == "account.registered" and item["read"] is False
    assert item["link"] == f"/admin/registrations/{SEED_USERS['client_b1'].id}"
    assert got["unread"] == 1
    assert (await listing(http, issuer, "tech1"))["items"] == []
    [(channel, message)] = fake.sent
    assert channel == f"ws:user:{SEED_USERS['admin'].id}"
    assert message["type"] == "notification" and message["data"]["id"] == item["id"]


@pytest.mark.req("NOT-1")
async def test_a_redelivered_event_makes_nothing_twice(env):
    _, http, proc, fake, issuer, *_ = env
    await directory(proc, "admin", "client_a1")
    raw = event("request.submitted", request_data(status="submitted", by_admin=False),
                actor="client_a1", org=ORG)
    assert await proc.process(raw) is Outcome.APPLIED
    assert await proc.process(raw) is Outcome.DUPLICATE
    assert len((await listing(http, issuer, "admin"))["items"]) == 1
    assert len([m for _, m in fake.sent if m["type"] == "notification"]) == 1


async def test_nothing_is_pushed_when_the_event_was_a_duplicate_or_dead(env):
    _, _, proc, fake, _, _, dead = env
    await directory(proc, "admin")
    assert await proc.process(b"not an event") is Outcome.DEAD_LETTERED
    assert dead and fake.sent == []


async def test_a_push_that_fails_does_not_fail_the_event_and_the_list_catches_up(env):
    _, http, proc, fake, issuer, *_ = env
    await directory(proc, "admin", "client_a1")
    fake.down = True
    raw = event("request.submitted", request_data(status="submitted", by_admin=False),
                actor="client_a1", org=ORG)
    assert await proc.process(raw) is Outcome.APPLIED
    assert len((await listing(http, issuer, "admin"))["items"]) == 1  # NOT-2


@pytest.mark.req("NOT-1")
@pytest.mark.req("REQ-10")
async def test_an_internal_comment_reaches_staff_and_never_the_client_or_their_page(env):
    _, http, proc, fake, issuer, *_ = env
    await directory(proc, *ALL)
    raw = event("comment.added", {
        **request_data(assigned_staff_ids=[SEED_USERS["tech1"].id, SEED_USERS["tech2"].id]),
        "comment_id": new_id(), "author_id": SEED_USERS["tech1"].id,
        "author_name": SEED_USERS["tech1"].name, "author_role": "technician",
        "internal": True, "attachment_count": 1,
    }, actor="tech1", org=ORG)
    assert await proc.process(raw) is Outcome.APPLIED
    assert len((await listing(http, issuer, "tech2"))["items"]) == 1
    assert (await listing(http, issuer, "tech1"))["items"] == []  # the author
    for client in ("client_a1", "client_a2"):
        assert (await listing(http, issuer, client))["items"] == []
    audience = {c.split(":")[-1] for c, _ in fake.sent}
    assert SEED_USERS["client_a1"].id not in audience
    assert SEED_USERS["client_a2"].id not in audience
    assert SEED_USERS["viewer"].id in audience  # staff pages learn of it (entity.updated)


@pytest.mark.req("NOT-5")
async def test_a_status_change_is_pushed_to_staff_and_the_organization(env):
    _, _, proc, fake, *_ = env
    await directory(proc, *ALL)
    raw = event("request.status_changed", {**request_data(), "from_status": "submitted",
                                           "to_status": "approved", "reason": None},
                actor="admin", org=ORG)
    await proc.process(raw)
    pushed = {c.split(":")[-1]: m for c, m in fake.sent}
    assert set(pushed) == {SEED_USERS[k].id for k in ALL if k != "client_b1"}
    message = next(iter(pushed.values()))
    assert message == {"type": "entity.updated", "entity": "request", "id": REQ,
                       "status": "approved", "kind": "status"}


async def test_another_organizations_client_hears_of_nothing(env):
    _, http, proc, fake, issuer, *_ = env
    await directory(proc, "admin", "client_a1", "client_b1")
    await proc.process(event("request.status_changed", {
        **request_data(), "from_status": "submitted", "to_status": "approved", "reason": None,
    }, actor="admin", org=ORG))
    audience = {c.split(":")[-1] for c, _ in fake.sent}
    assert SEED_USERS["client_b1"].id not in audience
    assert (await listing(http, issuer, "client_b1"))["items"] == []


async def test_a_disabled_or_pending_person_is_not_told(env):
    _, http, proc, _, issuer, *_ = env
    await directory(proc, "admin")
    await proc.process(event("user.disabled", {**person("tech1"), "status": "disabled"},
                             source="auth", key=SEED_USERS["tech1"].id))
    await proc.process(event("request.assigned", {
        **request_data(assigned_staff_ids=[SEED_USERS["tech1"].id]),
        "staff_ids": [SEED_USERS["tech1"].id], "staff_names": ["T"], "claimed": False,
        "by_id": SEED_USERS["admin"].id,
    }, actor="admin", org=ORG))
    # Tech 1 was named, but a disabled person gets nothing pushed (they can't log in anyway)
    assert (await listing(http, issuer, "admin"))["items"] == []


async def test_an_older_user_event_does_not_undo_a_newer_one(env):
    _, _, proc, _, _, _, _ = env
    key = "tech1"
    uid = SEED_USERS[key].id
    await proc.process(event("user.updated", {**person(key), "name": "Newer",
                                              "changed_fields": ["name"]},
                             source="auth", key=uid, version=5))
    await proc.process(event("user.updated", {**person(key), "name": "Older",
                                              "changed_fields": ["name"]},
                             source="auth", key=uid, version=2))
    from app.repo import directory as repo

    db = proc._db  # type: ignore[attr-defined]
    assert (await repo.get(db, uid))["name"] == "Newer"  # type: ignore[index]


# --- The list (NOT-2) --------------------------------------------------------------------------


async def make_notifications(env, n: int) -> None:
    _, _, proc, *_ = env
    await directory(proc, "admin", "client_a1")
    for _ in range(n):
        await proc.process(event("request.submitted", request_data(status="submitted",
                                                                  by_admin=False),
                                 actor="client_a1", org=ORG))


@pytest.mark.req("NOT-2")
async def test_the_list_is_newest_first_with_paging_and_the_unread_count(env):
    _, http, _, _, issuer, *_ = env
    await make_notifications(env, 5)
    first = await listing(http, issuer, "admin", "?limit=2")
    assert len(first["items"]) == 2 and first["unread"] == 5 and first["next_before"]
    ids = [i["id"] for i in first["items"]]
    assert ids == sorted(ids, reverse=True)
    older = await listing(http, issuer, "admin", f"?limit=10&before={first['next_before']}")
    assert len(older["items"]) == 3 and older["next_before"] is None
    assert {i["id"] for i in older["items"]}.isdisjoint(ids)


@pytest.mark.req("NOT-2")
async def test_a_browser_that_was_away_asks_for_everything_after_the_last_one_it_has(env):
    _, http, proc, _, issuer, *_ = env
    await make_notifications(env, 3)
    seen = (await listing(http, issuer, "admin"))["items"][0]["id"]
    for _ in range(2):
        await proc.process(event("request.submitted", request_data(status="submitted",
                                                                  by_admin=False),
                                 actor="client_a1", org=ORG))
    caught_up = await listing(http, issuer, "admin", f"?after={seen}")
    assert len(caught_up["items"]) == 2
    assert all(i["id"] > seen for i in caught_up["items"])


@pytest.mark.req("NOT-2")
async def test_reading_one_or_all_and_the_filters(env):
    _, http, _, _, issuer, *_ = env
    await make_notifications(env, 3)
    items = (await listing(http, issuer, "admin"))["items"]
    r = await http.post(f"/api/v1/notifications/{items[0]['id']}/read",
                        headers=bearer(issuer, "admin"))
    assert r.status_code == 200 and r.json() == {"marked": 1, "unread": 2}
    again = await http.post(f"/api/v1/notifications/{items[0]['id']}/read",
                            headers=bearer(issuer, "admin"))
    assert again.status_code == 200 and again.json()["unread"] == 2
    assert len((await listing(http, issuer, "admin", "?unread=true"))["items"]) == 2
    assert len((await listing(http, issuer, "admin", "?group=requests"))["items"]) == 3
    assert (await listing(http, issuer, "admin", "?group=comments"))["items"] == []
    done = await http.post("/api/v1/notifications/read-all", headers=bearer(issuer, "admin"))
    assert done.json() == {"marked": 2, "unread": 0}


@pytest.mark.req("NOT-2")
async def test_nobody_reads_or_marks_another_persons_notification(env):
    _, http, _, _, issuer, *_ = env
    await make_notifications(env, 1)
    mine = (await listing(http, issuer, "admin"))["items"][0]["id"]
    for key in ("tech1", "client_a1"):
        r = await http.post(f"/api/v1/notifications/{mine}/read", headers=bearer(issuer, key))
        assert r.status_code == 404  # rule 4
        assert (await listing(http, issuer, key))["items"] == []
    assert (await listing(http, issuer, "admin"))["unread"] == 1
    assert (await http.get("/api/v1/notifications")).status_code == 401


# --- The socket (NOT-1, NOT-5; TRD §13.4) ------------------------------------------------------


@pytest.fixture
def live(mongo_uri, redis_url):
    clock = ManualClock(datetime(2026, 10, 21, 9, tzinfo=UTC))
    issuer = TestIssuer(clock)
    suffix = uuid.uuid4().hex[:8]
    settings = Settings(
        mongo_uri=mongo_uri, mongo_db=f"notification_{suffix}", audit_mongo_uri=mongo_uri,
        audit_db=f"audit_{suffix}", redis_url=redis_url, run_background=False,
        ws_heartbeat_s=0.3,
    )
    app = create_app(settings, ready_checks={}, clock=clock, keys=issuer.keys)
    with TestClient(app) as client:
        yield client, issuer, clock, sync_redis.Redis.from_url(redis_url)


@pytest.mark.req("NOT-1")
def test_a_socket_receives_its_own_persons_messages_and_nobody_elses(live):
    client, issuer, _, redis = live
    mine, other = SEED_USERS["tech1"].id, SEED_USERS["tech2"].id
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": issuer.token("tech1")}))
        assert json.loads(ws.receive_text()) == {"type": "ready"}
        redis.publish(f"ws:user:{other}", json.dumps({"type": "entity.updated", "id": "not-yours"}))
        redis.publish(f"ws:user:{mine}", json.dumps({"type": "entity.updated", "id": "yours"}))
        got = json.loads(ws.receive_text())
        while got.get("type") == "ping":  # the heartbeat is short in this test
            got = json.loads(ws.receive_text())
        assert got["id"] == "yours"
        ws.close()


@pytest.mark.parametrize("first", [
    json.dumps({"type": "auth", "token": "not-a-token"}),
    json.dumps({"type": "hello"}),
    "not json",
])
def test_a_socket_that_does_not_authenticate_is_closed(live, first):
    client, *_ = live
    with client.websocket_connect("/ws") as ws:
        ws.send_text(first)
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert closed.value.code == 4401


def test_a_socket_ends_with_4401_when_its_token_runs_out_unless_it_is_renewed(live):
    client, issuer, clock, _ = live
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": issuer.token("tech1")}))
        assert json.loads(ws.receive_text())["type"] == "ready"
        clock.advance(minutes=30)  # past the access token's life
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(20):
                ws.receive_text()
    assert closed.value.code == 4401


def test_a_renewed_token_keeps_the_socket_open_but_only_for_the_same_person(live):
    client, issuer, clock, _ = live
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": issuer.token("tech1")}))
        assert json.loads(ws.receive_text())["type"] == "ready"
        clock.advance(minutes=10)
        ws.send_text(json.dumps({"type": "auth", "token": issuer.token("tech1")}))
        clock.advance(minutes=10)  # the first token is over now, the second is not
        assert json.loads(ws.receive_text())["type"] == "ping"
        ws.send_text(json.dumps({"type": "auth", "token": issuer.token("tech2")}))
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(20):
                ws.receive_text()
    assert closed.value.code == 4401
