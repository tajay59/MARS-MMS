"""The visit report template (PRD Appendix A, RPT-1, RPT-9, RPT-10): the HTML anywhere, and the
PDF where Pango is installed. The visual baseline comes with the template slice."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest

from app.domain import drafts, visit_view
from app.repo import render
from tests import visit_facts as vf

NOW = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)


def view(*, pictures=None, draft=True):
    facts = vf.facts()
    report = drafts.new_draft(
        report_id="r1", number="VR-2026-0042-02", subject_ref=f"visit:{vf.VISIT}",
        visit_id=vf.VISIT, request_id=vf.REQUEST, org_id=vf.ORG, staff_ids=[vf.LEAD],
        lead_staff_id=vf.LEAD, ended_at=NOW, now=NOW)
    report["content"] = {
        "facts": facts, "narrative": drafts.default_narrative(facts),
        "media_selection": drafts.default_media_selection(facts)}
    if not draft:
        report["status"] = "final"
    return visit_view.build(report, pictures or {}, app_url="https://mms.example", generated_at=NOW)


def test_the_html_has_every_section_of_the_template():
    html = render.render_visit_html(view(), "visit-1")
    for text in (
        "Site Visit Report", "VR-2026-0042-02", "Test Weather Service", "Rain gauge not reporting",
        "Test Hill", "TST-002", "Replace the rain gauge funnel", "Not finished", "Mast and guy wires",
        "Trim the tree to the east", "Version <span class=\"mono\">4</span>", "Walk round",
        "Bring a new funnel", "Calibrations coming due", "Not yet signed", "Additional visit required",
    ):
        assert text in html, text
    assert 'class="qr-small"' in html and "data:image/svg+xml" in html  # a QR code for the video
    assert "Scan to watch it in the app" in html and "clip.mp4" in html
    assert "DRAFT" in html and 'class="watermark"' in html
    assert "08:30 EST" in html and "11:30 AST" in html  # each station's own zone


def test_a_final_report_has_no_watermark():
    html = render.render_visit_html(view(draft=False), "visit-1")
    assert 'class="watermark"' not in html and "v1 · Final" in html


def test_what_people_wrote_is_escaped():
    facts = vf.facts()
    facts["stations"][0]["elements"][1]["title"] = "<script>alert(1)</script>"
    report = drafts.new_draft(
        report_id="r1", number="VR-1", subject_ref="visit:v", visit_id="v", request_id="q",
        org_id="o", staff_ids=[], lead_staff_id=vf.LEAD, ended_at=NOW, now=NOW)
    report["content"] = {"facts": facts, "narrative": drafts.default_narrative(facts),
                         "media_selection": []}
    html = render.render_visit_html(
        visit_view.build(report, {}, app_url="https://m", generated_at=NOW), "visit-1")
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_a_picture_that_is_not_ready_prints_a_box_and_a_ready_one_prints_the_photo():
    pictures = {vf.P_BEFORE: render.jpeg_data_uri(vf.webp())}
    html = render.render_visit_html(view(pictures=pictures), "visit-1")
    assert "data:image/jpeg;base64," in html and "Photo not available" in html


def test_a_display_copy_is_shrunk_and_made_a_jpeg():
    from PIL import Image

    uri = render.jpeg_data_uri(vf.webp((3000, 2000)))
    assert uri.startswith("data:image/jpeg;base64,")
    import base64

    image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert image.format == "JPEG" and max(image.size) == render.PAGE_PICTURE_PX


def test_the_pdf_carries_the_number_the_zones_and_the_draft_watermark():
    pictures = {m: render.jpeg_data_uri(vf.webp()) for m in (vf.P_BEFORE, vf.P_AFTER, vf.P_NOTE)}
    try:
        rendered = render.to_pdf(render.render_visit_html(view(pictures=pictures), "visit-1"))
    except OSError:
        pytest.skip("WeasyPrint's native libraries (Pango) are not installed here")
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(rendered.pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert rendered.pdf.startswith(b"%PDF") and rendered.pages == len(reader.pages) >= 2
    assert "VR-2026-0042-02" in text and "Site Visit Report" in text
    assert "EST" in text and "AST" in text
    assert "DRAFT" in text
    assert f"Page 1 of {rendered.pages}" in text
