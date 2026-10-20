"""Turns data into PDFs (TRD §11.1): Jinja templates, then WeasyPrint.

`render_html` is plain Jinja and runs anywhere; `to_pdf` needs WeasyPrint's native libraries
(Pango), which the service image installs. The templates and `print.css` live in
`app/templates/` and ship inside the package.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import segno
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.domain.labels import TEMPLATE_VERSION, Label, paginate

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html", "j2"], default_for_string=True),
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class Rendered:
    pdf: bytes
    pages: int


class Renderer(Protocol):
    async def labels(self, labels: list[Label], phone: str | None) -> Rendered: ...


def qr_data_uri(url: str) -> str:
    """The QR code as an SVG data URI, black on white with the standard quiet zone. Level M
    survives a scuffed outdoor label; the URL is short, so the code stays coarse and easy to
    scan from a distance."""
    code = segno.make(url, error="m", micro=False)
    uri: str = code.svg_data_uri(scale=10, border=2, dark="#000000", light="#ffffff")
    return uri


def render_html(labels: list[Label], phone: str | None) -> str:
    pages = [
        [{"label": label, "qr": qr_data_uri(label.scan_url)} for label in page]
        for page in paginate(labels)
    ]
    template = _env.get_template("labels.html.j2")
    return template.render(pages=pages, phone=phone, template_version=TEMPLATE_VERSION)


def to_pdf(html: str) -> Rendered:
    from weasyprint import HTML  # noqa: PLC0415 - imports Pango; keep it out of API start-up

    document = HTML(string=html, base_url=str(TEMPLATES) + "/").render()
    return Rendered(pdf=bytes(document.write_pdf() or b""), pages=len(document.pages))


class WeasyRenderer:
    async def labels(self, labels: list[Label], phone: str | None) -> Rendered:
        html = render_html(labels, phone)
        return await asyncio.to_thread(to_pdf, html)
