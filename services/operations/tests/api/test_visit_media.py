"""Photos and video on a visit, W11 slice 4 (PRD VIS-5, VIS-10; ADR-18, ADR-19; rules 2 to 6), over
the real app: who may add, caption, hide and remove, when, what the end of the visit shares with the
client, and the owner check media makes for `visit:` references."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from app.domain.visits import media as rules
from tests.api.test_config_and_owner_check import attachable
from tests.api.test_visits import TECH1, TECH2, a_request, move, plan

PHASES = ("before", "during", "after")


async def two_techs(ops, *, start: bool = True):
    """A visit of two stations, tech1 (the lead, who owns both) and tech2 attending."""
    request, stations = await a_request(ops, staff=("tech1", "tech2"))
    r = await plan(ops, "tech1", request, stations, staff=(TECH1, TECH2))
    assert r.status_code == 201, r.text
    visit = r.json()
    if start:
        started = await move(ops, "tech1", visit["id"], "start")
        assert started.status_code == 200, started.text
        visit = started.json()
    return visit, request, stations


def ref(visit: dict[str, Any], station: dict[str, Any], phase: str = "before") -> str:
    return rules.owner_ref(visit["id"], station["id"], phase)


def photo(ops, visit, station, phase="before", *, by="tech1", **kw: Any) -> str:
    return ops.media.add(ref(visit, station, phase), by=by, kind="image", filename="IMG_1.jpg",
                         **kw)


async def attach(ops, who: str, visit, station, media_id: str, phase="before", **extra: Any):
    return await ops.http.post(
        f"/api/v1/visits/{visit['id']}/stations/{station['id']}/media",
        json={"media_id": media_id, "phase": phase, **extra}, headers=ops.bearer(who),
    )


def path(visit, station, media_id: str) -> str:
    return f"/api/v1/visits/{visit['id']}/stations/{station['id']}/media/{media_id}"


def media_of(visit: dict[str, Any], station_id: str) -> list[dict[str, Any]]:
    found = next(s for s in visit["stations"] if s["station_id"] == station_id)
    items: list[dict[str, Any]] = found["media"]
    return items


async def read(ops, who: str, visit_id: str) -> dict[str, Any]:
    r = await ops.http.get(f"/api/v1/visits/{visit_id}", headers=ops.bearer(who))
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


async def visibility(ops) -> list[Any]:
    return await ops.outbox("media.visibility_requested")


# --- Adding (VIS-5) -----------------------------------------------------------------------------


@pytest.mark.req("VIS-5")
async def test_a_photo_goes_on_a_station_and_stays_staff_only_while_the_visit_is_under_way(ops):
    visit, _, [one, _two] = await two_techs(ops)
    media_id = photo(ops, visit, one)
    r = await attach(ops, "tech1", visit, one, media_id, caption="  North mast, from the gate ",
                     captured_at=(ops.clock.now() - timedelta(minutes=5)).isoformat())
    assert r.status_code == 200, r.text
    [item] = media_of(r.json(), one["id"])
    assert item["media_id"] == media_id and item["phase"] == "before" and item["kind"] == "image"
    assert item["caption"] == "North mast, from the gate" and item["hidden"] is False
    assert item["added_by"] == {"id": TECH1, "name": SEED_USERS["tech1"].name}
    assert item["filename"] == "IMG_1.jpg" and item["captured_at"] is not None
    assert media_of(r.json(), _two["id"]) == []
    assert await visibility(ops) == []  # staff-only until the visit ends (ADR-19)
    [event] = await ops.outbox("visit.media_changed")
    assert event.data["change"] == "added" and event.data["media_id"] == media_id
    assert event.data["station_id"] == one["id"] and event.data["phase"] == "before"
    text = event.model_dump_json()
    assert "IMG_1.jpg" not in text and "North mast" not in text


@pytest.mark.req("VIS-5")
async def test_every_phase_takes_photos_and_a_video(ops):
    visit, _, [one, _] = await two_techs(ops)
    for phase in PHASES:
        r = await attach(ops, "tech1", visit, one, photo(ops, visit, one, phase), phase)
        assert r.status_code == 200, r.text
    clip = ops.media.add(ref(visit, one, "during"), kind="video", filename="walk.mp4")
    r = await attach(ops, "tech1", visit, one, clip, "during")
    assert r.status_code == 200, r.text
    assert [i["phase"] for i in media_of(r.json(), one["id"])] == [*PHASES, "during"]
    assert media_of(r.json(), one["id"])[-1]["kind"] == "video"


@pytest.mark.req("VIS-5")
async def test_adding_the_same_file_again_changes_nothing(ops):
    visit, _, [one, _] = await two_techs(ops)
    media_id = photo(ops, visit, one)
    first = await attach(ops, "tech1", visit, one, media_id)
    again = await attach(ops, "tech1", visit, one, media_id, caption="Changed my mind")
    assert first.status_code == again.status_code == 200
    assert len(media_of(again.json(), one["id"])) == 1
    assert media_of(again.json(), one["id"])[0]["caption"] is None
    assert len(await ops.outbox("visit.media_changed")) == 1


@pytest.mark.req("VIS-5")
async def test_anyone_attending_adds_to_any_station_not_just_the_owner(ops):
    visit, _, [one, _] = await two_techs(ops)
    media_id = photo(ops, visit, one, by="tech2")
    r = await attach(ops, "tech2", visit, one, media_id)  # tech1 owns the station
    assert r.status_code == 200, r.text
    assert media_of(r.json(), one["id"])[0]["added_by"]["id"] == TECH2


@pytest.mark.req("VIS-5")
async def test_staff_not_on_the_visit_and_viewers_may_not_add(ops):
    request, stations = await a_request(ops, staff=("tech1",))
    visit = (await plan(ops, "tech1", request, stations)).json()
    assert (await move(ops, "tech1", visit["id"], "start")).status_code == 200
    one = stations[0]
    mine = photo(ops, visit, one, by="tech2")
    outside = await attach(ops, "tech2", visit, one, mine)
    assert outside.status_code == 403 and outside.json()["code"] == "not_attending"
    assert (await attach(ops, "viewer", visit, one, mine)).status_code == 403
    assert (await attach(ops, "client_a1", visit, one, mine)).status_code == 403
    admin = photo(ops, visit, one, by="admin")
    assert (await attach(ops, "admin", visit, one, admin)).status_code == 200  # admins always may


@pytest.mark.req("VIS-5")
async def test_a_station_that_is_not_on_the_visit_is_not_found(ops):
    visit, _, [one, _] = await two_techs(ops)
    elsewhere = {"id": new_id()}
    r = await attach(ops, "tech1", visit, elsewhere, photo(ops, visit, one))
    assert r.status_code == 404


@pytest.mark.req("VIS-5")
@pytest.mark.parametrize(("case", "code"), [
    ("elsewhere", "wrong_owner"), ("someone_else", "not_yours"), ("pdf", "wrong_kind"),
    ("unknown", "unknown_file"), ("unfinished", "file_not_uploaded"),
])
async def test_a_file_that_does_not_belong_is_refused_with_a_reason(ops, case, code):
    visit, _, [one, two] = await two_techs(ops)
    media_id = {
        "elsewhere": lambda: photo(ops, visit, two),  # uploaded for the other station
        "someone_else": lambda: photo(ops, visit, one, by="tech2"),
        "pdf": lambda: ops.media.add(ref(visit, one), kind="pdf", filename="a.pdf"),
        "unknown": lambda: new_id(),
        "unfinished": lambda: photo(ops, visit, one, status="pending"),
    }[case]()
    r = await attach(ops, "tech1", visit, one, media_id)
    assert r.status_code == 422 and r.json()["code"] == code, r.text
    assert media_of(await read(ops, "tech1", visit["id"]), one["id"]) == []
    assert await ops.outbox("visit.media_changed") == []


@pytest.mark.req("VIS-5")
async def test_a_file_still_being_processed_can_be_added(ops):
    visit, _, [one, _] = await two_techs(ops)
    r = await attach(ops, "tech1", visit, one, photo(ops, visit, one, status="processing"))
    assert r.status_code == 200, r.text


@pytest.mark.req("VIS-5")
async def test_the_phase_the_caption_and_the_time_are_checked(ops):
    visit, _, [one, _] = await two_techs(ops)
    media_id = photo(ops, visit, one)
    assert (await attach(ops, "tech1", visit, one, media_id, phase="later")).status_code == 422
    long = await attach(ops, "tech1", visit, one, media_id, caption="x" * 301)
    assert long.status_code == 422 and long.json()["code"] == "caption_too_long"
    future = await attach(ops, "tech1", visit, one, media_id,
                          captured_at=(ops.clock.now() + timedelta(days=3)).isoformat())
    assert future.status_code == 422 and future.json()["code"] == "captured_in_future"
    blank = await attach(ops, "tech1", visit, one, media_id, caption="   ")
    assert blank.status_code == 200 and media_of(blank.json(), one["id"])[0]["caption"] is None


@pytest.mark.req("VIS-5")
async def test_media_waits_for_the_visit_to_start_and_stops_when_it_is_locked(ops):
    visit, _, [one, _] = await two_techs(ops, start=False)
    media_id = photo(ops, visit, one)
    planned = await attach(ops, "tech1", visit, one, media_id)
    assert planned.status_code == 409 and planned.json()["code"] == "not_started"

    assert (await move(ops, "tech1", visit["id"], "start")).status_code == 200
    assert (await attach(ops, "tech1", visit, one, media_id)).status_code == 200
    await ops.db["site_visits"].update_one({"_id": visit["id"]}, {"$set": {"locked": True}})
    locked = await attach(ops, "tech1", visit, one, photo(ops, visit, one))
    assert locked.status_code == 409 and locked.json()["code"] == "locked"



@pytest.mark.req("VIS-5")
async def test_a_cancelled_visit_takes_no_media(ops):
    visit, _, [one, _] = await two_techs(ops, start=False)
    cancelled = await move(ops, "tech1", visit["id"], "cancel")
    assert cancelled.status_code == 200, cancelled.text
    r = await attach(ops, "tech1", visit, one, photo(ops, visit, one))
    assert r.status_code == 409 and r.json()["code"] == "visit_cancelled"


# --- Sharing with the client (decision W11-13) ---------------------------------------------------


@pytest.mark.req("VIS-10")
async def test_the_end_of_the_visit_shows_its_media_to_the_client_except_what_was_hidden(ops):
    visit, _, [one, two] = await two_techs(ops)
    shown = [photo(ops, visit, one, p) for p in PHASES]
    on_two = photo(ops, visit, two, "after")
    hidden = photo(ops, visit, one, "during")
    for station, media_id, phase in [(one, shown[0], "before"), (one, shown[1], "during"),
                                     (one, shown[2], "after"), (two, on_two, "after"),
                                     (one, hidden, "during")]:
        assert (await attach(ops, "tech1", visit, station, media_id, phase)).status_code == 200
    r = await ops.http.patch(path(visit, one, hidden), json={"hidden": True},
                             headers=ops.bearer("tech1"))
    assert r.status_code == 200, r.text
    assert await visibility(ops) == []  # nothing is shared while the visit is under way

    ended = await move(ops, "tech1", visit["id"], "end", additional_visit_required=False)
    assert ended.status_code == 200, ended.text
    [event] = await visibility(ops)
    assert event.data["visibility"] == "org"
    assert sorted(event.data["media_ids"]) == sorted([*shown, on_two])
    assert hidden not in event.data["media_ids"]
    assert event.org_id == ORG_A
    assert event.data["visibility_version"] == ended.json()["version"]


@pytest.mark.req("VIS-10")
async def test_media_added_after_the_end_is_shown_at_once_and_a_hidden_one_is_withdrawn(ops):
    visit, _, [one, _] = await two_techs(ops)
    assert (await move(ops, "tech1", visit["id"], "end",
                       additional_visit_required=False)).status_code == 200
    assert await visibility(ops) == []  # no media, nothing to share
    late = photo(ops, visit, one, "after")
    added = await attach(ops, "tech1", visit, one, late, "after")
    assert added.status_code == 200, added.text
    [shown] = await visibility(ops)
    assert shown.data["media_ids"] == [late] and shown.data["visibility"] == "org"
    assert shown.data["visibility_version"] == added.json()["version"]

    hid = await ops.http.patch(path(visit, one, late), json={"hidden": True},
                               headers=ops.bearer("tech2"))  # anyone attending may hide
    assert hid.status_code == 200, hid.text
    assert media_of(hid.json(), one["id"])[0]["hidden"] is True
    [_, withdrawn] = await visibility(ops)
    assert withdrawn.data["visibility"] == "staff" and withdrawn.data["media_ids"] == [late]
    assert withdrawn.data["visibility_version"] == hid.json()["version"] > shown.data[
        "visibility_version"]

    again = await ops.http.patch(path(visit, one, late), json={"hidden": False},
                                 headers=ops.bearer("admin"))
    assert again.status_code == 200, again.text
    last = (await visibility(ops))[-1]
    assert last.data["visibility"] == "org"
    assert last.data["visibility_version"] > withdrawn.data["visibility_version"]
    changes = [e.data["change"] for e in await ops.outbox("visit.media_changed")]
    assert changes == ["added", "hidden", "shown"]


@pytest.mark.req("VIS-10")
async def test_a_client_sees_no_media_on_the_visit_yet(ops):
    visit, _, [one, _] = await two_techs(ops)
    assert (await attach(ops, "tech1", visit, one, photo(ops, visit, one))).status_code == 200
    assert (await move(ops, "tech1", visit["id"], "end",
                       additional_visit_required=False)).status_code == 200
    seen = await read(ops, "client_a1", visit["id"])
    assert all(s["media"] == [] for s in seen["stations"])  # the client's view is W12
    staff = await read(ops, "tech1", visit["id"])
    assert len(media_of(staff, one["id"])) == 1


# --- Captions and hiding ------------------------------------------------------------------------


@pytest.mark.req("VIS-5")
async def test_a_caption_is_set_and_cleared_by_anyone_attending(ops):
    visit, _, [one, _] = await two_techs(ops)
    media_id = photo(ops, visit, one)
    assert (await attach(ops, "tech1", visit, one, media_id)).status_code == 200
    r = await ops.http.patch(path(visit, one, media_id), json={"caption": "Guy wire, south"},
                             headers=ops.bearer("tech2"))
    assert r.status_code == 200, r.text
    assert media_of(r.json(), one["id"])[0]["caption"] == "Guy wire, south"
    same = await ops.http.patch(path(visit, one, media_id), json={"caption": "Guy wire, south"},
                                headers=ops.bearer("tech1"))
    assert same.status_code == 200 and len(await ops.outbox("visit.media_changed")) == 2
    cleared = await ops.http.patch(path(visit, one, media_id), json={"caption": None},
                                   headers=ops.bearer("tech1"))
    assert media_of(cleared.json(), one["id"])[0]["caption"] is None
    assert [e.data["change"] for e in await ops.outbox("visit.media_changed")] == [
        "added", "captioned", "captioned"]
    assert await visibility(ops) == []  # a caption shares nothing


@pytest.mark.req("VIS-5")
async def test_changes_to_an_item_that_is_not_there_or_a_visit_not_attended_are_refused(ops):
    visit, _, [one, _] = await two_techs(ops)
    gone = await ops.http.patch(path(visit, one, new_id()), json={"caption": "x"},
                                headers=ops.bearer("tech1"))
    assert gone.status_code == 404
    bad = await ops.http.patch(path(visit, one, new_id()), json={"colour": "red"},
                               headers=ops.bearer("tech1"))
    assert bad.status_code == 422
    nothing = await ops.http.patch(path(visit, one, photo(ops, visit, one)), json={},
                                   headers=ops.bearer("tech1"))
    assert nothing.status_code == 404  # not attached yet


# --- Removing -----------------------------------------------------------------------------------


@pytest.mark.req("VIS-5")
async def test_the_person_who_added_a_photo_removes_it_and_the_file_is_deleted(ops):
    visit, _, [one, _] = await two_techs(ops)
    mine = photo(ops, visit, one)
    theirs = photo(ops, visit, one, by="tech2")
    assert (await attach(ops, "tech1", visit, one, mine)).status_code == 200
    assert (await attach(ops, "tech2", visit, one, theirs)).status_code == 200

    denied = await ops.http.delete(path(visit, one, theirs), headers=ops.bearer("tech1"))
    assert denied.status_code == 403 and denied.json()["code"] == "not_uploader"
    r = await ops.http.delete(path(visit, one, mine), headers=ops.bearer("tech1"))
    assert r.status_code == 200, r.text
    assert [i["media_id"] for i in media_of(r.json(), one["id"])] == [theirs]
    [asked] = await ops.outbox("media.deletion_requested")
    assert asked.data["media_ids"] == [mine] and asked.data["reason"] == "removed_from_visit"
    assert [e.data["change"] for e in await ops.outbox("visit.media_changed")][-1] == "removed"

    again = await ops.http.delete(path(visit, one, mine), headers=ops.bearer("tech1"))
    assert again.status_code == 404  # gone
    assert len(await ops.outbox("media.deletion_requested")) == 1
    by_admin = await ops.http.delete(path(visit, one, theirs), headers=ops.bearer("admin"))
    assert by_admin.status_code == 200 and media_of(by_admin.json(), one["id"]) == []


@pytest.mark.req("VIS-5")
async def test_removing_stops_when_the_report_locks_the_visit(ops):
    visit, _, [one, _] = await two_techs(ops)
    media_id = photo(ops, visit, one)
    assert (await attach(ops, "tech1", visit, one, media_id)).status_code == 200
    await ops.db["site_visits"].update_one({"_id": visit["id"]}, {"$set": {"locked": True}})
    r = await ops.http.delete(path(visit, one, media_id), headers=ops.bearer("tech1"))
    assert r.status_code == 409 and r.json()["code"] == "locked"
    assert await ops.outbox("media.deletion_requested") == []
    assert len(media_of(await read(ops, "tech1", visit["id"]), one["id"])) == 1


# --- The owner check media makes ----------------------------------------------------------------


@pytest.mark.req("VIS-5")
async def test_media_may_upload_for_a_visit_to_those_attending_and_the_file_takes_its_org(ops):
    request, stations = await a_request(ops, staff=("tech1",))
    visit = (await plan(ops, "tech1", request, stations)).json()
    one = stations[0]
    owner = rules.owner_ref(visit["id"], one["id"], "during")
    for who in ("tech1", "admin"):
        r = await attachable(ops, owner, who)
        assert r.status_code == 200 and r.json() == {"org_id": ORG_A}, (who, r.text)
    assert (await attachable(ops, owner, "tech2")).status_code == 403  # not attending
    assert (await attachable(ops, owner, "viewer")).status_code == 403
    assert (await attachable(ops, owner, "client_a1")).status_code == 404  # no client uploads
    assert (await attachable(ops, owner, "tech1", service="report")).status_code == 403


@pytest.mark.req("VIS-5")
async def test_the_owner_check_does_not_know_a_visit_or_station_that_is_not_there(ops):
    request, stations = await a_request(ops, staff=("tech1",))
    visit = (await plan(ops, "tech1", request, stations)).json()
    assert (await attachable(ops, rules.owner_ref(new_id(), stations[0]["id"], "before")
                             )).status_code == 404
    assert (await attachable(ops, rules.owner_ref(visit["id"], new_id(), "before"))
            ).status_code == 404
    assert (await attachable(ops, f"visit:{visit['id']}:station:{stations[0]['id']}:later")
            ).status_code == 404
