"""The field-test report (`python -m app.cli field-test-report`; W15-5): it reads what the server
holds for a visit, changes nothing, and names what is odd."""

from __future__ import annotations

from mms_common.testing.seed import SEED_USERS

from app.jobs import field_report
from tests.api.test_visit_board import added, two_techs, upload
from tests.api.test_visits import move


async def titled(ops, request: dict, title: str) -> None:
    await ops.db["requests"].update_one({"_id": request["id"]}, {"$set": {"title": title}})


async def test_it_finds_the_visits_by_the_requests_title_and_counts_the_board(ops):
    visit, request, stations = await two_techs(ops)
    await titled(ops, request, "[Field test] Rain gauge check")
    first = await added(ops, "tech1", visit, stations[0], "note")
    await added(ops, "tech1", visit, stations[0], "task")
    await added(ops, "tech1", visit, stations[1], "recommendation")
    media_id = upload(ops, visit, stations[0], first)
    r = await ops.http.post(
        f"/api/v1/visits/{visit['id']}/stations/{stations[0]['id']}/elements/{first['id']}/media",
        json={"media_id": media_id, "section": "main"}, headers=ops.bearer("tech1"))
    assert r.status_code in (200, 201), r.text

    assert await field_report.visit_ids_for(ops.db, "[Field test]") == [visit["id"]]
    assert await field_report.visit_ids_for(ops.db, "[Other]") == []

    text, problems = await field_report.run(ops.db, [visit["id"]])
    assert problems == 0
    assert "started" in text
    assert "elements 3 (deleted 0), files on boards 1" in text
    assert "1 note, 1 task" in text
    assert "1 recommendation" in text
    assert "Check: nothing" in text


async def test_it_does_not_change_anything(ops):
    visit, request, stations = await two_techs(ops)
    await titled(ops, request, "[Field test] x")
    await added(ops, "tech1", visit, stations[0], "note")
    before = [d async for d in ops.db["visit_elements"].find({})]
    await field_report.run(ops.db, [visit["id"]])
    assert [d async for d in ops.db["visit_elements"].find({})] == before


async def test_it_names_a_file_attached_twice_and_an_unanswered_operation(ops):
    visit, _request, stations = await two_techs(ops)
    one = await added(ops, "tech1", visit, stations[0], "note")
    two = await added(ops, "tech1", visit, stations[0], "note")
    # The same file on two elements (it cannot happen through the API; the report must still say so)
    entry = {"media_id": "m-1", "kind": "image", "filename": "a.jpg", "caption": None}
    for element in (one, two):
        await ops.db["visit_elements"].update_one(
            {"_id": element["id"]}, {"$set": {"media": {"main": [entry]}}})
    await ops.db["sync_operations"].insert_one({
        "_id": "op-1", "user_id": SEED_USERS["tech1"].id, "device_id": "0192abcdef0123",
        "type": "element.create", "visit_id": visit["id"], "result": None,
        "applied_at": ops.clock.now(),
    })
    text, problems = await field_report.run(ops.db, [visit["id"]])
    assert problems == 2
    assert "file m-1 is attached 2 times" in text
    assert "operation op-1 (element.create) was claimed and has no answer" in text
    assert "devices: 0192…0123" in text


async def test_an_unknown_visit_is_a_problem(ops):
    text, problems = await field_report.run(ops.db, ["nope"])
    assert "not found" in text
    assert problems == 1


async def test_an_ended_visit_shows_its_end(ops):
    visit, request, stations = await two_techs(ops)
    await titled(ops, request, "[Field test] y")
    for station in stations:
        await move(ops, "tech1", visit["id"], f"stations/{station['id']}/arrive")
    ended = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert ended.status_code == 200, ended.text
    text, _ = await field_report.run(ops.db, [visit["id"]])
    assert " ended " in text
    assert "ended -" not in text
