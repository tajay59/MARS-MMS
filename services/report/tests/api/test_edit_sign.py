"""Editing a visit report draft and signing it (TRD 11.2, 11.3; PRD RPT-2, RPT-4, RPT-5; W17-1 to
W17-6): the routes, the version a save is checked against, and what clears a signature."""

from __future__ import annotations

import asyncio
import base64
import importlib
import io
from copy import deepcopy
from typing import Any

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import SEED_USERS
from PIL import Image, ImageDraw

from app.jobs import drafts as jobs
from tests import visit_facts as vf
from tests.api.test_drafts import TECH1, TECH2, ended, one, processor, with_visit

LEAD = TECH1  # the visit's lead is tech1, tech2 also attended
GATE_NOTE = "Gate code is 4471"


def drawing(size=(300, 120)) -> str:
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    ImageDraw.Draw(image).line([(10, 10), (280, 100), (40, 90)], fill="black", width=4)
    out = io.BytesIO()
    image.save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode()


async def ready(report) -> dict[str, Any]:
    p, _ = await processor(report)
    await p.process(ended(report))
    with_visit(report)
    assert await jobs.refresh_facts(report.svc, await one(report))
    return await one(report)


async def patch(report, d, body: dict[str, Any], who: str = "tech1", **over: Any):
    return await report.http.patch(
        f"/api/v1/reports/{d['_id']}/content", headers=report.bearer(who),
        json={"content_version": over.pop("version", d["content_version"]), **body})


async def sign(report, d, who: str = "tech1", **over: Any):
    body = {"content_version": d["content_version"], "typed_name": "Test Person",
            "image": drawing(), **over}
    return await report.http.post(
        f"/api/v1/reports/{d['_id']}/sign", headers=report.bearer(who), json=body)


async def read(report, d, who: str = "tech1"):
    return await report.http.get(f"/api/v1/reports/{d['_id']}", headers=report.bearer(who))


async def events(report, type_: str) -> list[dict[str, Any]]:
    return [e async for e in report.db["outbox"].find({"type": type_})]


# --- the record carries what the editor needs ----------------------------------------------------


@pytest.mark.req("RPT-2")
async def test_a_draft_carries_its_hash_the_attestation_and_who_attended(report):
    d = await ready(report)
    body = (await read(report, d)).json()
    assert len(body["content_hash"]) == 64 and d["content_hash"] == body["content_hash"]
    assert body["lead_staff_id"] == LEAD and body["staff_ids"] == [TECH1, TECH2]
    assert body["attestation"] == report.settings.attestation and body["signatures"] == []


# --- editing ---------------------------------------------------------------------------------------


@pytest.mark.req("RPT-2")
async def test_an_edit_saves_the_text_and_moves_the_version_and_the_hash(report):
    d = await ready(report)
    r = await patch(report, d, {"narrative": {"summary": "Rain gauge replaced and levelled."}})
    assert r.status_code == 200
    body = r.json()
    assert body["content_version"] == d["content_version"] + 1
    assert body["content"]["narrative"]["summary"] == "Rain gauge replaced and levelled."
    assert body["content"]["narrative"]["follow_up"] == "Bring a new funnel"
    assert body["content_hash"] != d["content_hash"]
    assert body["pdf"]["current"] is False


@pytest.mark.req("RPT-2")
async def test_the_same_save_again_changes_nothing_even_with_the_old_version(report):
    d = await ready(report)
    edit = {"narrative": {"summary": "One summary."}, "media_selection": [
        {"media_id": vf.P_NOTE, "in_body": False}]}
    first = (await patch(report, d, edit)).json()
    again = await patch(report, d, edit)  # the answer was lost: the old version is sent again
    assert again.status_code == 200
    assert again.json()["content_version"] == first["content_version"]
    assert again.json()["content_hash"] == first["content_hash"]
    assert len(await events(report, "report.signatures_cleared")) == 0


@pytest.mark.req("RPT-2")
async def test_a_save_from_a_stale_version_is_refused_with_the_current_record(report):
    d = await ready(report)
    await patch(report, d, {"narrative": {"summary": "Written first."}}, "tech1")
    late = await patch(report, d, {"narrative": {"summary": "Written second."}}, "tech2")
    assert late.status_code == 409 and late.json()["code"] == "content_changed"
    assert late.json()["content_version"] == d["content_version"] + 1
    assert late.json()["current"]["content"]["narrative"]["summary"] == "Written first."
    assert (await read(report, d)).json()["content"]["narrative"]["summary"] == "Written first."


async def test_the_photo_choice_is_edited_per_photo(report):
    d = await ready(report)
    r = await patch(report, d, {"media_selection": [
        {"media_id": vf.P_NOTE, "in_body": False, "caption": "Looking east"}]})
    by_id = {s["media_id"]: s for s in r.json()["content"]["media_selection"]}
    assert by_id[vf.P_NOTE]["in_body"] is False and by_id[vf.P_NOTE]["caption"] == "Looking east"
    assert by_id[vf.P_BEFORE]["in_body"] is True


@pytest.mark.parametrize(("body", "code"), [
    ({"narrative": {"summary": "x" * 5000}}, "too_long"),
    ({"narrative": {"stations": [{"station_id": new_id(), "work_performed": "x"}]}},
     "unknown_station"),
    ({"media_selection": [{"media_id": new_id(), "in_body": True}]}, "unknown_photo"),
])
async def test_an_edit_the_report_cannot_take_is_422_and_changes_nothing(report, body, code):
    d = await ready(report)
    r = await patch(report, d, body)
    assert r.status_code == 422 and r.json()["code"] == code
    assert (await one(report))["content_version"] == d["content_version"]


async def test_unknown_fields_and_a_missing_version_are_422(report):
    d = await ready(report)
    url = f"/api/v1/reports/{d['_id']}/content"
    assert (await report.http.patch(url, headers=report.bearer("tech1"), json={
        "content_version": 1, "narrative": {"secret": "x"}})).status_code == 422
    assert (await report.http.patch(url, headers=report.bearer("tech1"), json={
        "narrative": {"summary": "x"}})).status_code == 422


@pytest.mark.req("RPT-2")
async def test_only_the_people_attending_and_admins_edit(report):
    d = await ready(report)
    await report.db["reports"].update_one({}, {"$set": {"staff_ids": [TECH2]}})
    body = {"narrative": {"summary": "x"}}
    assert (await patch(report, d, body, "tech1")).status_code == 403
    assert (await patch(report, d, body, "viewer")).status_code == 403
    assert (await patch(report, d, body, "client_a1")).status_code == 403
    assert (await patch(report, d, body, "tech2")).status_code == 200
    assert (await patch(report, d, {"narrative": {"summary": "y"}}, "admin",
                        version=d["content_version"] + 1)).status_code == 200


async def test_a_report_that_is_not_there_or_not_ready_or_not_a_draft_cannot_be_edited(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    early = await one(report)
    r = await patch(report, early, {"narrative": {"summary": "x"}})
    assert r.status_code == 409 and r.json()["code"] == "draft_not_ready"
    d = await ready(report)
    await report.db["reports"].update_one({}, {"$set": {"status": "final"}})
    r = await patch(report, d, {"narrative": {"summary": "x"}})
    assert r.status_code == 409 and r.json()["code"] == "not_a_draft"
    gone = await report.http.patch(
        f"/api/v1/reports/{new_id()}/content", headers=report.bearer("tech1"),
        json={"content_version": 1, "narrative": {"summary": "x"}})
    assert gone.status_code == 404


# --- signing -----------------------------------------------------------------------------------------


@pytest.mark.req("RPT-4")
async def test_the_lead_signs_and_the_record_keeps_what_the_trd_asks(report):
    d = await ready(report)
    r = await sign(report, d, "tech1", typed_name="  Test   Lead ")
    assert r.status_code == 201
    (sig,) = r.json()["signatures"]
    assert sig["role"] == "lead" and sig["signer_id"] == LEAD and sig["valid"] is True
    assert sig["typed_name"] == "Test Lead" and sig["signer_name"] == SEED_USERS["tech1"].name
    assert sig["attestation"] == report.settings.attestation
    assert sig["image"].startswith("data:image/png;base64,")
    assert sig["content_version"] == d["content_version"]
    stored = await report.db["signatures"].find_one({"_id": sig["id"]})
    assert stored["content_hash"] == d["content_hash"] and stored["report_version"] == 1
    assert stored["user_agent"].startswith("python-httpx") and stored["ip"]
    assert bytes(stored["image"]).startswith(b"\x89PNG")


@pytest.mark.req("RPT-4")
async def test_another_person_who_attended_signs_as_attending(report):
    d = await ready(report)
    await sign(report, d, "tech1")
    r = await sign(report, d, "tech2")
    assert r.status_code == 201
    assert sorted(s["role"] for s in r.json()["signatures"]) == ["attending", "lead"]
    (event,) = [e for e in await events(report, "report.signed") if e["data"]["role"] == "attending"]
    assert event["data"]["valid_signatures"] == 2 and event["data"]["signer_id"] == TECH2


@pytest.mark.req("RPT-4")
async def test_signing_twice_is_409_already_signed_and_adds_nothing(report):
    d = await ready(report)
    assert (await sign(report, d, "tech1")).status_code == 201
    again = await sign(report, d, "tech1")
    assert again.status_code == 409 and again.json()["code"] == "already_signed"
    assert await report.db["signatures"].count_documents({}) == 1
    assert len((await read(report, d)).json()["signatures"]) == 1


@pytest.mark.req("RPT-4")
async def test_two_taps_at_once_make_one_signature(report):
    d = await ready(report)
    first, second = await asyncio.gather(sign(report, d, "tech1"), sign(report, d, "tech1"))
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    assert await report.db["signatures"].count_documents({"valid": True}) == 1


@pytest.mark.req("RPT-4")
async def test_an_admin_who_did_not_attend_does_not_sign_and_a_viewer_cannot(report):
    d = await ready(report)
    for who in ("admin", "viewer", "client_a1"):
        assert (await sign(report, d, who)).status_code == 403
    assert await report.db["signatures"].count_documents({}) == 0


@pytest.mark.req("RPT-4")
async def test_a_signature_is_for_the_version_the_person_read(report):
    d = await ready(report)
    await patch(report, d, {"narrative": {"summary": "Changed while the dialog was open."}})
    r = await sign(report, d, "tech1")
    assert r.status_code == 409 and r.json()["code"] == "content_changed"
    assert r.json()["content_version"] == d["content_version"] + 1
    assert await report.db["signatures"].count_documents({}) == 0


@pytest.mark.parametrize(("over", "code"), [
    ({"image": "not an image"}, "bad_signature"),
    ({"image": base64.b64encode(b"GIF89a-not-a-png").decode()}, "bad_signature"),
    ({"image": drawing((1300, 100))}, "signature_too_large"),
    ({"typed_name": "A"}, "bad_name"),
])
async def test_a_bad_drawing_or_name_is_422_and_nothing_is_stored(report, over, code):
    d = await ready(report)
    r = await sign(report, d, "tech1", **over)
    assert r.status_code == 422 and r.json()["code"] == code
    assert await report.db["signatures"].count_documents({}) == 0


async def test_a_draft_not_yet_prepared_or_not_a_draft_cannot_be_signed(report):
    p, _ = await processor(report)
    await p.process(ended(report))
    early = await sign(report, await one(report), "tech1", content_version=1)
    assert early.status_code == 409 and early.json()["code"] == "draft_not_ready"
    d = await ready(report)
    await report.db["reports"].update_one({}, {"$set": {"status": "final"}})
    r = await sign(report, d, "tech1")
    assert r.status_code == 409 and r.json()["code"] == "not_a_draft"
    assert (await sign(report, {"_id": new_id(), "content_version": 1}, "tech1")).status_code == 404


async def test_the_event_names_the_signer_and_never_the_drawing_or_the_name(report):
    d = await ready(report)
    await sign(report, d, "tech1", typed_name="Zebediah Quux")
    (event,) = await events(report, "report.signed")
    text = str(event)
    assert "Zebediah" not in text and "image" not in text and "iVBOR" not in text
    assert event["data"]["report_id"] == d["_id"] and event["data"]["content_version"] == 1
    assert event["key"] == vf.REQUEST


# --- what clears a signature (W17-3, W17-4) ------------------------------------------------------------


@pytest.mark.req("RPT-4")
async def test_an_edit_that_changes_the_page_clears_every_signature_and_keeps_them_flagged(report):
    d = await ready(report)
    await sign(report, d, "tech1")
    await sign(report, d, "tech2")
    r = await patch(report, d, {"narrative": {"summary": "Edited after signing."}}, "tech2")
    body = r.json()
    assert len(body["signatures"]) == 2 and all(s["valid"] is False for s in body["signatures"])
    assert all(s["cleared_by"] == TECH2 and s["cleared_at"] and s["image"] is None
               for s in body["signatures"])
    (cleared,) = await events(report, "report.signatures_cleared")
    assert cleared["data"]["count"] == 2 and cleared["data"]["reason"] == "edit"
    assert cleared["actor"]["user_id"] == TECH2
    # They sign again, on the new version of the page
    again = await sign(report, {**d, "content_version": body["content_version"]}, "tech1")
    assert again.status_code == 201
    assert [s["valid"] for s in again.json()["signatures"]].count(True) == 1
    assert await report.db["signatures"].count_documents({}) == 3


@pytest.mark.req("RPT-4")
async def test_a_save_that_changes_nothing_keeps_the_signatures(report):
    d = await ready(report)
    await patch(report, d, {"narrative": {"summary": "Same words."}})
    d = await one(report)
    await sign(report, d, "tech1")
    same = await patch(report, d, {"narrative": {"summary": "Same words."}})
    assert same.status_code == 200 and same.json()["signatures"][0]["valid"] is True
    assert await events(report, "report.signatures_cleared") == []


@pytest.mark.req("RPT-4")
async def test_the_same_facts_read_again_keep_the_signatures(report):
    d = await ready(report)
    await sign(report, d, "tech1")
    await report.db["reports"].update_one(
        {}, {"$set": {"facts_stale": True, "facts_stale_at": report.clock.now()}})
    report.facts.by_visit[vf.VISIT]["visit"]["version"] += 1  # the visit moved, the page did not
    assert (await jobs.tick(report.svc))["refreshed"] == 1
    after = await one(report)
    assert after["facts_version"] == d["facts_version"] + 1
    assert after["content_version"] == d["content_version"]
    assert after["content_hash"] == d["content_hash"]
    assert (await read(report, d)).json()["signatures"][0]["valid"] is True


@pytest.mark.req("RPT-4")
async def test_a_board_change_that_changes_the_page_clears_the_signatures(report):
    d = await ready(report)
    await sign(report, d, "tech1")
    report.facts.by_visit[vf.VISIT]["stations"][0]["elements"][0]["title"] = "Replaced the funnel"
    await report.db["reports"].update_one(
        {}, {"$set": {"facts_stale": True, "facts_stale_at": report.clock.now()}})
    await jobs.tick(report.svc)
    after = await one(report)
    assert after["content_version"] == d["content_version"] + 1
    assert after["content_hash"] != d["content_hash"]
    body = (await read(report, d)).json()
    assert body["signatures"][0]["valid"] is False and body["signatures"][0]["cleared_by"] == "facts"
    (event,) = await events(report, "report.signatures_cleared")
    assert event["data"]["reason"] == "facts" and event["data"]["count"] == 1
    # The person who read the old page can no longer sign it
    late = await sign(report, d, "tech2")
    assert late.status_code == 409 and late.json()["code"] == "content_changed"


@pytest.mark.req("RPT-4")
async def test_a_staff_only_element_changing_on_the_board_keeps_the_signatures(report):
    d = await ready(report)
    facts = report.facts.by_visit[vf.VISIT]
    facts["stations"][0]["elements"].append(
        vf.element("note", "Access", description=GATE_NOTE, shared=False))
    await report.db["reports"].update_one(
        {}, {"$set": {"facts_stale": True, "facts_stale_at": report.clock.now()}})
    await sign(report, d, "tech1")
    await jobs.tick(report.svc)
    after = await one(report)
    assert after["content_hash"] == d["content_hash"]
    assert (await read(report, d)).json()["signatures"][0]["valid"] is True
    assert GATE_NOTE in str(after["content"]["facts"])  # staff still see it in the editor


async def test_a_refresh_does_not_overwrite_an_edit_made_while_the_facts_were_read(report):
    d = await ready(report)
    await report.db["reports"].update_one(
        {}, {"$set": {"facts_stale": True, "facts_stale_at": report.clock.now()}})
    stale = await one(report)
    await patch(report, d, {"narrative": {"summary": "Typed meanwhile."}})
    assert await jobs.refresh_facts(report.svc, stale)  # works from the copy it read before the edit
    after = await one(report)
    assert after["content"]["narrative"]["summary"] == "Typed meanwhile."
    assert after["facts_stale"] is True  # read again on the next tick
    assert (await jobs.tick(report.svc))["refreshed"] == 1
    assert (await one(report))["facts_stale"] is False


# --- what a client reads (rule 6) -----------------------------------------------------------------------


@pytest.mark.req("RPT-5")
async def test_a_client_reads_a_final_report_without_staff_only_elements_or_signatures(report):
    d = await ready(report)
    facts = deepcopy(report.facts.by_visit[vf.VISIT])
    facts["stations"][0]["elements"].append(
        vf.element("note", "Access", description=GATE_NOTE, shared=False))
    report.facts.by_visit[vf.VISIT] = facts
    await report.db["reports"].update_one(
        {}, {"$set": {"facts_stale": True, "facts_stale_at": report.clock.now()}})
    await jobs.tick(report.svc)
    await sign(report, d, "tech1")
    await report.db["reports"].update_one(
        {}, {"$set": {"status": "final", "org_id": SEED_USERS["client_a1"].org_id}})
    staff = (await read(report, d)).json()
    assert GATE_NOTE in str(staff["content"])
    mine = (await read(report, d, "client_a1")).json()
    assert GATE_NOTE not in str(mine) and "Access" not in str(mine)
    assert mine["signatures"] == [] and mine["content_hash"] is None and mine["staff_ids"] == []
    assert mine["lead_staff_id"] is None and mine["attestation"] is None
    assert (await read(report, d, "client_b1")).status_code == 404
    assert "iVBOR" not in str(mine) and "data:image/png" not in str(mine)


async def test_a_final_report_is_immutable_through_every_mutating_route(report):
    d = await ready(report)
    await sign(report, d, "tech1")
    await report.db["reports"].update_one({}, {"$set": {"status": "superseded"}})
    before = await report.db["reports"].find_one({})
    for status in ("final", "superseded"):
        await report.db["reports"].update_one({}, {"$set": {"status": status}})
        assert (await patch(report, d, {"narrative": {"summary": "no"}})).status_code == 409
        assert (await sign(report, d, "tech2")).status_code == 409
    after = await report.db["reports"].find_one({})
    assert after["content"] == before["content"] and after["content_version"] == before["content_version"]
    assert await report.db["signatures"].count_documents({"valid": True}) == 1


# --- the migration -----------------------------------------------------------------------------------------


async def test_a_draft_from_before_signatures_gets_its_hash_in_the_migration(report):
    d = await ready(report)
    await report.db["reports"].update_one({}, {"$set": {"content_hash": None}})
    migration = importlib.import_module("app.migrations.0004_signatures")
    await migration.up(report.db)
    assert (await one(report))["content_hash"] == d["content_hash"]
