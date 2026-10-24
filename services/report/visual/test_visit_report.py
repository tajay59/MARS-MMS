"""The visit report as a picture (W16-9 and the visual baseline of IP W16): every page of a made-up
report is drawn in the report image's own fonts and compared with the committed baseline. A
template change that moves things shows up as a failing picture; a deliberate one is accepted with
`--update-baselines`, in the same commit, so the pull request shows the new pictures.

It runs only where the fonts are the image's (`MMS_VISUAL=1`, set by `visual/Dockerfile`): the same
template draws a little differently with other fonts, which says nothing about the template."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain import drafts, visit_view
from app.repo import render
from tests import visit_facts as vf

pytestmark = pytest.mark.skipif(
    os.environ.get("MMS_VISUAL") != "1", reason="drawn in the report image (visual/Dockerfile)")

BASELINES = Path(__file__).parent / "baselines"
DPI = 80
PIXEL_TOLERANCE = 24  # a colour channel that differs by more than this counts as changed
PAGE_TOLERANCE = 0.005  # share of a page's pixels that may differ (0.5%)
NOW = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)


def report(facts: dict, *, status: str = "draft") -> dict:
    doc = drafts.new_draft(
        report_id="r1", number="VR-2026-0042-02", subject_ref=f"visit:{vf.VISIT}",
        visit_id=vf.VISIT, request_id=vf.REQUEST, org_id=vf.ORG, staff_ids=[vf.LEAD],
        lead_staff_id=vf.LEAD, ended_at=NOW, now=NOW)
    doc["status"] = status
    doc["content"] = {
        "facts": facts, "narrative": drafts.default_narrative(facts),
        "media_selection": drafts.default_media_selection(facts)}
    return doc


def pdf_of(doc: dict, pictures: dict[str, str | None]) -> bytes:
    view = visit_view.build(doc, pictures, app_url="https://mms.example", generated_at=NOW)
    return render.to_pdf(render.render_visit_html(view, "visit-1")).pdf


def pages(pdf: bytes):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf)
    return [document[i].render(scale=DPI / 72).to_pil().convert("RGB") for i in range(len(document))]


def pictures() -> dict[str, str | None]:
    colours = {vf.P_BEFORE: "#2a6f97", vf.P_AFTER: "#3b8b5a", vf.P_NOTE: "#c26a1b",
               vf.P_EXTRA: "#7a5ab0"}
    out: dict[str, str | None] = {m: render.jpeg_data_uri(vf.webp(colour=c))
                                  for m, c in colours.items()}
    out[f"poster:{vf.VIDEO}"] = render.jpeg_data_uri(vf.webp((640, 360), "#444444"))
    return out


def empty_visit() -> dict:
    facts = vf.facts()
    facts["visit"]["additional_visit_required"] = False
    facts["visit"]["follow_up_notes"] = None
    for station in facts["stations"]:
        station["elements"] = []
    return facts


CASES = {
    "full-draft": lambda: pdf_of(report(vf.facts()), pictures()),
    "full-final": lambda: pdf_of(report(vf.facts(), status="final"), pictures()),
    "no-work": lambda: pdf_of(report(empty_visit()), {}),
}


def changed_share(now, before) -> float:
    from PIL import ImageChops

    if now.size != before.size:
        return 1.0
    grey = ImageChops.difference(now, before).convert("L")
    changed = sum(grey.histogram()[PIXEL_TOLERANCE + 1:])
    return changed / (now.size[0] * now.size[1])


@pytest.mark.parametrize("name", CASES)
def test_the_report_looks_as_it_did(name, request):
    from PIL import Image

    drawn = pages(CASES[name]())
    update = request.config.getoption("--update-baselines")
    out = Path(os.environ.get("MMS_VISUAL_OUT", "")) if os.environ.get("MMS_VISUAL_OUT") else None
    BASELINES.mkdir(exist_ok=True)
    existing = sorted(BASELINES.glob(f"{name}-p*.png"))
    if update:
        for old in existing:
            old.unlink()
        for number, page in enumerate(drawn, 1):
            page.save(BASELINES / f"{name}-p{number}.png", optimize=True)
        return
    assert existing, f"no baseline for {name}: run with --update-baselines"
    problems = []
    if len(existing) != len(drawn):
        problems.append(f"{name}: {len(drawn)} pages, the baseline has {len(existing)}")
    for number, (page, path) in enumerate(zip(drawn, existing, strict=False), 1):
        share = changed_share(page, Image.open(path).convert("RGB"))
        if share > PAGE_TOLERANCE:
            problems.append(f"{name} page {number}: {share:.2%} of the pixels changed")
            if out:
                out.mkdir(parents=True, exist_ok=True)
                page.save(out / f"{name}-p{number}.now.png")
    assert not problems, "; ".join(problems)
