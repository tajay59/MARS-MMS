"""A draft's rules and the page's words (TRD 11.2, W16-3 to W16-5, W16-10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain import drafts, numbering, visit_view
from tests import visit_facts as vf

T0 = datetime(2026, 10, 5, 16, 40, tzinfo=UTC)


def test_the_narrative_starts_from_notes_recommendations_and_follow_up():
    narrative = drafts.default_narrative(vf.facts())
    first = next(s for s in narrative["stations"] if s["station_id"] == vf.S1)
    assert first["work_performed"] == "Mast and guy wires: All tight"
    assert narrative["recommendations"] == "TST-001: Trim the tree to the east (high)"
    assert narrative["follow_up"] == "Bring a new funnel"
    assert narrative["summary"] == ""


def test_the_default_selection_takes_a_tasks_before_and_after_first_and_six_a_station():
    facts = vf.facts()
    selection = drafts.default_media_selection(facts)
    ids = [s["media_id"] for s in selection]
    assert ids[:2] == [vf.P_BEFORE, vf.P_AFTER]
    assert vf.VIDEO not in ids  # video has its own section
    assert all(s["in_body"] for s in selection)
    # Ten photos on one station: six in the body, four for the appendix
    station = facts["stations"][0]
    station["elements"][1]["media"]["main"] = [
        vf.media(f"01900000-0000-7000-8000-0000000f01{n:02d}") for n in range(10)]
    selection = drafts.default_media_selection(facts)
    assert sum(1 for s in selection if s["in_body"]) == drafts.PER_STATION_IN_BODY


def test_a_refresh_keeps_what_people_chose_and_adds_new_photos_to_the_appendix():
    facts = vf.facts()
    chosen = drafts.default_media_selection(facts)
    chosen[0]["caption"] = "Edited caption"
    chosen[0]["in_body"] = False
    facts["stations"][0]["elements"][1]["media"]["main"].append(vf.media("01900000-0000-7000-8000-0000000f0999"))
    facts["stations"][0]["elements"][2]["media"]["main"] = []  # the photo of the tree was removed
    kept = drafts.refreshed_selection(chosen, facts)
    by_id = {s["media_id"]: s for s in kept}
    assert by_id[chosen[0]["media_id"]]["caption"] == "Edited caption"
    assert by_id[chosen[0]["media_id"]]["in_body"] is False
    assert by_id["01900000-0000-7000-8000-0000000f0999"]["in_body"] is False
    assert vf.P_EXTRA not in by_id


def test_files_still_processing_are_waited_for_and_unknown_ones_are_not():
    facts = vf.facts()
    states = {vf.P_BEFORE: "ready", vf.P_AFTER: "processing", vf.P_NOTE: "uploaded",
              vf.P_EXTRA: "failed", vf.VIDEO: None}
    assert drafts.pending_media(facts, states) == [vf.P_AFTER, vf.P_NOTE]


def _draft(**over):
    doc = drafts.new_draft(
        report_id="r1", number="VR-2026-0042-02", subject_ref="visit:v1", visit_id="v1",
        request_id="q1", org_id="o1", staff_ids=["u1"], lead_staff_id="u1", ended_at=T0, now=T0)
    doc["facts_stale"] = False
    doc["content"]["facts"] = vf.facts()
    return {**doc, **over}


def test_the_first_pdf_waits_for_files_but_only_five_minutes():
    wait = timedelta(minutes=5)
    ready = _draft()
    assert drafts.ready_to_render(ready, T0, wait)
    waiting = _draft(awaiting_media=[vf.VIDEO])
    assert not drafts.ready_to_render(waiting, T0 + timedelta(minutes=4, seconds=59), wait)
    assert drafts.ready_to_render(waiting, T0 + timedelta(minutes=5), wait)


def test_nothing_is_drawn_without_facts_while_stale_twice_or_after_the_first_pdf():
    wait = timedelta(minutes=5)
    assert not drafts.ready_to_render(_draft(facts_stale=True), T0, wait)
    nofacts = _draft()
    nofacts["content"]["facts"] = None
    assert not drafts.ready_to_render(nofacts, T0, wait)
    busy = _draft()
    busy["render"]["state"] = "queued"
    assert not drafts.ready_to_render(busy, T0, wait)
    assert not drafts.ready_to_render(_draft(draft_pdf={"content_version": 1, "facts_version": 1}), T0, wait)
    assert not drafts.ready_to_render(_draft(status="final"), T0, wait)


def test_a_pdf_is_current_only_for_the_versions_it_was_drawn_from():
    pdf = {"content_version": 1, "facts_version": 2}
    assert drafts.pdf_is_current(_draft(draft_pdf=pdf, facts_version=2))
    assert not drafts.pdf_is_current(_draft(draft_pdf=pdf, facts_version=3))
    assert not drafts.pdf_is_current(_draft(draft_pdf=None))


def test_numbers_and_file_names():
    assert numbering.visit_report_number("VR-2026-0042-02") == "VR-2026-0042-02"
    assert numbering.file_name("VR-2026-0042-02", 1, draft=True) == "VR-2026-0042-02-v1-draft.pdf"
    assert numbering.file_name("VR-2026-0042-02", 2, draft=False) == "VR-2026-0042-02-v2.pdf"


def test_times_are_written_in_the_stations_zone_with_its_abbreviation():
    assert visit_view.local("2026-10-05T16:40:00Z", "America/Jamaica") == "05 Oct 2026, 11:40 EST"
    assert visit_view.local("2026-10-05T16:40:00Z", "America/Port_of_Spain") == "05 Oct 2026, 12:40 AST"
    assert visit_view.local("2026-10-05T16:40:00Z", None).endswith("16:40 UTC")
    assert visit_view.local("2026-10-05T16:40:00Z", "Nowhere/Land").endswith("UTC")
    assert visit_view.local(None, "America/Jamaica") == "-"


def _view(pictures=None):
    report = _draft()
    report["content"]["narrative"] = drafts.default_narrative(vf.facts())
    report["content"]["media_selection"] = drafts.default_media_selection(vf.facts())
    return visit_view.build(
        report, pictures or {}, app_url="https://mms.example/", generated_at=T0)


def test_the_view_has_the_header_the_stations_and_the_outcome():
    view = _view({vf.P_BEFORE: "data:image/jpeg;base64,AA=="})
    assert view["number"] == "VR-2026-0042-02" and view["draft"] is True
    assert view["outcome"] == "Additional visit required"
    assert [p["name"] for p in view["staff"]] == ["Test Lead", "Test Helper"]
    assert view["staff"][0]["lead"] is True
    assert view["started"] == "05 Oct 2026, 08:20 EST"
    first, second = view["stations"]
    assert first["arrived"] == "05 Oct 2026, 08:30 EST" and first["coordinates"] == "18.01230, -76.78910"
    assert second["arrived"] == "05 Oct 2026, 11:30 AST" and second["coordinates"] is None
    task = first["tasks"][0]
    assert task["incomplete"] is True and task["before"][0]["uri"].startswith("data:image/jpeg")
    assert task["after"][0]["uri"] is None  # not ready: the page prints a grey box
    assert second["configs"][0]["versions"][0]["version"] == 4
    assert view["calibrations_due"] == [{"code": "TST-001", "due": "30 Nov 2026, 19:00 EST"}]


def test_a_video_has_a_link_and_a_photo_outside_the_body_goes_to_the_appendix():
    facts = vf.facts()
    report = _draft()
    report["content"]["narrative"] = drafts.default_narrative(facts)
    selection = drafts.default_media_selection(facts)
    selection[0]["in_body"] = False
    report["content"]["media_selection"] = selection
    view = visit_view.build(report, {}, app_url="https://mms.example/", generated_at=T0)
    assert view["videos"][0]["link"] == f"https://mms.example/visits/{vf.VISIT}/media/{vf.VIDEO}"
    assert [a["media_id"] for a in view["appendix"]] == [selection[0]["media_id"]]


def test_a_visit_with_nothing_on_its_boards_says_so():
    facts = vf.facts()
    for s in facts["stations"]:
        s["elements"] = []
    report = _draft()
    report["content"]["facts"] = facts
    report["content"]["narrative"] = drafts.default_narrative(facts)
    view = visit_view.build(report, {}, app_url="https://m/", generated_at=T0)
    assert view["no_work"] is True and all(s["empty"] for s in view["stations"])
