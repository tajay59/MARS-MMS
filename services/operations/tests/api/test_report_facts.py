"""The read the report service makes for a draft (TRD 11.2 step 1, W16-2): the visit, its request,
its stations and their boards with the text events never carry (rule 1)."""

from __future__ import annotations

from datetime import datetime

from mms_common.ids import new_id

from tests.api.test_visit_board import added, attach, two_techs, upload
from tests.api.test_visits import move

NOWHERE = "01900000-0000-7000-8000-0000000000ee"


async def facts(ops, visit_id: str, service: str = "report"):
    return await ops.http.get(f"/internal/visits/{visit_id}/report-facts",
                              headers=ops.service(service))


async def test_the_facts_hold_the_visit_the_request_and_each_boards_content(ops):
    visit, request, stations = await two_techs(ops)
    note = await added(ops, "tech1", visit, stations[0], "note", description="Mast is straight")
    task = await added(ops, "tech1", visit, stations[0], "task",
                       items=[{"id": new_id(), "text": "Clean the screen", "done": True},
                              {"id": new_id(), "text": "Tighten the clamp", "done": False}])
    await added(ops, "tech1", visit, stations[1], "recommendation", priority="high")
    media_id = upload(ops, visit, stations[0], note, "main", filename="IMG_7.jpg")
    assert (await attach(ops, "tech1", visit, stations[0], note, media_id)).status_code in (200, 201)

    r = await facts(ops, visit["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["facts_version"] == 1
    v = body["visit"]
    assert v["id"] == visit["id"] and v["ref"] == visit["ref"] and v["status"] == "started"
    assert v["request_ref"] == request["ref"] and v["request_title"] == request["title"]
    assert v["lead_staff_id"] and [p["name"] for p in v["staff"]]
    assert [s["station_id"] for s in body["stations"]] == [s["id"] for s in stations]
    first, second = body["stations"]
    assert first["code"] == stations[0]["code"] and first["time_zone"]
    assert first["owner"]["id"] == v["lead_staff_id"] and first["owner"]["name"]
    by_title = {e["id"]: e for e in first["elements"]}
    assert by_title[note["id"]]["description"] == "Mast is straight"
    assert by_title[note["id"]]["media"]["main"][0]["media_id"] == media_id
    assert by_title[note["id"]]["media"]["main"][0]["filename"] == "IMG_7.jpg"
    assert [i["text"] for i in by_title[task["id"]]["items"]] == [
        "Clean the screen", "Tighten the clamp"]
    assert by_title[task["id"]]["items"][0]["done"] is True
    assert [e["kind"] for e in second["elements"]] == ["recommendation"]
    assert second["elements"][0]["priority"] == "high"
    datetime.fromisoformat(first["elements"][0]["created_at"])


async def test_a_deleted_element_and_a_hidden_file_are_left_out(ops):
    visit, _request, stations = await two_techs(ops)
    gone = await added(ops, "tech1", visit, stations[0], "note", title="Gone")
    kept = await added(ops, "tech1", visit, stations[0], "note", title="Kept")
    r = await ops.http.delete(
        f"/api/v1/visits/{visit['id']}/stations/{stations[0]['id']}/elements/{gone['id']}"
        f"?base_version={gone['version']}", headers=ops.bearer("tech1"))
    assert r.status_code in (200, 204), r.text
    elements = (await facts(ops, visit["id"])).json()["stations"][0]["elements"]
    assert [e["id"] for e in elements] == [kept["id"]]


async def test_an_ended_visit_carries_its_end(ops):
    visit, _request, stations = await two_techs(ops)
    for station in stations:
        await move(ops, "tech1", visit["id"], f"stations/{station['id']}/arrive")
    r = await move(ops, "tech1", visit["id"], "end", additional_visit_required=True,
                   follow_up_notes="Bring a new battery")
    assert r.status_code == 200, r.text
    v = (await facts(ops, visit["id"])).json()["visit"]
    assert v["status"] == "ended" and v["ended_at"] and v["started_at"]
    assert v["additional_visit_required"] is True
    assert v["follow_up_notes"] == "Bring a new battery"


async def test_only_the_report_service_may_ask_and_an_unknown_visit_is_404(ops):
    visit, _request, _stations = await two_techs(ops)
    for who in ("media", "platform", "operations"):
        assert (await facts(ops, visit["id"], who)).status_code in (401, 403)
    assert (await ops.http.get(f"/internal/visits/{visit['id']}/report-facts",
                               headers=ops.bearer("admin"))).status_code in (401, 403)
    assert (await facts(ops, NOWHERE)).status_code == 404
