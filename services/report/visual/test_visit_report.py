"""The visit report as a picture (W16-9 and the visual baseline of IP W16): every page of a made-up
report is drawn in the report image's own fonts and compared with the committed baseline. A
template change that moves things shows up as a failing picture; a deliberate one is accepted with
`--update-baselines`, in the same commit, so the pull request shows the new pictures.

It runs only where the fonts are the image's (`MMS_VISUAL=1`, set by `visual/Dockerfile`): the same
template draws a little differently with other fonts, which says nothing about the template."""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain import client_form, client_form_view, closeout, closeout_view, drafts, visit_view
from app.repo import render
from tests import visit_facts as vf

pytestmark = pytest.mark.skipif(
    os.environ.get("MMS_VISUAL") != "1", reason="drawn in the report image (visual/Dockerfile)")

BASELINES = Path(__file__).parent / "baselines"
DPI = 80
PIXEL_TOLERANCE = 24  # a colour channel that differs by more than this counts as changed
PAGE_TOLERANCE = 0.005  # share of a page's pixels that may differ (0.5%)
NOW = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)


HASH = "3f9a1c2e4b7d8a60" + "0" * 48  # the first 16 characters are printed in a final footer


def drawn(seed: int) -> bytes:
    """A made-up signature: a looping line, nobody's real one (the repository is public)."""
    import io

    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (520, 180), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    points = [(20 + 38 * n, 100 + (60 if (n + seed) % 2 else -60) * ((n % 3) + 1) // 3)
              for n in range(13)]
    draw.line(points, fill=(20, 28, 60, 255), width=5, joint="curve")
    draw.line([(30, 150), (480, 140)], fill=(20, 28, 60, 255), width=3)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def signatures() -> list[dict]:
    attest = "I confirm the information in this report is accurate and the work described was carried out."
    return [
        {"signer_id": vf.LEAD, "role": "lead", "typed_name": "Test Lead", "attestation": attest,
         "signed_at": datetime(2026, 10, 5, 17, 3, tzinfo=UTC), "image": drawn(1)},
        {"signer_id": vf.OTHER, "role": "attending", "typed_name": "Test Helper",
         "attestation": attest, "signed_at": datetime(2026, 10, 5, 17, 9, tzinfo=UTC),
         "image": drawn(2)},
    ]


def report(facts: dict, *, status: str = "draft") -> dict:
    doc = drafts.new_draft(
        report_id="r1", number="VR-2026-0042-02", subject_ref=f"visit:{vf.VISIT}",
        visit_id=vf.VISIT, request_id=vf.REQUEST, org_id=vf.ORG, staff_ids=[vf.LEAD],
        lead_staff_id=vf.LEAD, ended_at=NOW, now=NOW)
    doc["status"] = status
    doc["content_hash"] = HASH
    doc["content"] = {
        "facts": facts, "narrative": drafts.default_narrative(facts),
        "media_selection": drafts.default_media_selection(facts)}
    return doc


def pdf_of(doc: dict, pictures: dict[str, str | None], signed: list[dict] | None = None) -> bytes:
    view = visit_view.build(
        doc, pictures, app_url="https://mms.example", generated_at=NOW, signatures=signed or [])
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


def closeout_facts(*, accepted: bool = True, version: int = 1) -> dict:
    """A made-up request, closed: nobody's real name, station or signature."""
    return {
        "facts_version": 2,
        "request": {
            "id": vf.REQUEST, "ref": "MR-2026-0042", "title": "Rain gauge not reporting",
            "category": "fault", "priority": "high", "org_id": vf.ORG,
            "org_name": "Test Weather Service", "requester_name": "Una Client",
            "created_at": "2026-09-01T14:00:00Z", "milestones": {"closed_at": "2026-10-05T16:00:00Z"},
        },
        "stations": [{"station_id": vf.S1, "code": "TST-001", "name": "Test Harbour",
                      "country": "JM", "time_zone": "America/Jamaica"}],
        "timeline": [
            {"to": "submitted", "at": "2026-09-01T14:00:00Z", "by_name": "Una Client", "note": None},
            {"to": "approved", "at": "2026-09-02T09:00:00Z", "by_name": "Test Admin", "note": None},
            {"to": "assigned", "at": "2026-09-02T09:05:00Z", "by_name": "Test Admin", "note": None},
            {"to": "client_review", "at": "2026-09-20T14:00:00Z", "by_name": None, "note": None},
            {"to": "closed", "at": "2026-10-05T16:00:00Z",
             "by_name": "Una Client" if accepted else None,
             "note": "Accepted by the client" if accepted else "Closed automatically"},
        ],
        "visits": [{"visit_id": vf.VISIT, "ref": "VR-2026-0042-02", "status": "ended",
                    "started_at": "2026-09-05T13:00:00Z", "ended_at": "2026-09-05T17:00:00Z",
                    "lead_name": "Test Lead", "report_id": "r1", "report_version": version}],
        "client_reports": [{"id": vf.OTHER, "kind": "form", "title": "Gauge check",
                            "report_date": "2026-09-30", "submitted_by_name": "Una Client",
                            "submitted_at": "2026-09-30T15:00:00Z", "report_id": None}],
        "comments": [{"author_name": "Una Client", "author_role": "client",
                      "body": "Please check the mast as well.", "created_at": "2026-09-02T10:00:00Z"},
                     {"author_name": "Test Lead", "author_role": "technician",
                      "body": "The mast is sound.", "created_at": "2026-09-05T17:30:00Z"}],
        "decision": {
            "outcome": "accepted" if accepted else "auto_closed",
            "by_name": "Una Client" if accepted else None, "at": "2026-10-05T16:00:00Z",
            "reviewing": "2026-09-05T16:00:00Z", "comment": "Thank you for the quick work." if accepted else None,
            "typed_name": "Una Client" if accepted else None,
            "attestation": "I confirm the work described in the reports above has been completed and I accept it." if accepted else None,
            "signature_png_b64": base64.b64encode(drawn(3)).decode() if accepted else None,
        },
    }


def pdf_of_closeout(facts: dict, corrections: list | None = None) -> bytes:
    doc = closeout.new_closeout(
        report_id="c1", request_id=vf.REQUEST, request_ref="MR-2026-0042", title="T",
        org_id=vf.ORG, version=2 if corrections else 1, supersedes_id=None, expects={}, now=NOW)
    doc["content_hash"] = HASH
    view = closeout_view.build(doc, facts, app_url="https://mms.example", generated_at=NOW,
                               corrections=corrections or [])
    return render.to_pdf(render.render_closeout_html(view, closeout.TEMPLATE_VERSION)).pdf


def pdf_of_form(images: bool = True) -> bytes:
    facts = {
        "facts_version": 1, "client_report_id": "x", "attempt": 1,
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
        "summary": "Readings were steady across the quarter apart from one gap. "
                   "The cups were replaced in July.",
        "observations": [{"station_id": vf.S1, "text": "The cups are worn again and turn slowly."}],
        "data_quality_notes": "No data was recorded on the 4th after a power cut.",
        "images": [{"media_id": vf.P_BEFORE, "name": "gauge.jpg"},
                   {"media_id": vf.P_AFTER, "name": "mast.jpg"}] if images else [],
    }
    doc = client_form.new_report(
        report_id="r1", client_report_id="x", report_number="CR-2026-0042-01",
        request_id=vf.REQUEST, org_id=vf.ORG, submitted_by="u1", attempt=1, now=NOW)
    doc["content_hash"] = HASH
    view = client_form_view.build(doc, facts, pictures(), generated_at=NOW)
    return render.to_pdf(render.render_client_form_html(view, client_form.TEMPLATE_VERSION)).pdf


CASES = {
    "full-draft": lambda: pdf_of(report(vf.facts()), pictures()),
    "full-final": lambda: pdf_of(report(vf.facts(), status="final"), pictures(), signatures()),
    "no-work": lambda: pdf_of(report(empty_visit()), {}),
    "closeout-accepted": lambda: pdf_of_closeout(closeout_facts()),
    "closeout-auto": lambda: pdf_of_closeout(closeout_facts(accepted=False)),
    "closeout-corrected": lambda: pdf_of_closeout(
        closeout_facts(version=2),
        [{"ref": "VR-2026-0042-02", "from": 1, "to": 2, "at": NOW}]),
    "client-form": lambda: pdf_of_form(),
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
