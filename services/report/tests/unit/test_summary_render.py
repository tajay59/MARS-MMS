"""A summary report as a page (W19-8): the HTML says what it covers, who made it and that it is
not signed, and the PDF is drawn where Pango is installed (the service image has it)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain import summary
from app.domain.summary import Kind
from app.repo import render

NOW = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
STATIONS = {"s1": {"_id": "s1", "code": "JM-KIN-001", "name": "Kingston <b>", "country": "Jamaica",
                   "status": "operational"}}


def view(rows: bool = True) -> dict:
    doc = summary.build(Kind.NETWORK_STATUS, {
        "stations": STATIONS if rows else {}, "last_visit": {"s1": NOW}, "open_requests": {"s1": 3},
        "overdue_units": {}})
    return summary.pdf_view(doc, subtitle="Every station.", filters="as of 2026-10-28 · 1 stations",
                            zone="America/Jamaica", generated_at=NOW, generated_by="Andrea Wright")


def test_the_page_names_the_report_its_filters_and_who_made_it():
    html = render.render_summary_html(view(), summary.TEMPLATE_VERSION)
    assert "<h1>Network status</h1>" in html and "Every station." in html
    assert "as of 2026-10-28" in html and "JM-KIN-001" in html
    assert "Generated 2026-10-28 10:00 by Andrea Wright" in html
    assert "times in America/Jamaica" in html and "not signed" in html
    assert 'class="r"' in html  # the numbers are right-aligned
    assert "Open requests" in html


def test_text_from_a_station_name_cannot_add_markup():
    html = render.render_summary_html(view(), summary.TEMPLATE_VERSION)
    assert "Kingston &lt;b&gt;" in html and "Kingston <b>" not in html


def test_an_empty_report_says_so_and_still_has_its_heading():
    html = render.render_summary_html(view(rows=False), summary.TEMPLATE_VERSION)
    assert "Nothing matches these filters." in html and "<h1>Network status</h1>" in html


def test_the_pdf_is_drawn_where_pango_is_installed():
    pytest.importorskip("weasyprint")
    try:
        rendered = render.to_pdf(render.render_summary_html(view(), summary.TEMPLATE_VERSION))
    except OSError:
        pytest.skip("Pango is not installed")
    assert rendered.pdf.startswith(b"%PDF") and rendered.pages == 1
