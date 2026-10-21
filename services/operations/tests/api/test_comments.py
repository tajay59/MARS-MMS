"""Comments and PDF attachments, W9 slice 2 (PRD REQ-3, REQ-9, REQ-10; rules 3, 4, 5, 6;
ADR-19), over the real app. The exit check: an internal comment's file never reaches a client."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from tests.api.test_requests import make, two_orgs

CLIENT_A = SEED_USERS["client_a1"].id
TECH1 = SEED_USERS["tech1"].id


async def a_request(ops, who: str = "client_a1", **fields: Any) -> dict[str, Any]:
    a, _ = await two_orgs(ops)
    return await make(ops, who, [a["id"]], **fields)


async def post(
    ops, who: str, request_id: str, body: str = "Hello", *, media: list[str] | None = None,
    internal: bool = False, comment_id: str | None = None,
):
    json: dict[str, Any] = {"body": body, "internal": internal, "media_ids": media or []}
    if comment_id:
        json["id"] = comment_id
    return await ops.http.post(
        f"/api/v1/requests/{request_id}/comments", json=json, headers=ops.bearer(who)
    )


async def thread(ops, who: str, request_id: str) -> list[dict[str, Any]]:
    r = await ops.http.get(f"/api/v1/requests/{request_id}/comments", headers=ops.bearer(who))
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    return items


def pdf(ops, request_id: str, comment_id: str, who: str = "tech1", **fields: Any) -> str:
    return ops.media.add(f"comment:{request_id}:{comment_id}", by=who, kind="pdf", **fields)


# --- Posting and reading (REQ-9) ---------------------------------------------------------------


@pytest.mark.req("REQ-9")
async def test_a_client_and_staff_talk_in_one_thread_oldest_first(ops):
    request = await a_request(ops)
    first = await post(ops, "client_a1", request["id"], "The cups do not turn.")
    assert first.status_code == 201, first.text
    ops.clock.advance(minutes=5)
    await post(ops, "tech1", request["id"], "I can go on Thursday.")
    ops.clock.advance(minutes=5)
    await post(ops, "client_a1", request["id"], "Thursday works.")
    items = await thread(ops, "client_a1", request["id"])
    assert [i["body"] for i in items] == [
        "The cups do not turn.", "I can go on Thursday.", "Thursday works.",
    ]
    assert [i["author_role"] for i in items] == ["client", "technician", "client"]
    assert items[1]["author"] == {"id": TECH1, "name": SEED_USERS["tech1"].name}
    assert "@" not in str(items)  # names only, never an email (D4)


@pytest.mark.req("REQ-9")
async def test_a_comment_counts_on_the_request(ops):
    request = await a_request(ops)
    assert request["comment_count"] == 0
    await post(ops, "client_a1", request["id"])
    got = (await ops.http.get(f"/api/v1/requests/{request['id']}",
                              headers=ops.bearer("tech1"))).json()
    assert got["comment_count"] == 1


@pytest.mark.req("REQ-9")
async def test_posting_is_idempotent_by_the_comment_id(ops):
    request = await a_request(ops)
    cid = new_id()
    one = await post(ops, "client_a1", request["id"], "Once", comment_id=cid)
    two = await post(ops, "client_a1", request["id"], "Once", comment_id=cid)
    assert (one.status_code, two.status_code) == (201, 200)
    assert one.json()["id"] == two.json()["id"] == cid
    assert len(await thread(ops, "client_a1", request["id"])) == 1
    other = await post(ops, "tech1", request["id"], "Mine now", comment_id=cid)
    assert other.status_code == 409 and other.json()["code"] == "id_taken"
    assert len(await ops.outbox("comment.added")) == 1


@pytest.mark.req("REQ-9")
async def test_two_posts_with_one_id_at_once_make_one_comment(ops):
    request = await a_request(ops)
    cid = new_id()
    first, second = await asyncio.gather(
        post(ops, "client_a1", request["id"], "Same", comment_id=cid),
        post(ops, "client_a1", request["id"], "Same", comment_id=cid),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 201]
    assert len(await thread(ops, "client_a1", request["id"])) == 1


@pytest.mark.req("REQ-9")
@pytest.mark.parametrize("text", ["", "   ", "x" * 5001])
async def test_a_comment_needs_words_and_not_too_many(ops, text):
    request = await a_request(ops)
    assert (await post(ops, "client_a1", request["id"], text)).status_code == 422


@pytest.mark.req("REQ-9")
async def test_a_viewer_reads_and_never_posts(ops):
    request = await a_request(ops)
    await post(ops, "tech1", request["id"], "Hello")
    assert len(await thread(ops, "viewer", request["id"])) == 1
    assert (await post(ops, "viewer", request["id"])).status_code == 403


@pytest.mark.req("REQ-9")
async def test_another_organization_has_no_thread_to_read_or_join(ops):
    request = await a_request(ops)
    await post(ops, "client_a1", request["id"])
    stranger = ops.http.get(f"/api/v1/requests/{request['id']}/comments",
                            headers=ops.bearer("client_b1"))
    assert (await stranger).status_code == 404  # rule 4
    assert (await post(ops, "client_b1", request["id"])).status_code == 404
    assert (await ops.http.get(f"/api/v1/requests/{request['id']}/comments")).status_code == 401


async def test_the_comment_event_names_the_comment_and_never_its_words(ops):
    request = await a_request(ops)
    await post(ops, "tech1", request["id"], "Secret plan: bring the spare modem", internal=True)
    [event] = await ops.outbox("comment.added")
    assert event.key == request["id"] and event.org_id == ORG_A
    assert event.data["internal"] is True and event.data["author_role"] == "technician"
    assert event.data["title"] == request["title"] and event.data["created_by"] == CLIENT_A
    assert "Secret" not in str(event.data) and "body" not in event.data


# --- Internal comments (REQ-10, rule 6) --------------------------------------------------------


@pytest.mark.req("REQ-10")
async def test_an_internal_comment_is_never_shown_to_the_client(ops):
    request = await a_request(ops)
    await post(ops, "client_a1", request["id"], "Visible")
    r = await post(ops, "tech1", request["id"], "Staff only", internal=True)
    assert r.json()["internal"] is True
    assert [i["body"] for i in await thread(ops, "client_a1", request["id"])] == ["Visible"]
    assert [i["body"] for i in await thread(ops, "tech1", request["id"])] == [
        "Visible", "Staff only",
    ]
    assert [i["internal"] for i in await thread(ops, "admin", request["id"])] == [False, True]
    # Not in the count either: nothing hints that it exists
    mine = (await ops.http.get(f"/api/v1/requests/{request['id']}",
                               headers=ops.bearer("client_a1"))).json()
    assert mine["comment_count"] == 1
    assert "Staff only" not in str(mine)


@pytest.mark.req("REQ-10")
async def test_a_client_cannot_mark_a_comment_internal(ops):
    request = await a_request(ops)
    r = await post(ops, "client_a1", request["id"], "I tried", internal=True)
    assert r.status_code == 201 and r.json()["internal"] is False
    assert len(await thread(ops, "client_a1", request["id"])) == 1


@pytest.mark.req("REQ-10")
async def test_a_client_cannot_edit_an_internal_comment_or_find_it(ops):
    request = await a_request(ops)
    hidden = (await post(ops, "tech1", request["id"], "Hidden", internal=True)).json()
    r = await ops.http.patch(
        f"/api/v1/requests/{request['id']}/comments/{hidden['id']}",
        json={"version": 1, "body": "Changed"}, headers=ops.bearer("client_a1"),
    )
    assert r.status_code == 404


# --- Editing (REQ-9, REQ-10) -------------------------------------------------------------------


async def edit(ops, who: str, request_id: str, comment_id: str, **json: Any):
    return await ops.http.patch(
        f"/api/v1/requests/{request_id}/comments/{comment_id}", json=json,
        headers=ops.bearer(who),
    )


@pytest.mark.req("REQ-9")
async def test_the_author_edits_within_fifteen_minutes_and_then_it_is_fixed(ops):
    request = await a_request(ops)
    posted = (await post(ops, "client_a1", request["id"], "First")).json()
    assert posted["editable_until"] is not None
    ops.clock.advance(minutes=14)
    r = await edit(ops, "client_a1", request["id"], posted["id"], version=1, body="Better")
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "Better" and r.json()["edited_at"] is not None
    assert r.json()["version"] == 2
    [event] = await ops.outbox("comment.updated")
    assert event.data["body_changed"] is True and event.data["internal_changed"] is False
    ops.clock.advance(minutes=2)
    late = await edit(ops, "client_a1", request["id"], posted["id"], version=2, body="Too late")
    assert late.status_code == 409 and late.json()["code"] == "edit_window_closed"
    assert (await thread(ops, "client_a1", request["id"]))[0]["editable_until"] is None


@pytest.mark.req("REQ-9")
async def test_only_the_author_edits(ops):
    request = await a_request(ops)
    posted = (await post(ops, "client_a1", request["id"], "Mine")).json()
    for who in ("tech1", "admin"):
        r = await edit(ops, who, request["id"], posted["id"], version=1, body="Not yours")
        assert r.status_code == 403
    mine = (await thread(ops, "tech1", request["id"]))[0]
    assert mine["editable_until"] is None  # no edit button for staff on a client's comment


async def test_a_stale_version_is_refused(ops):
    request = await a_request(ops)
    posted = (await post(ops, "client_a1", request["id"], "First")).json()
    await edit(ops, "client_a1", request["id"], posted["id"], version=1, body="Second")
    r = await edit(ops, "client_a1", request["id"], posted["id"], version=1, body="Third")
    assert r.status_code == 409


@pytest.mark.req("REQ-10")
async def test_staff_make_their_own_comment_internal_and_back(ops):
    request = await a_request(ops)
    posted = (await post(ops, "tech1", request["id"], "Oops, meant for staff")).json()
    assert len(await thread(ops, "client_a1", request["id"])) == 1
    r = await edit(ops, "tech1", request["id"], posted["id"], version=1, internal=True)
    assert r.status_code == 200 and r.json()["internal"] is True
    assert await thread(ops, "client_a1", request["id"]) == []
    [event] = await ops.outbox("comment.updated")
    assert event.data["internal_changed"] is True and event.data["internal"] is True
    back = await edit(ops, "tech1", request["id"], posted["id"], version=2, internal=False)
    assert back.json()["internal"] is False
    assert len(await thread(ops, "client_a1", request["id"])) == 1


async def test_a_client_edit_cannot_change_who_sees_it(ops):
    request = await a_request(ops)
    posted = (await post(ops, "client_a1", request["id"], "Hello")).json()
    r = await edit(ops, "client_a1", request["id"], posted["id"], version=1, internal=True)
    assert r.status_code == 200 and r.json()["internal"] is False and r.json()["version"] == 1


# --- Files on a comment (REQ-3, W9-8, W9-9) ----------------------------------------------------


@pytest.mark.req("REQ-3")
async def test_a_comment_holds_clean_pdfs_the_author_uploaded_for_it(ops):
    request = await a_request(ops)
    cid = new_id()
    media = pdf(ops, request["id"], cid, "client_a1", filename="storm-report.pdf", size=1_200_000)
    r = await post(ops, "client_a1", request["id"], "Attached", media=[media], comment_id=cid)
    assert r.status_code == 201, r.text
    assert r.json()["attachments"] == [
        {"media_id": media, "name": "storm-report.pdf", "size_bytes": 1_200_000}
    ]


@pytest.mark.req("REQ-3")
@pytest.mark.parametrize(
    ("problem", "expected", "code"),
    [
        ("pending", 409, None),
        ("wrong_owner", 422, "wrong_owner"),
        ("not_yours", 422, "not_yours"),
        ("wrong_kind", 422, "wrong_kind"),
        ("too_large", 422, "too_large"),
        ("unknown", 422, "unknown_file"),
    ],
)
async def test_a_file_that_is_not_right_is_refused_with_a_reason(ops, problem, expected, code):
    request = await a_request(ops)
    cid = new_id()
    owner = f"comment:{request['id']}:{cid}"
    media: str
    if problem == "pending":
        media = ops.media.add(owner, by="client_a1", kind="pdf", status="processing")
    elif problem == "wrong_owner":
        media = ops.media.add(f"comment:{request['id']}:{new_id()}", by="client_a1", kind="pdf")
    elif problem == "not_yours":
        media = ops.media.add(owner, by="tech1", kind="pdf")
    elif problem == "wrong_kind":
        media = ops.media.add(owner, by="client_a1", kind="config")
    elif problem == "too_large":
        media = ops.media.add(owner, by="client_a1", kind="pdf", size=26 * 1024 * 1024)
    else:
        media = new_id()
    r = await post(ops, "client_a1", request["id"], "With a file", media=[media], comment_id=cid)
    assert r.status_code == expected, r.text
    if code:
        assert r.json()["code"] == code
    assert await thread(ops, "client_a1", request["id"]) == []  # nothing half-made


async def test_a_file_cannot_be_used_twice_and_five_is_the_most(ops):
    request = await a_request(ops)
    first = new_id()
    media = pdf(ops, request["id"], first, "client_a1")
    assert (await post(ops, "client_a1", request["id"], "One", media=[media],
                       comment_id=first)).status_code == 201
    # The same file named by another comment: its owner reference is wrong anyway, and the
    # in-use check catches a forged one
    second = new_id()
    ops.media.files[media] = ops.media.files[media].__class__(
        **{**ops.media.files[media].__dict__, "owner_ref": f"comment:{request['id']}:{second}"}
    )
    r = await post(ops, "client_a1", request["id"], "Two", media=[media], comment_id=second)
    assert r.status_code == 409 and r.json()["code"] == "file_in_use"
    many = new_id()
    six = [pdf(ops, request["id"], many, "client_a1") for _ in range(6)]
    assert (await post(ops, "client_a1", request["id"], "Six", media=six,
                       comment_id=many)).status_code == 422


# --- The exit check: an internal comment's file never reaches a client ------------------------


async def link(ops, who: str, request_id: str, comment_id: str, media_id: str):
    return await ops.http.get(
        f"/api/v1/requests/{request_id}/comments/{comment_id}/attachments/{media_id}/download",
        headers=ops.bearer(who),
    )


@pytest.mark.req("REQ-10")
@pytest.mark.req("REQ-3")
async def test_the_file_of_an_internal_comment_stays_staff_only_end_to_end(ops):
    request = await a_request(ops)
    cid = new_id()
    media = pdf(ops, request["id"], cid, "tech1", filename="modem-quote.pdf")
    posted = await post(ops, "tech1", request["id"], "Quote for staff", media=[media],
                        internal=True, comment_id=cid)
    assert posted.status_code == 201, posted.text

    # (1) the client's thread has no trace of it, in the list or the count
    assert await thread(ops, "client_a1", request["id"]) == []
    # (2) asking for the file by its ID is 404, the same as for a file that does not exist
    assert (await link(ops, "client_a1", request["id"], cid, media)).status_code == 404
    assert (await link(ops, "client_a1", request["id"], new_id(), media)).status_code == 404
    # (3) another organization's client is no better off
    assert (await link(ops, "client_b1", request["id"], cid, media)).status_code == 404
    # (4) media was told to keep it staff-only
    [vis] = await ops.outbox("media.visibility_requested")
    assert vis.data["media_ids"] == [media] and vis.data["visibility"] == "staff"
    # Staff do get it
    ok = await link(ops, "admin", request["id"], cid, media)
    assert ok.status_code == 200 and ok.json()["filename"] == "modem-quote.pdf"
    assert ops.media.links[-1] == (media, True)


@pytest.mark.req("REQ-3")
async def test_the_file_of_a_client_visible_comment_is_shown_to_the_organization(ops):
    request = await a_request(ops)
    cid = new_id()
    media = pdf(ops, request["id"], cid, "tech1")
    await post(ops, "tech1", request["id"], "Datasheet", media=[media], comment_id=cid)
    [vis] = await ops.outbox("media.visibility_requested")
    assert vis.data["visibility"] == "org" and vis.data["visibility_version"] == 1
    assert (await link(ops, "client_a1", request["id"], cid, media)).status_code == 200
    assert (await link(ops, "client_b1", request["id"], cid, media)).status_code == 404


@pytest.mark.req("REQ-10")
async def test_making_a_comment_internal_hides_its_file_again_with_a_newer_version(ops):
    request = await a_request(ops)
    cid = new_id()
    media = pdf(ops, request["id"], cid, "tech1")
    await post(ops, "tech1", request["id"], "Datasheet", media=[media], comment_id=cid)
    assert (await link(ops, "client_a1", request["id"], cid, media)).status_code == 200
    await edit(ops, "tech1", request["id"], cid, version=1, internal=True)
    sent = await ops.outbox("media.visibility_requested")
    assert [(e.data["visibility"], e.data["visibility_version"]) for e in sent] == [
        ("org", 1), ("staff", 2),
    ]
    assert (await link(ops, "client_a1", request["id"], cid, media)).status_code == 404


async def test_a_file_media_has_not_cleared_is_not_handed_out(ops):
    request = await a_request(ops)
    cid = new_id()
    media = pdf(ops, request["id"], cid, "tech1")
    await post(ops, "tech1", request["id"], "Datasheet", media=[media], comment_id=cid)
    ops.media.files[media] = ops.media.files[media].__class__(
        **{**ops.media.files[media].__dict__, "status": "processing"}
    )
    r = await link(ops, "admin", request["id"], cid, media)
    assert r.status_code == 409 and r.json()["code"] == "not_ready"


async def test_only_the_files_of_that_comment_can_be_fetched_through_it(ops):
    request = await a_request(ops)
    cid, other = new_id(), new_id()
    mine = pdf(ops, request["id"], cid, "tech1")
    theirs = pdf(ops, request["id"], other, "tech1")
    await post(ops, "tech1", request["id"], "A", media=[mine], comment_id=cid)
    await post(ops, "tech1", request["id"], "B", media=[theirs], comment_id=other)
    assert (await link(ops, "admin", request["id"], cid, theirs)).status_code == 404


# --- Files on a new request (REQ-3) ------------------------------------------------------------


@pytest.mark.req("REQ-3")
async def test_a_request_can_be_made_with_pdfs_uploaded_before_it_existed(ops):
    a, _ = await two_orgs(ops)
    request_id = new_id()
    media = ops.media.add(f"request:{request_id}", by="client_a1", kind="pdf",
                          filename="site-notes.pdf", size=2048)
    r = await ops.http.post(
        "/api/v1/requests", headers=ops.bearer("client_a1"),
        json={"id": request_id, "title": "With a file", "description": "See the notes.",
              "category": "fault", "priority": "normal", "station_ids": [a["id"]],
              "media_ids": [media]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["attachments"] == [
        {"media_id": media, "name": "site-notes.pdf", "size_bytes": 2048}
    ]
    [vis] = await ops.outbox("media.visibility_requested")
    assert vis.data["media_ids"] == [media] and vis.data["visibility"] == "org"
    download = await ops.http.get(
        f"/api/v1/requests/{request_id}/attachments/{media}/download",
        headers=ops.bearer("tech1"),
    )
    assert download.status_code == 200 and download.json()["filename"] == "site-notes.pdf"
    other = await ops.http.get(
        f"/api/v1/requests/{request_id}/attachments/{media}/download",
        headers=ops.bearer("client_b1"),
    )
    assert other.status_code == 404


@pytest.mark.req("REQ-3")
async def test_files_need_the_requests_own_id_and_the_right_owner(ops):
    a, _ = await two_orgs(ops)
    media = ops.media.add(f"request:{new_id()}", by="client_a1", kind="pdf")
    base = {"title": "T", "description": "D", "category": "fault", "priority": "low",
            "station_ids": [a["id"]], "media_ids": [media]}
    no_id = await ops.http.post("/api/v1/requests", json=base, headers=ops.bearer("client_a1"))
    assert no_id.status_code == 422 and no_id.json()["code"] == "id_required"
    wrong = await ops.http.post("/api/v1/requests", json={**base, "id": new_id()},
                                headers=ops.bearer("client_a1"))
    assert wrong.status_code == 422 and wrong.json()["code"] == "wrong_owner"


# --- The owner check media makes on upload (TRD §3.3) -----------------------------------------


async def attachable(ops, owner_ref: str, who: str):
    user = SEED_USERS[who]
    return await ops.http.get(
        "/internal/attachable",
        params={"owner_ref": owner_ref, "user_id": user.id, "roles": ",".join(user.roles),
                "org_id": user.org_id or ""},
        headers=ops.service("media"),
    )


async def test_a_client_may_upload_for_a_request_that_does_not_exist_yet(ops):
    r = await attachable(ops, f"request:{new_id()}", "client_a1")
    assert r.status_code == 200 and r.json()["org_id"] == ORG_A
    assert (await attachable(ops, f"request:{new_id()}", "admin")).status_code == 200
    assert (await attachable(ops, f"request:{new_id()}", "viewer")).status_code == 403
    assert (await attachable(ops, f"request:{new_id()}", "tech1")).status_code == 403


async def test_uploads_for_an_existing_request_follow_who_can_see_it(ops):
    request = await a_request(ops)
    assert (await attachable(ops, f"request:{request['id']}", "client_a1")).json()["org_id"] \
        == ORG_A
    assert (await attachable(ops, f"request:{request['id']}", "client_b1")).status_code == 404
    assert (await attachable(ops, f"request:{request['id']}", "tech1")).status_code == 200
    assert (await attachable(ops, f"request:{request['id']}", "viewer")).status_code == 403


async def test_uploads_for_a_comment_need_a_request_the_person_can_see(ops):
    request = await a_request(ops)
    ref = f"comment:{request['id']}:{new_id()}"
    assert (await attachable(ops, ref, "client_a1")).json()["org_id"] == ORG_A
    assert (await attachable(ops, ref, "tech1")).status_code == 200
    assert (await attachable(ops, ref, "client_b1")).status_code == 404
    assert (await attachable(ops, ref, "viewer")).status_code == 403
    missing = f"comment:{new_id()}:{new_id()}"
    assert (await attachable(ops, missing, "tech1")).status_code == 404
