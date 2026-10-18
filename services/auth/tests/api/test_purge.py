"""AUTH-5: pending registrations are deleted after 30 days."""

from datetime import timedelta

import pytest

from app.jobs.purge import purge_pending


@pytest.mark.req("AUTH-5")
async def test_stale_pending_registrations_are_purged(auth):
    old = await auth.add_user(email="old@example.org", status="pending", org_id=None,
                              created_at=auth.clock.now() - timedelta(days=31))
    fresh = await auth.add_user(email="new@example.org", status="pending", org_id=None)
    rejected = await auth.add_user(email="no@example.org", status="rejected", org_id=None,
                                   created_at=auth.clock.now() - timedelta(days=90))
    state = auth.app.state  # the app's own client: sessions belong to the client that made them
    assert await purge_pending(state.mongo, state.db, auth.clock, 30) == 1
    remaining = {d["_id"] async for d in auth.db["users"].find({}, {"_id": 1})}
    assert old["_id"] not in remaining
    assert {fresh["_id"], rejected["_id"]} <= remaining
    [event] = await auth.outbox("user.purged")
    assert event.data == {"user_id": old["_id"]}
    assert event.actor.name == "system"
