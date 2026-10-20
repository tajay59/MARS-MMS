"""The label template (QR-1, QR-6): HTML anywhere, and the PDF where Pango is installed."""

from __future__ import annotations

import re

import pytest

from app.domain.labels import PER_PAGE, Label
from app.repo import render


def make(n: int, name: str = "Kingston") -> list[Label]:
    return [
        Label(f"id{i}", f"JM-{i:03}", f"{name} {i}", "Organization A", f"https://x.example/s/t{i}")
        for i in range(n)
    ]


def test_every_label_has_its_qr_name_code_and_phone():
    html = render.render_html(make(3), "+1 876 555 0100")
    assert html.count('class="label"') == 3
    assert html.count("data:image/svg+xml") == 3
    for i in range(3):
        assert f"JM-{i:03}" in html and f"Kingston {i}" in html
    assert html.count("Call +1 876 555 0100") == 3


def test_no_phone_prints_no_phone_line():
    assert "Call" not in render.render_html(make(1), None)


def test_names_are_escaped():
    html = render.render_html(make(1, name="<script>alert(1)</script>"), None)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_a_new_sheet_starts_after_ten_labels():
    assert render.render_html(make(PER_PAGE), None).count('class="sheet"') == 1
    assert render.render_html(make(PER_PAGE + 1), None).count('class="sheet"') == 2


def test_the_qr_code_is_a_valid_svg():
    uri = render.qr_data_uri("https://mms.example/s/abc")
    assert re.match(r"^data:image/svg\+xml[;,]", uri)


def test_a_sheet_holds_the_labels_the_stylesheet_lays_out():
    """`print.css` fits 2 x 5 labels of 98 x 55 mm on 196 x 275 mm; the domain says 10."""
    css = (render.TEMPLATES / "print.css").read_text(encoding="utf-8")
    assert "width: 196mm" in css and "height: 275mm" in css
    assert "width: 98mm" in css and "height: 55mm" in css
    assert 196 // 98 * (275 // 55) == PER_PAGE


def test_the_pdf_has_one_page_per_ten_labels():
    try:
        rendered = render.to_pdf(render.render_html(make(PER_PAGE + 3), "+1 876 555 0100"))
    except OSError:
        pytest.skip("WeasyPrint's native libraries (Pango) are not installed here")
    assert rendered.pdf.startswith(b"%PDF") and rendered.pages == 2
