"""The client form template (PRD CRP-3; W18-10): the HTML anywhere, the PDF where Pango is
installed, and the rules of the number and the view that need no I/O."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain import client_form, client_form_view
from app.repo import render
from tests import visit_facts as vf

NOW = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)
CLIENT_REPORT = "01900000-0000-7000-8000-00000000f101"


def facts(**over):
    return {
        "facts_version": 1, "client_report_id": CLIENT_REPORT, "attempt": 1,
        "request": {"id": vf.REQUEST, "ref": "MR-2026-0042", "title": "Rain gauge not reporting"},
        "org_id": vf.ORG, "org_name": "Test Weather Service", "title": "Q3 gauge check",
        "report_date": "2026-09-30", "submitted_by_name": "Una Client",
        "submitted_at": "2026-10-05T16:00:00Z",
        "stations": [
            {"station_id": vf.S1, "code": "TST-001", "name": "Test Harbour", "country": "JM",
             "time_zone": "America/Jamaica"},
            {"station_id": vf.S2, "code": "TST-002", "name": "Test Hill", "country": "JM",
             "time_zone": None},
        ],
        "summary": "Readings were steady.\nOne gap.",
        "observations": [{"station_id": vf.S1, "text": "Cups are worn."}],
        "data_quality_notes": "No data on the 4th.",
        "images": [{"media_id": vf.P_BEFORE, "name": "gauge.jpg"}], **over,
    }


def view(**over):
    data = facts(**over)
    report = client_form.new_report(
        report_id="r1", client_report_id=CLIENT_REPORT, report_number="CR-2026-0042-01",
        request_id=vf.REQUEST, org_id=vf.ORG, submitted_by="u1", attempt=1, now=NOW)
    report["content_hash"] = client_form.content_hash(data)
    return client_form_view.build(report, data, {vf.P_BEFORE: "data:image/jpeg;base64,AAAA"},
                                  generated_at=NOW), report


def test_the_number_follows_the_request():
    assert client_form.number("MR-2026-0042", 1) == "CR-2026-0042-01"
    assert client_form.number("MR-2026-0042", 12) == "CR-2026-0042-12"


def test_the_hash_ignores_the_attempt_and_changes_with_the_text():
    base = facts()
    assert client_form.content_hash(base) == client_form.content_hash({**base, "attempt": 2})
    assert client_form.content_hash(base) != client_form.content_hash(facts(summary="Other"))


def test_a_failed_report_can_be_tried_again_only_by_a_later_attempt():
    _, report = view()
    assert not client_form.can_try_again(report, 2)  # still rendering
    failed = {**report, "status": client_form.FAILED}
    assert client_form.can_try_again(failed, 2)
    assert not client_form.can_try_again(failed, 1)


def test_the_view_writes_dates_in_the_first_zone_and_pairs_notes_with_stations():
    v, report = view()
    assert v["report_date"] == "30 Sep 2026" and v["submitted"] == "05 Oct 2026, 11:00 EST"
    assert [(s["code"], s["observation"]) for s in v["stations"]] == [
        ("TST-001", "Cups are worn."), ("TST-002", "")]
    assert v["hash"] == report["content_hash"][:16]


def test_the_html_has_every_section_and_escapes_what_the_client_wrote():
    v, _ = view(summary="<script>alert(1)</script> & done", title="Gauge <b>check</b>")
    html = render.render_client_form_html(v, client_form.TEMPLATE_VERSION)
    for text in ("Client Report", "CR-2026-0042-01", "Test Weather Service", "Una Client",
                 "Observations by station", "Cups are worn.", "Data quality", "No data on the 4th.",
                 "Attachments", "gauge.jpg", "30 Sep 2026", "Rain gauge not reporting"):
        assert text in html, text
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Gauge &lt;b&gt;check&lt;/b&gt;" in html
    assert 'src="data:image/jpeg;base64,AAAA"' in html


def test_a_missing_picture_and_empty_sections_leave_no_holes():
    v, _ = view(images=[{"media_id": vf.P_AFTER, "name": "mast.jpg"}], observations=[],
                data_quality_notes="")
    html = render.render_client_form_html(v, client_form.TEMPLATE_VERSION)
    assert "Picture not available" in html and "mast.jpg" in html
    assert "Observations by station" not in html and "Data quality" not in html
    bare, _ = view(images=[])
    assert "Attachments" not in render.render_client_form_html(bare, client_form.TEMPLATE_VERSION)


def test_the_pdf_is_drawn_where_pango_is_installed():
    pytest.importorskip("weasyprint")
    v, _ = view()
    try:
        rendered = render.to_pdf(render.render_client_form_html(v, client_form.TEMPLATE_VERSION))
    except OSError:
        pytest.skip("Pango is not installed")
    assert rendered.pdf.startswith(b"%PDF") and rendered.pages >= 1
