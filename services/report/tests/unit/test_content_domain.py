"""What a visit report prints and the hash a signature stands for (TRD 11.2, 11.3; W17-1 to W17-3,
W17-6). Pure rules."""

from __future__ import annotations

import base64
import io
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from mms_common.errors import ValidationFailed
from PIL import Image, ImageDraw

from app.domain import content, drafts, signing, visit_view
from tests import visit_facts as vf

NOW = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)
GATE_NOTE = "Gate code is 4471"
LIMITS = {"max_bytes": 100 * 1024, "max_width": 1200, "max_height": 600}


def staff_only_note(facts):
    """A note on the first station that is staff only, with a photo."""
    note = vf.element("note", "Access", description=GATE_NOTE, shared=False,
                      media={"main": [vf.media("01900000-0000-7000-8000-0000000f0aaa")]})
    facts["stations"][0]["elements"].append(note)
    return note


def made(facts):
    return {"facts": facts, "narrative": drafts.default_narrative(facts),
            "media_selection": drafts.default_media_selection(facts)}


def png(size=(300, 120), *, mode="RGBA") -> bytes:
    image = Image.new(mode, size, (255, 255, 255, 0) if mode == "RGBA" else "white")
    ImageDraw.Draw(image).line([(10, 10), (280, 100), (40, 90)], fill="black", width=4)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


# --- only shared elements print (W17-1) --------------------------------------------------------


def test_the_narrative_and_the_photo_choice_leave_out_staff_only_elements():
    facts = vf.facts()
    staff_only_note(facts)
    narrative = drafts.default_narrative(facts)
    assert GATE_NOTE not in str(narrative)
    selection = drafts.default_media_selection(facts)
    assert "01900000-0000-7000-8000-0000000f0aaa" not in [s["media_id"] for s in selection]
    assert "01900000-0000-7000-8000-0000000f0aaa" not in drafts.pending_media(
        facts, {"01900000-0000-7000-8000-0000000f0aaa": "processing"})


def test_the_page_prints_shared_elements_only_and_says_so_for_a_station_with_none():
    facts = vf.facts()
    staff_only_note(facts)
    for e in facts["stations"][1]["elements"]:
        e["shared"] = False
    report = {**drafts.new_draft(
        report_id="r1", number="VR-2026-0042-02", subject_ref="visit:x", visit_id=vf.VISIT,
        request_id=vf.REQUEST, org_id=vf.ORG, staff_ids=[vf.LEAD], lead_staff_id=vf.LEAD,
        ended_at=NOW, now=NOW), "content": made(facts)}
    page = visit_view.build(report, {}, app_url="https://x", generated_at=NOW)
    assert GATE_NOTE not in str(page) and "Access" not in str(page)
    first, second = page["stations"]
    assert [n["title"] for n in first["notes"]] == ["Mast and guy wires"]
    assert second["empty"] is True and second["configs"] == []


def test_a_refresh_drops_a_photo_that_stopped_being_shared():
    facts = vf.facts()
    chosen = drafts.default_media_selection(facts)
    facts["stations"][0]["elements"][2]["shared"] = False  # the recommendation, with P_EXTRA
    kept = drafts.refreshed_selection(chosen, facts)
    assert vf.P_EXTRA not in [s["media_id"] for s in kept]


# --- the hash (W17-3) ------------------------------------------------------------------------------


def test_the_hash_is_stable_and_ignores_what_does_not_print():
    one = made(vf.facts())
    other = deepcopy(one)
    assert content.content_hash(one) == content.content_hash(other)
    assert len(content.content_hash(one)) == 64
    # Counters and the lock move without changing the page
    other["facts"]["visit"]["version"] = 99
    other["facts"]["visit"]["locked"] = True
    other["facts"]["facts_version"] = 7
    for station in other["facts"]["stations"]:
        for e in station["elements"]:
            e["version"] += 3
            e["created_by_name"] = "Someone else"
    assert content.content_hash(one) == content.content_hash(other)


def test_a_staff_only_element_does_not_change_the_hash_but_a_shared_one_does():
    base = made(vf.facts())
    before = content.content_hash(base)
    staff_only_note(base["facts"])
    assert content.content_hash(base) == before
    base["facts"]["stations"][0]["elements"][0]["title"] = "Replace the funnel, again"
    assert content.content_hash(base) != before


@pytest.mark.parametrize("change", [
    lambda c: c["narrative"].update(summary="Changed"),
    lambda c: c["media_selection"][0].update(in_body=False),
    lambda c: c["media_selection"][0].update(caption="Another caption"),
    lambda c: c["facts"]["visit"].update(follow_up_notes="Different"),
])
def test_what_people_write_or_choose_changes_the_hash(change):
    base = made(vf.facts())
    before = content.content_hash(base)
    change(base)
    assert content.content_hash(base) != before


# --- editing (W17-2) ---------------------------------------------------------------------------------


def test_an_edit_replaces_the_fields_given_and_keeps_the_rest():
    base = made(vf.facts())
    new = content.edited(base, narrative={"summary": "All done.", "stations": [
        {"station_id": vf.S1, "work_performed": "Changed the funnel\r\nand levelled it\x00"}]},
        media_selection=None)
    assert new["narrative"]["summary"] == "All done."
    assert new["narrative"]["follow_up"] == "Bring a new funnel"
    story = {s["station_id"]: s["work_performed"] for s in new["narrative"]["stations"]}
    assert story[vf.S1] == "Changed the funnel\nand levelled it"
    assert story[vf.S2] == ""
    assert base["narrative"]["summary"] == ""  # the original is untouched


def test_a_selection_edit_moves_one_photo_and_keeps_the_others():
    base = made(vf.facts())
    new = content.edited(base, narrative=None, media_selection=[
        {"media_id": vf.P_NOTE, "in_body": False, "caption": "Looking east"}])
    by_id = {s["media_id"]: s for s in new["media_selection"]}
    assert by_id[vf.P_NOTE]["in_body"] is False and by_id[vf.P_NOTE]["caption"] == "Looking east"
    assert by_id[vf.P_BEFORE]["in_body"] is True
    cleared = content.edited(base, narrative=None, media_selection=[
        {"media_id": vf.P_NOTE, "caption": None}])
    assert {s["media_id"]: s for s in cleared["media_selection"]}[vf.P_NOTE]["caption"] is None


@pytest.mark.parametrize(("narrative", "selection", "code"), [
    ({"summary": "x" * (content.SUMMARY_MAX + 1)}, None, "too_long"),
    ({"stations": [{"station_id": "nope", "work_performed": "x"}]}, None, "unknown_station"),
    (None, [{"media_id": "nope", "in_body": True}], "unknown_photo"),
    (None, [{"media_id": vf.P_NOTE, "caption": "x" * (content.CAPTION_MAX + 1)}], "too_long"),
])
def test_an_edit_the_report_cannot_take_is_refused(narrative, selection, code):
    with pytest.raises(ValidationFailed) as caught:
        content.edited(made(vf.facts()), narrative=narrative, media_selection=selection)
    assert caught.value.extra["code"] == code


def test_seven_photos_in_one_stations_body_are_too_many():
    facts = vf.facts()
    facts["stations"][0]["elements"][1]["media"]["main"] = [
        vf.media(f"01900000-0000-7000-8000-0000000f01{n:02d}") for n in range(10)]
    base = made(facts)
    appendix = [s["media_id"] for s in base["media_selection"] if not s["in_body"]]
    assert appendix
    with pytest.raises(ValidationFailed) as caught:
        content.edited(base, narrative=None,
                       media_selection=[{"media_id": appendix[0], "in_body": True}])
    assert caught.value.extra["code"] == "too_many_in_body"


# --- what a client reads (rule 6) --------------------------------------------------------------------


def test_a_client_reads_the_shared_elements_only():
    base = made(vf.facts())
    staff_only_note(base["facts"])
    seen = content.client_view(base)
    assert GATE_NOTE not in str(seen)
    assert [e["title"] for e in seen["facts"]["stations"][0]["elements"]] == [
        "Replace the rain gauge funnel", "Mast and guy wires", "Trim the tree to the east"]
    assert "01900000-0000-7000-8000-0000000f0aaa" not in str(seen)


# --- who signs and the drawing (W17-5, W17-6) -------------------------------------------------------


def test_the_lead_and_the_others_who_attended_sign_and_nobody_else():
    report = {"lead_staff_id": "lead", "staff_ids": ["lead", "other"]}
    assert signing.role_of(report, "lead") == "lead"
    assert signing.role_of(report, "other") == "attending"
    assert signing.role_of(report, "an-admin") is None


def test_a_drawn_signature_is_checked_and_a_data_uri_is_accepted():
    raw = png()
    for text in (base64.b64encode(raw).decode(), "data:image/png;base64," + base64.b64encode(raw).decode()):
        got, width, height = signing.png_bytes(text, **LIMITS)
        assert got == raw and (width, height) == (300, 120)


@pytest.mark.parametrize("bad", [
    "not base64 !!",
    base64.b64encode(b"GIF89a....").decode(),
    base64.b64encode(png()[:-12]).decode(),  # cut off: no end marker
    base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 30 + b"IEND\xaeB`\x82").decode(),  # no IHDR
])
def test_something_that_is_not_a_png_is_refused(bad):
    with pytest.raises(ValidationFailed) as caught:
        signing.png_bytes(bad, **LIMITS)
    assert caught.value.extra["code"] == "bad_signature"


def test_a_signature_that_is_too_big_in_bytes_or_pixels_is_refused():
    with pytest.raises(ValidationFailed) as caught:
        signing.png_bytes(base64.b64encode(png((1300, 100))).decode(), **LIMITS)
    assert caught.value.extra["code"] == "signature_too_large"
    with pytest.raises(ValidationFailed) as caught:
        signing.png_bytes(base64.b64encode(png()).decode(), **{**LIMITS, "max_bytes": 100})
    assert caught.value.extra["code"] == "signature_too_large"


def test_the_typed_name_is_tidied_and_must_be_a_name():
    assert signing.typed_name("  Test   Lead ") == "Test Lead"
    for bad in ("", "A", "x" * 121):
        with pytest.raises(ValidationFailed):
            signing.typed_name(bad)
