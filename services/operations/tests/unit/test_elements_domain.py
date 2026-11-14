"""The visit board's rules (TRD §3.2.3; PRD VIS-5, VIS-7; W11-16 to W11-35), with no I/O."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mms_common.errors import Conflict, Forbidden, NotFound, ValidationFailed
from mms_common.ids import new_id

from app.domain.stations.documents import FileFacts
from app.domain.visits import elements as rules

NOW = datetime(2026, 10, 22, 14, 0, tzinfo=UTC)
ALICE, BOB, CAROL = new_id(), new_id(), new_id()  # Alice owns the station, Bob attends, Carol not


def visit(**fields: Any) -> dict[str, Any]:
    return {"_id": new_id(), "request_id": new_id(), "status": "started", "locked": False,
            "staff_ids": [ALICE, BOB], **fields}


STATION = {"station_id": new_id(), "owner_staff_id": ALICE}


def element(kind: str = "note", **fields: Any) -> dict[str, Any]:
    base = rules.new_element(
        element_id=new_id(), visit=visit(), station_id=STATION["station_id"], org_id=new_id(),
        kind=kind, fields=rules.content(kind, title="Mast", description=None, items=None,
                                        priority=None, shared=None, previous=None,
                                        user_id=BOB, now=NOW),
        user_id=BOB, user_name="Bob", device_id=None, now=NOW,
    )
    return {**base, **fields}


def item(text: str = "Clean the funnel", done: bool = False, id_: str | None = None) -> Any:
    return rules.ItemIn(id=id_ or new_id(), text=text, done=done)


def task(items: list[Any], previous: dict[str, Any] | None = None, by: str = BOB,
         now: datetime = NOW) -> dict[str, Any]:
    return rules.content("task", title="Rain gauge", description=None, items=items,
                         priority=None, shared=None, previous=previous, user_id=by, now=now)


def code(caught: pytest.ExceptionInfo[Any]) -> str:
    return str(caught.value.extra["code"])


# --- References ---------------------------------------------------------------------------------


@pytest.mark.req("VIS-5")
def test_an_owner_reference_names_the_element_and_its_section():
    v, s, e = new_id(), new_id(), new_id()
    ref = rules.owner_ref(v, s, e, "before")
    assert ref == f"visit:{v}:station:{s}:element:{e}:before"
    assert rules.parse_owner_ref(ref) == (v, s, e, "before")
    for other in (f"visit:{v}:station:{s}:before", f"visit:{v}:station:{s}:element:{e}:during",
                  f"config:{s}", f"request:{v}"):
        assert rules.parse_owner_ref(other) is None


# --- Who and when -------------------------------------------------------------------------------


@pytest.mark.req("VIS-7")
def test_anyone_attending_adds_and_only_the_author_the_owner_or_an_admin_edits():
    rules.check_can_create(visit(), BOB, False)
    rules.check_can_create(visit(), CAROL, True)  # an admin
    with pytest.raises(Forbidden) as caught:
        rules.check_can_create(visit(), CAROL, False)
    assert code(caught) == "not_attending"

    bobs = element()  # Bob wrote it, Alice owns the station
    for who, admin in ((BOB, False), (ALICE, False), (CAROL, True)):
        rules.check_can_edit(visit(), STATION, bobs, who, admin)
    alices = element(created_by=ALICE)
    with pytest.raises(Forbidden) as caught:
        rules.check_can_edit(visit(), STATION, alices, BOB, False)
    assert code(caught) == "not_editor"


@pytest.mark.req("VIS-7")
@pytest.mark.parametrize(("fields", "expected"), [
    ({"status": "planned"}, "not_started"), ({"status": "cancelled"}, "visit_cancelled"),
    ({"status": "ended", "locked": True}, "locked"),
])
def test_the_board_is_open_from_the_start_until_the_report_locks_it(fields, expected):
    with pytest.raises(Conflict) as caught:
        rules.check_can_create(visit(**fields), BOB, False)
    assert code(caught) == expected
    rules.check_open(visit(status="ended"))  # an ended visit can still be corrected


def test_a_deleted_element_says_so():
    with pytest.raises(Conflict) as caught:
        rules.check_alive(element(deleted_at=NOW))
    assert code(caught) == "element_deleted"
    rules.check_alive(element())


# --- Content ------------------------------------------------------------------------------------


@pytest.mark.req("VIS-5")
def test_each_kind_takes_its_own_fields_and_shares_by_its_default():
    for kind, shared in rules.SHARED_BY_DEFAULT.items():
        fields = rules.content(kind, title="  Guy wires  ", description="  ", items=None,
                               priority=None, shared=None, previous=None, user_id=BOB, now=NOW)
        assert fields["title"] == "Guy wires" and fields["description"] is None
        assert fields["shared"] is shared
        assert fields["priority"] == ("medium" if kind == "recommendation" else None)
    assert rules.SHARED_BY_DEFAULT == {"note": False, "task": True, "recommendation": True,
                                       "config": False}
    shared_note = rules.content("note", title="x", description=None, items=None, priority=None,
                                shared=True, previous=None, user_id=BOB, now=NOW)
    assert shared_note["shared"] is True


@pytest.mark.req("VIS-5")
@pytest.mark.parametrize(("kind", "kw", "expected"), [
    ("note", {"title": "   "}, "title_required"),
    ("note", {"title": "x" * 81}, "too_long"),
    ("note", {"description": "x" * 4001}, "too_long"),
    ("note", {"items": [rules.ItemIn(id=new_id(), text="x", done=False)]}, "items_not_allowed"),
    ("note", {"priority": "high"}, "priority_not_allowed"),
    ("recommendation", {"priority": "urgent"}, "bad_priority"),
    ("task", {"items": [rules.ItemIn(id=new_id(), text="  ", done=False)]}, "item_required"),
    ("task", {"items": [rules.ItemIn(id=new_id(), text="x" * 201, done=False)]}, "too_long"),
])
def test_content_is_bounded(kind, kw, expected):
    args: dict[str, Any] = {"title": "Mast", "description": None, "items": None,
                            "priority": None, "shared": None, **kw}
    with pytest.raises(ValidationFailed) as caught:
        rules.content(kind, **args, previous=None, user_id=BOB, now=NOW)
    assert code(caught) == expected


def test_a_task_has_at_most_fifty_items_with_their_own_ids():
    with pytest.raises(ValidationFailed) as caught:
        task([item() for _ in range(51)])
    assert code(caught) == "too_many_items"
    same = new_id()
    with pytest.raises(ValidationFailed) as caught:
        task([item(id_=same), item(id_=same)])
    assert code(caught) == "duplicate_id"
    assert len(task([item() for _ in range(50)])["items"]) == 50


@pytest.mark.req("VIS-7")
def test_a_task_is_complete_when_every_item_is_ticked_and_who_ticked_it_is_kept():
    a, b = new_id(), new_id()
    empty = task([])
    assert empty["completed_at"] is None and not rules.is_complete(empty["items"])

    half = task([item("Clean", True, a), item("Level", False, b)])
    assert half["completed_at"] is None
    assert half["items"][0]["done_by"] == BOB and half["items"][0]["done_at"] == NOW
    assert half["items"][1]["done_by"] is None

    later = NOW + timedelta(minutes=20)
    done = task([item("Clean", True, a), item("Level", True, b)], previous=half, by=ALICE,
                now=later)
    assert done["completed_at"] == later
    assert done["items"][0]["done_by"] == BOB and done["items"][0]["done_at"] == NOW  # kept
    assert done["items"][1]["done_by"] == ALICE

    again = task([item("Clean", True, a), item("Level", True, b)], previous=done,
                 now=later + timedelta(hours=1))
    assert again["completed_at"] == later  # completion keeps its first time

    added = task([*[item(i["text"], True, i["id"]) for i in done["items"]], item("Photo")],
                 previous=done)
    assert added["completed_at"] is None  # a new item reopens it
    unticked = task([item("Clean", False, a), item("Level", True, b)], previous=done)
    assert unticked["completed_at"] is None and unticked["items"][0]["done_by"] is None


@pytest.mark.req("VIS-7")
def test_a_save_that_says_what_is_saved_is_a_retry():
    saved = element("task", **task([item("Clean", True)]))
    again = task([rules.ItemIn(id=i["id"], text=i["text"], done=i["done"])
                  for i in saved["items"]], previous=saved, now=NOW + timedelta(hours=1))
    assert rules.same_content(saved, again)
    retitled = {**again, "title": "Funnel"}
    assert not rules.same_content(saved, retitled)
    assert rules.changed_fields(saved, retitled) == ["title"]


def test_a_new_element_starts_at_version_one_with_its_sections():
    for kind, sections in rules.SECTIONS.items():
        doc = element(kind)
        assert doc["version"] == doc["revision"] == 1 and doc["deleted_at"] is None
        assert tuple(doc["media"]) == sections
        assert doc["created_by"] == BOB and doc["request_ref"] is None


def test_a_board_has_room_for_two_hundred():
    rules.check_room(199)
    with pytest.raises(Conflict) as caught:
        rules.check_room(200)
    assert code(caught) == "board_full"


# --- Files --------------------------------------------------------------------------------------


def facts(kind: str = "image", **fields: Any) -> FileFacts:
    base: dict[str, Any] = {"owner_ref": "ref", "kind": kind, "status": "processing",
                            "uploaded_by": BOB, "filename": "IMG_1.jpg", "size_bytes": 10,
                            "checksum_sha256": "0" * 64}
    return FileFacts(**{**base, **fields})


@pytest.mark.req("VIS-5")
def test_each_kind_takes_files_in_its_own_sections():
    assert rules.check_section("note", "main") == "main"
    assert rules.check_section("task", "after") == "after"
    for kind, section in (("note", "before"), ("task", "main"), ("config", "main"),
                          ("recommendation", "after")):
        with pytest.raises(ValidationFailed) as caught:
            rules.check_section(kind, section)
        assert code(caught) == "bad_section"


@pytest.mark.req("CFG-4")
def test_config_takes_any_file_and_the_others_take_photos_and_video():
    assert rules.check_file(facts("config", filename="logger.py"), kind="config", owner="ref",
                            user_id=BOB).filename == "logger.py"
    rules.check_file(facts("video"), kind="task", owner="ref", user_id=BOB)
    with pytest.raises(ValidationFailed) as caught:
        rules.check_file(facts("config"), kind="note", owner="ref", user_id=BOB)
    assert code(caught) == "wrong_kind"


@pytest.mark.parametrize(("found", "expected"), [
    (None, "unknown_file"), (facts(owner_ref="other"), "wrong_owner"),
    (facts(uploaded_by=ALICE), "not_yours"), (facts(status="pending"), "file_not_uploaded"),
])
def test_a_file_that_does_not_belong_is_refused(found, expected):
    with pytest.raises(ValidationFailed) as caught:
        rules.check_file(found, kind="note", owner="ref", user_id=BOB)
    assert code(caught) == expected


def test_captions_and_capture_times_are_checked():
    assert rules.check_caption("  North mast ") == "North mast"
    assert rules.check_caption("   ") is None
    with pytest.raises(ValidationFailed):
        rules.check_caption("x" * 301)
    assert rules.check_captured_at(NOW, NOW) == NOW
    with pytest.raises(ValidationFailed):
        rules.check_captured_at(NOW + timedelta(days=2), NOW)


def entry(media_id: str, *, hidden: bool = False, kind: str = "image",
          at: datetime = NOW) -> dict[str, Any]:
    return {"media_id": media_id, "kind": kind, "hidden": hidden, "added_at": at}


def test_files_are_found_on_the_element():
    m1, m2 = new_id(), new_id()
    doc = element("task", media={"before": [entry(m1)], "after": [entry(m2, hidden=True)]})
    assert rules.find_media(doc, m2)[0] == "after"
    assert rules.has_media(doc, m1) and not rules.has_media(doc, new_id())
    assert rules.all_media_ids(doc) == [m1, m2]
    assert rules.shown_media_ids(doc) == [m1]
    with pytest.raises(NotFound):
        rules.find_media(doc, new_id())


# --- What the client sees -----------------------------------------------------------------------


@pytest.mark.req("VIS-11")
def test_a_client_sees_shared_elements_of_an_ended_visit_only():
    shared, private = element(shared=True), element(shared=False)
    assert not rules.visible_to_client(visit(), shared)
    assert rules.visible_to_client(visit(status="ended"), shared)
    assert not rules.visible_to_client(visit(status="ended"), private)
    assert not rules.visible_to_client(visit(status="ended"), {**shared, "deleted_at": NOW})
    assert not rules.visible_to_client(visit(status="cancelled"), shared)


@pytest.mark.req("VIS-11")
def test_after_the_end_a_change_of_sharing_shows_or_withdraws_the_files():
    m1, m2, m3 = new_id(), new_id(), new_id()
    before = element(shared=False, media={"main": [entry(m1), entry(m2, hidden=True)]})
    after = {**before, "shared": True}
    assert rules.sharing_change(visit(), before, after) == ([], [])  # not ended: nothing yet
    ended = visit(status="ended")
    assert rules.sharing_change(ended, before, after) == ([m1], [])
    assert rules.sharing_change(ended, after, before) == ([], [m1])
    assert rules.sharing_change(ended, after, None) == ([], [m1])  # deleted
    grown = {**after, "media": {"main": [entry(m1), entry(m2, hidden=True), entry(m3)]}}
    assert rules.sharing_change(ended, after, grown) == ([m3], [])
    hidden = {**after, "media": {"main": [entry(m1, hidden=True), entry(m2, hidden=True)]}}
    assert rules.sharing_change(ended, after, hidden) == ([], [m1])


@pytest.mark.req("VIS-7")
def test_a_board_event_carries_ids_and_flags_never_text():
    doc = element("recommendation", title="Guy wires corroded", priority="high")
    out = rules.facts(doc)
    assert out == {"station_id": doc["station_id"], "element_id": doc["_id"],
                   "kind": "recommendation", "shared": True, "completed": None,
                   "priority": "high", "element_version": 1}
    assert "Guy wires" not in str(out)
    assert rules.facts(element("task", items=[{"done": True}]))["completed"] is True


def test_a_board_is_summarized_with_its_newest_photo():
    m_old, m_new, m_file = new_id(), new_id(), new_id()
    board = [
        element("note", media={"main": [entry(m_old, at=NOW)]}),
        element("task", items=[{"done": False}], media={
            "before": [entry(m_new, kind="video", at=NOW + timedelta(minutes=5))], "after": []}),
        element("task", items=[{"done": True}]),
        element("config", media={"before": [], "after": [
            entry(m_file, kind="config", at=NOW + timedelta(hours=1))]}),
    ]
    summary = rules.summarize(board)
    assert summary.counts == {"note": 1, "task": 2, "recommendation": 0, "config": 1}
    assert summary.incomplete_tasks == 1
    assert summary.cover == (m_new, "video")  # a logger file is never the cover
    assert rules.summarize([]).cover is None


# --- Config → configuration versions, Recommendation → request -----------------------------------


def config_with(
    *entries: dict[str, Any], made: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return element("config", media={"before": [], "after": list(entries)},
                   config_versions=made or [])


@pytest.mark.req("CFG-4")
def test_a_config_version_holds_the_after_files_that_are_not_photos():
    m1, m2, photo = new_id(), new_id(), new_id()
    doc = config_with(entry(m2, kind="config", at=NOW + timedelta(minutes=1)),
                      entry(photo), entry(m1, kind="config", at=NOW))
    assert [e["media_id"] for e in rules.config_files(doc)] == [m1, m2]
    assert rules.config_files(element("note")) == []


@pytest.mark.req("CFG-4")
def test_a_version_is_due_when_the_after_files_changed():
    m1, m2 = new_id(), new_id()
    assert not rules.config_version_due(config_with())  # nothing to version
    fresh = config_with(entry(m1, kind="config"))
    assert rules.config_version_due(fresh)
    made = config_with(entry(m1, kind="config"),
                       made=[{"id": "v", "version": 5, "media_ids": [m1]}])
    assert not rules.config_version_due(made)
    grown = config_with(entry(m1, kind="config"), entry(m2, kind="config"),
                        made=[{"id": "v", "version": 5, "media_ids": [m1]}])
    assert rules.config_version_due(grown)


def test_versions_after_the_end_need_an_ended_visit_that_is_not_locked():
    rules.check_ended_for_version(visit(status="ended"))
    for fields, expected in (({"status": "started"}, "not_ended"),
                             ({"status": "ended", "locked": True}, "locked")):
        with pytest.raises(Conflict) as caught:
            rules.check_ended_for_version(visit(**fields))
        assert code(caught) == expected


@pytest.mark.req("VIS-7")
def test_a_recommendation_makes_one_request():
    rid = new_id()
    rec = element("recommendation")
    assert rules.check_can_request(rec, rid) is True
    made = {**rec, "request_ref": {"id": rid, "ref": "MR-2026-0051"}}
    assert rules.check_can_request(made, rid) is False  # a retry
    with pytest.raises(Conflict) as caught:
        rules.check_can_request(made, new_id())
    assert code(caught) == "already_requested"
    with pytest.raises(ValidationFailed) as caught:
        rules.check_can_request(element("note"), rid)
    assert code(caught) == "not_recommendation"
    assert rules.REQUEST_PRIORITY == {"low": "low", "medium": "normal", "high": "high"}
