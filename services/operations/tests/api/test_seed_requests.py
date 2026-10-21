"""The example requests (`python -m app.cli seed-requests`): they cover every status, follow the
workflow, show up on the real screens' routes, never touch the audit chain, and come out again."""

from __future__ import annotations

from collections import Counter

from mms_common.testing.seed import ORG_A, ORG_B

from app.domain.requests.state import RULES, Status
from app.jobs import seed_requests

# Every step a seeded history may take: an action in the table, or one that visits make (derived)
ALLOWED_STEPS = {(None, "submitted"), (None, "approved")} | {
    (a.value, b.value) for (a, _), r in RULES.items() for b in [r.to]
} | {
    ("assigned", "scheduled"), ("scheduled", "in_progress"), ("in_progress", "client_review"),
}


async def two_orgs(ops) -> None:
    await ops.station(code="JM-KIN-001", owner_org_id=ORG_A)
    await ops.station(code="JM-MBJ-002", owner_org_id=ORG_A)
    await ops.station(code="TT-POS-001", owner_org_id=ORG_B, country="TT",
                      time_zone="America/Port_of_Spain")


async def seed(ops, count: int = 50) -> int:
    return await seed_requests.run(ops.app.state.mongo, ops.app.state.db, ops.clock, count=count)


async def test_it_makes_fifty_examples_in_every_status(ops):
    await two_orgs(ops)
    assert await seed(ops) == 50
    docs = [d async for d in ops.db["requests"].find({})]
    assert len(docs) == 50
    counts = Counter(d["status"] for d in docs)
    assert set(counts) == {s.value for s in Status} - {"reopened"}  # reopened is never at rest
    assert counts["submitted"] > counts["closed"] > 0
    assert all(d["example"] is True and d["title"].startswith("[Example] ") for d in docs)
    assert len({d["ref"] for d in docs}) == 50
    assert {d["org_id"] for d in docs} <= {ORG_A, ORG_B}


async def test_each_history_follows_the_workflow_and_stays_in_the_past(ops):
    await two_orgs(ops)
    await seed(ops)
    async for d in ops.db["requests"].find({}):
        history = d["status_history"]
        assert history[-1]["to"] == d["status"]
        assert d["version"] == len(history)
        assert history[0]["from"] is None
        for before, after in zip(history, history[1:], strict=False):
            step = (before["to"], after["to"])
            assert step in ALLOWED_STEPS, (d["ref"], step)
            assert before["at"] <= after["at"]
        now = ops.clock.now().replace(tzinfo=None)  # Mongo hands datetimes back without a zone
        assert d["created_at"] <= history[0]["at"] <= history[-1]["at"] <= now
        if d["status"] == "denied":
            assert d["denial_reason"]
        if d["status"] == "cancelled":
            assert d["cancel_reason"]
        assert bool(d["assigned_staff"]) == (d["status"] in (
            "assigned", "scheduled", "in_progress", "client_review", "closed"))


async def test_the_ids_sort_by_date_so_the_list_is_newest_first(ops):
    await two_orgs(ops)
    await seed(ops)
    docs = [d async for d in ops.db["requests"].find({}).sort("_id", 1)]
    created = [d["created_at"] for d in docs]
    assert created == sorted(created)
    refs = [int(d["ref"].rsplit("-", 1)[1]) for d in docs]
    assert refs == sorted(refs)


async def test_they_appear_on_the_real_routes_for_the_right_people(ops):
    await two_orgs(ops)
    await seed(ops)
    admin = await ops.http.get("/api/v1/requests?limit=200", headers=ops.bearer("admin"))
    assert admin.status_code == 200 and admin.json()["total"] == 50
    mine = await ops.http.get("/api/v1/requests?limit=200", headers=ops.bearer("client_a1"))
    assert 0 < mine.json()["total"] < 50
    assert {r["org_id"] for r in mine.json()["items"]} == {ORG_A}
    first = admin.json()["items"][0]
    one = await ops.http.get(f"/api/v1/requests/{first['id']}", headers=ops.bearer("admin"))
    assert one.status_code == 200
    assert one.json()["requested_by"]["name"] == "Example requester"
    # every status reads back through the response model, with the right buttons
    for item in admin.json()["items"]:
        detail = await ops.http.get(f"/api/v1/requests/{item['id']}", headers=ops.bearer("admin"))
        assert detail.status_code == 200, item["status"]
        if item["status"] in ("denied", "closed", "cancelled"):
            assert detail.json()["actions"] == []


async def test_nothing_fake_reaches_the_audit_chain(ops):
    await two_orgs(ops)
    before = await ops.db["outbox"].count_documents({})
    await seed(ops)
    assert await ops.db["outbox"].count_documents({}) == before  # no events at all


async def test_a_smaller_count_still_covers_each_status_it_can(ops):
    await two_orgs(ops)
    assert await seed(ops, count=9) == 9
    assert len({d["status"] async for d in ops.db["requests"].find({})}) == 9


async def test_they_can_be_removed_without_touching_a_real_request(ops):
    await two_orgs(ops)
    stations = await ops.http.get("/api/v1/stations", headers=ops.bearer("admin"))
    station = stations.json()["items"][0]
    real = await ops.http.post(
        "/api/v1/requests", headers=ops.bearer("admin"),
        json={"title": "A real one", "description": "x", "category": "fault", "priority": "normal",
              "org_id": station["owner_org_id"], "station_ids": [station["id"]]},
    )
    assert real.status_code == 201
    await seed(ops)
    assert await seed_requests.count_examples(ops.db) == 50
    assert await seed_requests.remove(ops.db) == 50
    assert await ops.db["requests"].count_documents({}) == 1
    left = await ops.db["requests"].find_one({})
    assert left["title"] == "A real one" and "example" not in left


async def test_without_stations_nothing_is_made(ops):
    assert await seed(ops) == 0
    assert await ops.db["requests"].count_documents({}) == 0
