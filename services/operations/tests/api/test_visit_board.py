"""The visit board over the real app (PRD VIS-5, VIS-7, VIS-11; TRD §3.2.3; W11-16 to W11-35;
rules 2 to 6): who adds and edits, when, idempotent saves and per-element conflicts, tombstones,
files on elements, what the client sees and when, and the owner check media makes."""

from __future__ import annotations

from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from app.domain.visits import elements as rules
from tests.api.test_config_and_owner_check import attachable
from tests.api.test_visits import TECH1, TECH2, a_request, move, plan


async def two_techs(ops, *, start: bool = True):
    """A visit of two stations: tech1 (the lead) owns both, tech2 attends."""
    request, stations = await a_request(ops, staff=("tech1", "tech2"))
    r = await plan(ops, "tech1", request, stations, staff=(TECH1, TECH2))
    assert r.status_code == 201, r.text
    visit = r.json()
    if start:
        started = await move(ops, "tech1", visit["id"], "start")
        assert started.status_code == 200, started.text
        visit = started.json()
    return visit, request, stations


def board(visit, station) -> str:
    return f"/api/v1/visits/{visit['id']}/stations/{station['id']}/elements"


async def add(ops, who: str, visit, station, kind: str = "note", **fields: Any):
    body = {"id": new_id(), "kind": kind, "title": "Guy wires", **fields}
    return await ops.http.post(board(visit, station), json=body, headers=ops.bearer(who))


async def added(ops, who: str, visit, station, kind: str = "note", **fields: Any):
    r = await add(ops, who, visit, station, kind, **fields)
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def put_body(element: dict[str, Any], **changes: Any) -> dict[str, Any]:
    items = [{"id": i["id"], "text": i["text"], "done": i["done"]} for i in element["items"]]
    body = {"title": element["title"], "description": element["description"], "items": items,
            "priority": element["priority"], "shared": element["shared"],
            "base_version": element["version"]}
    return {**body, **changes}


async def save(ops, who: str, visit, station, element, **changes: Any):
    return await ops.http.put(f"{board(visit, station)}/{element['id']}",
                              json=put_body(element, **changes), headers=ops.bearer(who))


async def listed(ops, who: str, visit, station) -> dict[str, Any]:
    r = await ops.http.get(board(visit, station), headers=ops.bearer(who))
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def upload(ops, visit, station, element, section: str = "main", *, by: str = "tech1",
           kind: str = "image", filename: str = "IMG_1.jpg", **kw: Any) -> str:
    ref = rules.owner_ref(visit["id"], station["id"], element["id"], section)
    return ops.media.add(ref, by=by, kind=kind, filename=filename, **kw)


async def attach(ops, who: str, visit, station, element, media_id: str, section="main", **kw):
    return await ops.http.post(f"{board(visit, station)}/{element['id']}/media",
                               json={"media_id": media_id, "section": section, **kw},
                               headers=ops.bearer(who))


async def visibility(ops) -> list[Any]:
    return await ops.outbox("media.visibility_requested")


# --- Adding (VIS-5, VIS-7) ----------------------------------------------------------------------


@pytest.mark.req("VIS-5")
async def test_a_note_goes_on_the_board_with_its_event_and_no_text_travels(ops):
    visit, _, [one, two] = await two_techs(ops)
    r = await add(ops, "tech2", visit, one, title="  Rust on the mast  ",
                  description="Below the wind vane")
    assert r.status_code == 201, r.text
    note = r.json()
    assert note["kind"] == "note" and note["title"] == "Rust on the mast"
    assert note["shared"] is False and note["version"] == 1 and note["can_edit"] is True
    assert note["created_by"] == {"id": TECH2, "name": SEED_USERS["tech2"].name}
    assert note["media"] == {"main": []} and note["complete"] is None
    assert [e["id"] for e in (await listed(ops, "tech1", visit, one))["items"]] == [note["id"]]
    assert (await listed(ops, "tech1", visit, two))["items"] == []

    [event] = await ops.outbox("visit.element_added")
    assert event.data["element_id"] == note["id"] and event.data["kind"] == "note"
    assert event.data["station_id"] == one["id"] and event.data["shared"] is False
    assert event.key == visit["request_id"]
    assert "Rust" not in str(event.data) and "wind vane" not in str(event.data)
    assert event.audit["after"]["title"] == "Rust on the mast"  # the audit chain keeps it


@pytest.mark.req("VIS-5")
async def test_each_kind_starts_with_its_sections_and_default_sharing(ops):
    visit, _, [one, _] = await two_techs(ops)
    shapes = {}
    for kind in rules.KINDS:
        out = await added(ops, "tech1", visit, one, kind)
        shapes[kind] = (sorted(out["media"]), out["shared"], out["priority"])
    assert shapes == {
        "note": (["main"], False, None), "task": (["after", "before"], True, None),
        "recommendation": (["main"], True, "medium"), "config": (["after", "before"], False, None),
    }
    summary = next(s for s in (await move_get(ops, "tech1", visit))["stations"]
                   if s["station_id"] == one["id"])["board"]
    assert summary == {"note": 1, "task": 1, "recommendation": 1, "config": 1,
                       "incomplete_tasks": 1, "cover": None}


async def move_get(ops, who: str, visit) -> dict[str, Any]:
    r = await ops.http.get(f"/api/v1/visits/{visit['id']}", headers=ops.bearer(who))
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


@pytest.mark.req("VIS-7")
async def test_adding_the_same_element_again_changes_nothing_and_another_with_its_id_is_refused(
        ops):
    visit, _, [one, _] = await two_techs(ops)
    body = {"id": new_id(), "kind": "task", "title": "Rain gauge",
            "items": [{"id": new_id(), "text": "Clean the funnel"}]}
    first = await ops.http.post(board(visit, one), json=body, headers=ops.bearer("tech1"))
    again = await ops.http.post(board(visit, one), json=body, headers=ops.bearer("tech1"))
    assert first.status_code == 201 and again.status_code == 200, again.text
    assert again.json() == first.json()
    assert len(await ops.outbox("visit.element_added")) == 1
    other = await ops.http.post(board(visit, one), json={**body, "title": "Something else"},
                                headers=ops.bearer("tech1"))
    assert other.status_code == 409 and other.json()["code"] == "duplicate_id"
    theirs = await ops.http.post(board(visit, one), json=body, headers=ops.bearer("tech2"))
    assert theirs.status_code == 409 and theirs.json()["code"] == "duplicate_id"


@pytest.mark.req("VIS-7")
async def test_people_not_attending_viewers_and_clients_may_not_add(ops):
    request, stations = await a_request(ops, staff=("tech1",))
    visit = (await plan(ops, "tech1", request, stations)).json()
    assert (await move(ops, "tech1", visit["id"], "start")).status_code == 200
    one = stations[0]
    outside = await add(ops, "tech2", visit, one)
    assert outside.status_code == 403 and outside.json()["code"] == "not_attending"
    assert (await add(ops, "viewer", visit, one)).status_code == 403
    assert (await add(ops, "client_a1", visit, one)).status_code == 403
    assert (await add(ops, "admin", visit, one)).status_code == 201  # admins always may
    staff = await listed(ops, "tech2", visit, one)  # staff read every board
    assert len(staff["items"]) == 1 and staff["can_add"] is False
    assert staff["items"][0]["can_edit"] is False
    assert (await listed(ops, "tech1", visit, one))["can_add"] is True


@pytest.mark.req("VIS-7")
@pytest.mark.parametrize(("setup", "expected"), [
    ("planned", "not_started"), ("cancelled", "visit_cancelled"), ("locked", "locked"),
])
async def test_the_board_opens_at_the_start_and_closes_when_the_report_locks(ops, setup, expected):
    visit, _, [one, _] = await two_techs(ops, start=setup == "locked")
    if setup == "cancelled":
        assert (await move(ops, "tech1", visit["id"], "cancel")).status_code == 200
    if setup == "locked":
        await ops.db["site_visits"].update_one({"_id": visit["id"]}, {"$set": {"locked": True}})
    r = await add(ops, "tech1", visit, one)
    assert r.status_code == 409 and r.json()["code"] == expected


async def test_a_station_that_is_not_on_the_visit_has_no_board(ops):
    visit, _, _ = await two_techs(ops)
    assert (await add(ops, "tech1", visit, {"id": new_id()})).status_code == 404
    r = await ops.http.get(board(visit, {"id": new_id()}), headers=ops.bearer("tech1"))
    assert r.status_code == 404


async def test_a_board_holds_up_to_its_limit(ops, monkeypatch):
    monkeypatch.setattr(rules, "MAX_ELEMENTS", 2)
    visit, _, [one, _] = await two_techs(ops)
    await added(ops, "tech1", visit, one)
    await added(ops, "tech1", visit, one)
    full = await add(ops, "tech1", visit, one)
    assert full.status_code == 409 and full.json()["code"] == "board_full"


# --- Saving -------------------------------------------------------------------------------------


@pytest.mark.req("VIS-7")
async def test_ticking_every_item_completes_the_task(ops):
    visit, _, [one, _] = await two_techs(ops)
    a, b = new_id(), new_id()
    task = await added(ops, "tech2", visit, one, "task",
                       items=[{"id": a, "text": "Clean the funnel"}, {"id": b, "text": "Level"}])
    assert task["complete"] is False and task["completed_at"] is None
    half = await save(ops, "tech2", visit, one, task,
                      items=[{"id": a, "text": "Clean the funnel", "done": True},
                             {"id": b, "text": "Level", "done": False}])
    assert half.status_code == 200, half.text
    assert half.json()["version"] == 2 and half.json()["items"][0]["done_by"] == TECH2
    done = await save(ops, "tech1", visit, one, half.json(),  # tech1 owns the station
                      items=[{"id": a, "text": "Clean the funnel", "done": True},
                             {"id": b, "text": "Level", "done": True}])
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["complete"] is True and out["completed_at"] is not None
    assert [i["done_by"] for i in out["items"]] == [TECH2, TECH1]
    events = await ops.outbox("visit.element_updated")
    assert [e.data["completed"] for e in events] == [False, True]
    assert events[-1].data["changed_fields"] == ["items"]
    summary = next(s for s in (await move_get(ops, "tech1", visit))["stations"]
                   if s["station_id"] == one["id"])["board"]
    assert summary["task"] == 1 and summary["incomplete_tasks"] == 0


@pytest.mark.req("VIS-7")
async def test_a_stale_save_is_a_conflict_with_the_saved_copy_and_a_retry_is_not(ops):
    visit, _, [one, _] = await two_techs(ops)
    note = await added(ops, "tech1", visit, one)
    first = await save(ops, "tech1", visit, one, note, title="Guy wires, south")
    assert first.status_code == 200, first.text
    retry = await save(ops, "tech1", visit, one, note, title="Guy wires, south")  # old version
    assert retry.status_code == 200 and retry.json()["version"] == 2
    stale = await save(ops, "tech1", visit, one, note, title="Guy wires, north")
    assert stale.status_code == 409 and stale.json()["code"] == "element_changed"
    assert stale.json()["current"]["title"] == "Guy wires, south"
    assert stale.json()["current"]["version"] == 2
    assert len(await ops.outbox("visit.element_updated")) == 1


@pytest.mark.req("VIS-7")
async def test_only_the_author_the_station_owner_or_an_admin_edits(ops):
    visit, _, [one, _] = await two_techs(ops)
    mine = await added(ops, "tech1", visit, one)  # tech1: the author and the owner
    denied = await save(ops, "tech2", visit, one, mine, title="Mine now")
    assert denied.status_code == 403 and denied.json()["code"] == "not_editor"
    assert (await save(ops, "viewer", visit, one, mine, title="x")).status_code == 403
    by_admin = await save(ops, "admin", visit, one, mine, title="Checked by admin")
    assert by_admin.status_code == 200, by_admin.text


@pytest.mark.req("VIS-7")
async def test_fields_of_another_kind_are_refused(ops):
    visit, _, [one, _] = await two_techs(ops)
    note = await added(ops, "tech1", visit, one)
    r = await save(ops, "tech1", visit, one, note, priority="high")
    assert r.status_code == 422 and r.json()["code"] == "priority_not_allowed"
    bad = await add(ops, "tech1", visit, one, "note", items=[{"id": new_id(), "text": "x"}])
    assert bad.status_code == 422 and bad.json()["code"] == "items_not_allowed"
    assert (await add(ops, "tech1", visit, one, "photo")).status_code == 422


@pytest.mark.req("VIS-7")
async def test_an_ended_visit_can_still_be_corrected_until_it_is_locked(ops):
    visit, _, [one, _] = await two_techs(ops)
    note = await added(ops, "tech1", visit, one)
    assert (await move(ops, "tech1", visit["id"], "end",
                       additional_visit_required=False)).status_code == 200
    fixed = await save(ops, "tech1", visit, one, note, title="Guy wires, both sides")
    assert fixed.status_code == 200, fixed.text
    await ops.db["site_visits"].update_one({"_id": visit["id"]}, {"$set": {"locked": True}})
    locked = await save(ops, "tech1", visit, one, fixed.json(), title="Too late")
    assert locked.status_code == 409 and locked.json()["code"] == "locked"
    assert (await listed(ops, "tech1", visit, one))["items"][0]["can_edit"] is False


# --- Deleting -----------------------------------------------------------------------------------


@pytest.mark.req("VIS-7")
async def test_a_deleted_element_leaves_a_tombstone_that_a_late_save_cannot_undo(ops):
    visit, _, [one, _] = await two_techs(ops)
    note = await added(ops, "tech1", visit, one)
    photo = upload(ops, visit, one, note)
    assert (await attach(ops, "tech1", visit, one, note, photo)).status_code == 200
    path = f"{board(visit, one)}/{note['id']}"
    stale = await ops.http.delete(path, params={"base_version": 9}, headers=ops.bearer("tech1"))
    assert stale.status_code == 409 and stale.json()["code"] == "element_changed"
    gone = await ops.http.delete(path, params={"base_version": 1}, headers=ops.bearer("tech1"))
    assert gone.status_code == 204, gone.text
    assert (await ops.http.get(path, headers=ops.bearer("tech1"))).status_code == 404
    assert (await listed(ops, "tech1", visit, one))["items"] == []

    late = await save(ops, "tech1", visit, one, note, title="Edited offline")
    assert late.status_code == 409 and late.json()["code"] == "element_deleted"
    replay = await ops.http.post(board(visit, one), json={
        "id": note["id"], "kind": "note", "title": note["title"]}, headers=ops.bearer("tech1"))
    assert replay.status_code == 409 and replay.json()["code"] == "element_deleted"
    again = await ops.http.delete(path, params={"base_version": 1}, headers=ops.bearer("tech1"))
    assert again.status_code == 204
    [asked] = await ops.outbox("media.deletion_requested")
    assert asked.data["media_ids"] == [photo]
    assert len(await ops.outbox("visit.element_deleted")) == 1


async def test_only_an_editor_deletes(ops):
    visit, _, [one, _] = await two_techs(ops)
    note = await added(ops, "tech1", visit, one)
    r = await ops.http.delete(f"{board(visit, one)}/{note['id']}", params={"base_version": 1},
                              headers=ops.bearer("tech2"))
    assert r.status_code == 403 and r.json()["code"] == "not_editor"


# --- Files (W11-27) -----------------------------------------------------------------------------


@pytest.mark.req("VIS-5")
async def test_a_task_takes_before_and_after_photos_and_a_note_takes_its_own(ops):
    visit, _, [one, _] = await two_techs(ops)
    task = await added(ops, "tech1", visit, one, "task")
    before = upload(ops, visit, one, task, "before")
    after = upload(ops, visit, one, task, "after", kind="video", filename="walk.mp4")
    r = await attach(ops, "tech1", visit, one, task, before, "before", caption=" Funnel ")
    assert r.status_code == 200, r.text
    r = await attach(ops, "tech1", visit, one, task, after, "after")
    assert r.status_code == 200, r.text
    out = r.json()
    assert [m["media_id"] for m in out["media"]["before"]] == [before]
    assert out["media"]["before"][0]["caption"] == "Funnel"
    assert out["media"]["after"][0]["kind"] == "video"
    assert out["version"] == 1  # files never make the editor's next save stale
    retry = await attach(ops, "tech1", visit, one, task, before, "before")
    assert retry.status_code == 200 and len(retry.json()["media"]["before"]) == 1
    changes = await ops.outbox("visit.media_changed")
    assert [(e.data["element_id"], e.data["section"], e.data["change"]) for e in changes] == [
        (task["id"], "before", "added"), (task["id"], "after", "added")]
    assert await visibility(ops) == []  # staff-only until the visit ends (ADR-19)

    note = await added(ops, "tech1", visit, one)
    wrong = await attach(ops, "tech1", visit, one, note, upload(ops, visit, one, note, "before"),
                         "before")
    assert wrong.status_code == 422 and wrong.json()["code"] == "bad_section"


@pytest.mark.req("CFG-4")
async def test_config_takes_any_file_and_a_note_only_photos_and_video(ops):
    visit, _, [one, _] = await two_techs(ops)
    config = await added(ops, "tech1", visit, one, "config")
    program = upload(ops, visit, one, config, "after", kind="config", filename="CR1000.py")
    r = await attach(ops, "tech1", visit, one, config, program, "after")
    assert r.status_code == 200, r.text
    assert r.json()["media"]["after"][0]["filename"] == "CR1000.py"
    note = await added(ops, "tech1", visit, one)
    refused = await attach(ops, "tech1", visit, one, note,
                           upload(ops, visit, one, note, kind="config", filename="a.py"))
    assert refused.status_code == 422 and refused.json()["code"] == "wrong_kind"


@pytest.mark.req("VIS-5")
@pytest.mark.parametrize(("case", "expected"), [
    ("elsewhere", "wrong_owner"), ("someone_else", "not_yours"), ("unknown", "unknown_file"),
    ("unfinished", "file_not_uploaded"),
])
async def test_a_file_that_does_not_belong_is_refused(ops, case, expected):
    visit, _, [one, two] = await two_techs(ops)
    note = await added(ops, "tech1", visit, one)
    media_id = {
        "elsewhere": lambda: ops.media.add(rules.owner_ref(visit["id"], two["id"], note["id"],
                                                           "main"), kind="image"),
        "someone_else": lambda: upload(ops, visit, one, note, by="tech2"),
        "unknown": new_id,
        "unfinished": lambda: upload(ops, visit, one, note, status="pending"),
    }[case]()
    r = await attach(ops, "tech1", visit, one, note, media_id)
    assert r.status_code == 422 and r.json()["code"] == expected, r.text


@pytest.mark.req("VIS-5")
async def test_files_are_captioned_hidden_and_removed_by_an_editor(ops):
    visit, _, [one, _] = await two_techs(ops)
    note = await added(ops, "tech1", visit, one)
    photo = upload(ops, visit, one, note)
    assert (await attach(ops, "tech1", visit, one, note, photo)).status_code == 200
    path = f"{board(visit, one)}/{note['id']}/media/{photo}"
    other = await ops.http.patch(path, json={"caption": "x"}, headers=ops.bearer("tech2"))
    assert other.status_code == 403 and other.json()["code"] == "not_editor"
    r = await ops.http.patch(path, json={"caption": "North mast", "hidden": True},
                             headers=ops.bearer("tech1"))
    assert r.status_code == 200, r.text
    assert r.json()["media"]["main"][0]["caption"] == "North mast"
    assert r.json()["media"]["main"][0]["hidden"] is True
    removed = await ops.http.delete(path, headers=ops.bearer("tech1"))
    assert removed.status_code == 200 and removed.json()["media"]["main"] == []
    [asked] = await ops.outbox("media.deletion_requested")
    assert asked.data["media_ids"] == [photo] and asked.data["reason"] == "removed_from_visit"
    assert [e.data["change"] for e in await ops.outbox("visit.media_changed")] == [
        "added", "captioned", "hidden", "removed"]
    assert (await ops.http.delete(path, headers=ops.bearer("tech1"))).status_code == 404


# --- What the client sees (W11-28) --------------------------------------------------------------


@pytest.mark.req("VIS-11")
async def test_the_client_sees_shared_elements_once_the_visit_ends_and_their_files_are_shared(ops):
    visit, _, [one, _] = await two_techs(ops)
    task = await added(ops, "tech1", visit, one, "task")  # shared by default
    note = await added(ops, "tech1", visit, one, "note")  # staff-only by default
    shown = upload(ops, visit, one, task, "before")
    hidden = upload(ops, visit, one, task, "after")
    private = upload(ops, visit, one, note)
    for element, media_id, section in ((task, shown, "before"), (task, hidden, "after"),
                                       (note, private, "main")):
        assert (await attach(ops, "tech1", visit, one, element, media_id,
                             section)).status_code == 200
    r = await ops.http.patch(f"{board(visit, one)}/{task['id']}/media/{hidden}",
                             json={"hidden": True}, headers=ops.bearer("tech1"))
    assert r.status_code == 200, r.text

    before_end = await listed(ops, "client_a1", visit, one)
    assert before_end["items"] == [] and before_end["can_add"] is False
    task_path = f"{board(visit, one)}/{task['id']}"
    assert (await ops.http.get(task_path, headers=ops.bearer("client_a1"))).status_code == 404
    assert await visibility(ops) == []

    ended = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert ended.status_code == 200, ended.text
    [event] = await visibility(ops)
    assert event.data["visibility"] == "org" and event.data["media_ids"] == [shown]
    assert event.org_id == ORG_A
    assert event.data["visibility_version"] > ended.json()["version"] - 1

    seen = await listed(ops, "client_a1", visit, one)
    assert [e["id"] for e in seen["items"]] == [task["id"]]
    assert seen["items"][0]["media"] == {"before": [seen["items"][0]["media"]["before"][0]],
                                         "after": []}  # the hidden file is left out
    assert seen["items"][0]["can_edit"] is False
    note_path = f"{board(visit, one)}/{note['id']}"
    assert (await ops.http.get(note_path, headers=ops.bearer("client_a1"))).status_code == 404
    assert (await ops.http.get(task_path, headers=ops.bearer("client_b1"))).status_code == 404
    client_board = next(s for s in (await move_get(ops, "client_a1", visit))["stations"]
                        if s["station_id"] == one["id"])["board"]
    assert client_board["note"] == 0 and client_board["task"] == 1


@pytest.mark.req("VIS-11")
async def test_after_the_end_sharing_and_new_files_reach_the_client_in_order(ops):
    visit, _, [one, _] = await two_techs(ops)
    note = await added(ops, "tech1", visit, one)
    photo = upload(ops, visit, one, note)
    assert (await attach(ops, "tech1", visit, one, note, photo)).status_code == 200
    assert (await move(ops, "tech1", visit["id"], "end",
                       additional_visit_required=False)).status_code == 200
    assert await visibility(ops) == []  # nothing shared on the board yet

    shared = await save(ops, "tech1", visit, one, note, shared=True)
    assert shared.status_code == 200, shared.text
    late = upload(ops, visit, one, note)
    assert (await attach(ops, "tech1", visit, one, note, late)).status_code == 200
    unshared = await save(ops, "tech1", visit, one, shared.json(), shared=False)
    assert unshared.status_code == 200, unshared.text
    events = await visibility(ops)
    assert [(e.data["visibility"], e.data["media_ids"]) for e in events] == [
        ("org", [photo]), ("org", [late]), ("staff", sorted([photo, late]))]
    versions = [e.data["visibility_version"] for e in events]
    assert versions == sorted(versions) and len(set(versions)) == 3


# --- The owner check media makes ----------------------------------------------------------------


@pytest.mark.req("VIS-5")
async def test_media_may_upload_for_an_element_even_before_it_exists(ops):
    visit, _, [one, _] = await two_techs(ops)
    future = rules.owner_ref(visit["id"], one["id"], new_id(), "before")
    for who in ("tech1", "tech2", "admin"):  # a phone uploads while the create op waits
        r = await attachable(ops, future, who)
        assert r.status_code == 200 and r.json() == {"org_id": ORG_A}, (who, r.text)
    assert (await attachable(ops, future, "viewer")).status_code == 403
    assert (await attachable(ops, future, "client_a1")).status_code == 404

    mine = await added(ops, "tech1", visit, one, "task")
    ref = rules.owner_ref(visit["id"], one["id"], mine["id"], "after")
    assert (await attachable(ops, ref, "tech1")).status_code == 200
    assert (await attachable(ops, ref, "tech2")).status_code == 403  # not an editor of it
    wrong = rules.owner_ref(visit["id"], one["id"], mine["id"], "main")
    assert (await attachable(ops, wrong, "tech1")).status_code == 404
    elsewhere = rules.owner_ref(visit["id"], new_id(), mine["id"], "after")
    assert (await attachable(ops, elsewhere, "tech1")).status_code == 404
    old_phase = f"visit:{visit['id']}:station:{one['id']}:before"
    assert (await attachable(ops, old_phase, "tech1")).status_code == 404
