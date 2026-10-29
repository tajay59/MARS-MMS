"""Turns data into PDFs (TRD §11.1): Jinja templates, then WeasyPrint.

`render_html` is plain Jinja and runs anywhere; `to_pdf` needs WeasyPrint's native libraries
(Pango), which the service image installs. The templates and `print.css` live in
`app/templates/` and ship inside the package.
"""

from __future__ import annotations

import asyncio
import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import segno
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

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

    async def visit_report(self, view: dict[str, Any], template_version: str) -> Rendered: ...

    async def client_form(self, view: dict[str, Any], template_version: str) -> Rendered: ...

    async def closeout(self, view: dict[str, Any], template_version: str) -> Rendered: ...

    async def summary(self, view: dict[str, Any], template_version: str) -> Rendered: ...


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


PAGE_PICTURE_PX = 1024  # TRD 11.1: pictures are embedded at a page-friendly size
PAGE_PICTURE_QUALITY = 82


def jpeg_data_uri(raw: bytes) -> str:
    """A photo's display copy (WebP, up to 2048 px) as a JPEG data URI at most
    `PAGE_PICTURE_PX` on the long side: smaller than the original, and something WeasyPrint
    always reads (TRD 11.1)."""
    with Image.open(io.BytesIO(raw)) as image:
        picture = image.convert("RGB")
    picture.thumbnail((PAGE_PICTURE_PX, PAGE_PICTURE_PX))
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=PAGE_PICTURE_QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def render_visit_html(view: dict[str, Any], template_version: str) -> str:
    """The visit report as HTML (TRD 11.1). `view` is `domain/visit_view.build`."""
    # The QR code beside each video links to it in the app (TRD 11.1)
    videos = [{**v, "qr": qr_data_uri(v["link"])} for v in view["videos"]]
    return _env.get_template("visit.html.j2").render(
        v={**view, "videos": videos}, template_version=template_version)


def render_client_form_html(view: dict[str, Any], template_version: str) -> str:
    """A client's online-form report as HTML (CRP-3). `view` is `domain/client_form_view.build`."""
    return _env.get_template("client_form.html.j2").render(
        v=view, template_version=template_version)


def render_closeout_html(view: dict[str, Any], template_version: str) -> str:
    """A request's close-out report as HTML (RPT-8). `view` is `domain/closeout_view.build`."""
    return _env.get_template("closeout.html.j2").render(
        v=view, template_version=template_version)


def render_summary_html(view: dict[str, Any], template_version: str) -> str:
    """A summary report as HTML (W19). `view` is `domain/summary.pdf_view`."""
    return _env.get_template("summary.html.j2").render(v=view, template_version=template_version)


def to_pdf(html: str) -> Rendered:
    from weasyprint import HTML  # noqa: PLC0415 - imports Pango; keep it out of API start-up

    document = HTML(string=html, base_url=str(TEMPLATES) + "/").render()
    return Rendered(pdf=bytes(document.write_pdf() or b""), pages=len(document.pages))


class WeasyRenderer:
    async def labels(self, labels: list[Label], phone: str | None) -> Rendered:
        html = render_html(labels, phone)
        return await asyncio.to_thread(to_pdf, html)

    async def visit_report(self, view: dict[str, Any], template_version: str) -> Rendered:
        html = render_visit_html(view, template_version)
        return await asyncio.to_thread(to_pdf, html)

    async def client_form(self, view: dict[str, Any], template_version: str) -> Rendered:
        html = render_client_form_html(view, template_version)
        return await asyncio.to_thread(to_pdf, html)

    async def closeout(self, view: dict[str, Any], template_version: str) -> Rendered:
        html = render_closeout_html(view, template_version)
        return await asyncio.to_thread(to_pdf, html)

    async def summary(self, view: dict[str, Any], template_version: str) -> Rendered:
        html = render_summary_html(view, template_version)
        return await asyncio.to_thread(to_pdf, html)
