"""The close-out template (PRD RPT-8, REQ-14; W18-11, W18-12): the HTML anywhere, the PDF where
Pango is installed, and the rules of the number, the hash and the version decision."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest

from app.domain import closeout, closeout_view
from app.repo import render
from tests import visit_facts as vf

NOW = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)
SIGNATURE = base64.b64encode(b"\x89PNG\r\n\x1a\n-not-really-a-png").decode()


def facts(*, accepted: bool = True, comments=None, version: int = 1):
    return {
        "facts_version": 2,
        "request": {
            "id": vf.REQUEST, "ref": "MR-2026-0042", "title": "Rain gauge not reporting",
            "category": "calibration_check", "priority": "high", "org_id": vf.ORG,
            "org_name": "Test Weather Service", "requester_name": "Una Client",
            "created_at": "2026-09-01T14:00:00Z", "milestones": {"closed_at": "2026-10-05T16:00:00Z"},
        },
        "stations": [{"station_id": vf.S1, "code": "TST-001", "name": "Test Harbour",
                      "country": "JM", "time_zone": "America/Jamaica"}],
        "timeline": [
            {"to": "submitted", "at": "2026-09-01T14:00:00Z", "by_name": "Una Client", "note": None},
            {"to": "client_review", "at": "2026-09-20T14:00:00Z", "by_name": None, "note": None},
            {"to": "closed", "at": "2026-10-05T16:00:00Z", "by_name": None, "note": "<b>x</b>"},
        ],
        "visits": [{"visit_id": vf.VISIT, "ref": "VR-2026-0042-02", "status": "ended",
                    "started_at": "2026-09-05T13:00:00Z", "ended_at": "2026-09-05T17:00:00Z",
                    "lead_name": "Test Lead", "report_id": "r1", "report_version": version}],
        "client_reports": [],
        "comments": comments or [],
        "decision": {
            "outcome": "accepted" if accepted else "auto_closed", "by_name": "Una Client",
            "at": "2026-10-05T16:00:00Z", "reviewing": "2026-09-05T16:00:00Z",
            "comment": "Thank you", "typed_name": "Una Client",
            "attestation": "I confirm the work is done.",
            "signature_png_b64": SIGNATURE if accepted else None,
        },
    }


def report(**over):
    doc = closeout.new_closeout(
        report_id="c1", request_id=vf.REQUEST, request_ref="MR-2026-0042", title="T",
        org_id=vf.ORG, version=1, supersedes_id=None, expects={}, now=NOW)
    return {**doc, **over}


def view(data=None, corrections=None, **over):
    data = data or facts(**over)
    doc = report(content_hash=closeout.content_hash(data))
    return closeout_view.build(doc, data, app_url="https://mms.example", generated_at=NOW,
                               corrections=corrections or [])


def test_the_number_follows_the_request_and_the_key_follows_the_report():
    assert closeout.number("MR-2026-0042") == "CO-2026-0042"
    assert closeout.final_key("abc") == "closeouts/abc/final.pdf"


def test_the_hash_stands_for_the_drawing_without_keeping_it():
    data = facts()
    kept = closeout.kept_facts(data)
    assert "signature_png_b64" not in kept["decision"] and len(kept["decision"]["signature_sha256"]) == 64
    other = facts()
    other["decision"]["signature_png_b64"] = base64.b64encode(b"another drawing").decode()
    assert closeout.content_hash(data) != closeout.content_hash(other)
    assert closeout.content_hash(data) == closeout.content_hash(facts())


@pytest.mark.parametrize(("latest", "version", "expected"), [
    (None, 2, "skip"),
    ({"status": "final"}, 1, "skip"),
    ({"status": "rendering"}, 2, "merge"),
    ({"status": "render_failed"}, 2, "merge"),
    ({"status": "final"}, 2, "new"),
    ({"status": "superseded"}, 3, "new"),
])
def test_the_decision_tree_for_a_visit_report_becoming_final(latest, version, expected):
    assert closeout.decide_version(latest, visit_version=version) == expected


def test_a_correction_is_waited_for_until_operations_knows_it():
    assert closeout.not_yet_known({vf.VISIT: 2}, facts(version=1))
    assert not closeout.not_yet_known({vf.VISIT: 2}, facts(version=2))
    assert not closeout.not_yet_known({}, facts(version=1))
    assert closeout.not_yet_known({"other-visit": 2}, facts(version=5))


def test_corrections_name_the_reports_whose_version_went_up():
    found = closeout.corrections(facts(version=1), facts(version=3), NOW)
    assert [(c["ref"], c["from"], c["to"]) for c in found] == [("VR-2026-0042-02", 1, 3)]
    assert closeout.corrections(facts(version=2), facts(version=2), NOW) == []
    assert closeout.corrections(None, facts(), NOW) == []


def test_the_view_writes_times_in_the_first_zone_and_counts_the_days_waited():
    v = view(accepted=False)
    assert v["closed"] == "05 Oct 2026, 11:00 EST"
    assert v["decision"]["sentence"] == (
        "Closed automatically on 05 Oct 2026, 11:00 EST after 30 days without a response.")
    assert v["category"] == "Calibration Check" and v["timeline"][1]["status"] == "Client Review"
    assert v["timeline"][1]["by"] == "System"


def test_the_html_has_every_section_and_escapes_what_people_wrote():
    comments = [{"author_name": "Una Client", "author_role": "client",
                 "body": "<script>alert(1)</script>", "created_at": "2026-09-02T10:00:00Z"}]
    corrected = [{"ref": "VR-2026-0042-02", "from": 1, "to": 2, "at": NOW}]
    html = render.render_closeout_html(
        view(facts(comments=comments, version=2), corrected), closeout.TEMPLATE_VERSION)
    for text in ("Close-out Report", "CO-2026-0042", "Test Weather Service", "Accepted by Una Client",
                 "I confirm the work is done.", "Timeline", "Client Review", "Visits and reports",
                 "VR-2026-0042-02", "Corrections", "replaced v1", "Comments", "Una Client"):
        assert text in html, text
    assert "<script>" not in html and "&lt;script&gt;" in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert 'src="data:image/png;base64,' in html
    assert 'href="https://mms.example/visit-reports/r1"' in html


def test_an_automatic_close_prints_the_sentence_and_no_signature():
    html = render.render_closeout_html(view(accepted=False), closeout.TEMPLATE_VERSION)
    assert "Closed automatically on" in html and "without a response" in html
    assert "<img" not in html and "Corrections" not in html and "Comments" not in html


def test_the_pdf_is_drawn_where_pango_is_installed():
    pytest.importorskip("weasyprint")
    try:
        rendered = render.to_pdf(
            render.render_closeout_html(view(), closeout.TEMPLATE_VERSION))
    except OSError:
        pytest.skip("Pango is not installed")
    assert rendered.pdf.startswith(b"%PDF") and rendered.pages >= 1
