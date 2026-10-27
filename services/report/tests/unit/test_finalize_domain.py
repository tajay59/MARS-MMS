"""Finalizing, reopening and the final page (TRD 11.2, 11.1; PRD RPT-4 to RPT-6; W17-5, W17-7,
W17-10). Pure rules, and the page drawn from them."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mms_common.errors import Conflict, Forbidden, ValidationFailed

from app.domain import drafts, finalize, visit_view
from app.repo import render
from tests import visit_facts as vf
from tests.unit.test_content_domain import png

NOW = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)
HASH = "3f9a1c2e4b7d8a60" + "0" * 48
GATE_NOTE = "Gate code is 4471"


def report(**over: Any) -> dict[str, Any]:
    facts = vf.facts()
    doc = drafts.new_draft(
        report_id="r1", number="VR-2026-0042-02", subject_ref=f"visit:{vf.VISIT}",
        visit_id=vf.VISIT, request_id=vf.REQUEST, org_id=vf.ORG, staff_ids=[vf.LEAD, vf.OTHER],
        lead_staff_id=vf.LEAD, ended_at=NOW, now=NOW)
    doc["content"] = {"facts": facts, "narrative": drafts.default_narrative(facts),
                      "media_selection": drafts.default_media_selection(facts)}
    doc["content_hash"] = HASH
    doc.update(over)
    return doc


def signature(signer: str = vf.LEAD, role: str = "lead", **over: Any) -> dict[str, Any]:
    return {"signer_id": signer, "role": role, "typed_name": "Test Lead", "valid": True,
            "attestation": "I confirm the information in this report is accurate.",
            "signed_at": NOW, "image": png(), "content_hash": HASH, **over}


# --- who may and what must be true -----------------------------------------------------------------


def test_the_lead_and_an_admin_may_finalize_and_nobody_else():
    finalize.may_finalize(report(), vf.LEAD, is_admin=False)
    finalize.may_finalize(report(), "someone-else", is_admin=True)
    with pytest.raises(Forbidden) as caught:
        finalize.may_finalize(report(), vf.OTHER, is_admin=False)
    assert caught.value.extra["code"] == "not_lead"


def test_the_leads_valid_signature_for_exactly_this_content_is_what_counts():
    doc = report()
    assert finalize.lead_signature([signature()], doc)
    assert finalize.lead_signature([signature(valid=False)], doc) is None
    assert finalize.lead_signature([signature(content_hash="other")], doc) is None
    assert finalize.lead_signature([signature(vf.OTHER, "attending")], doc) is None


@pytest.mark.parametrize(("over", "signed", "code"), [
    ({"status": "final"}, [signature()], "not_a_draft"),
    ({"status": "finalizing"}, [signature()], "not_a_draft"),
    ({"content_hash": None}, [signature()], "draft_not_ready"),
    ({}, [], "lead_not_signed"),
    ({}, [signature(vf.OTHER, "attending")], "lead_not_signed"),
])
def test_a_draft_that_is_not_ready_is_refused_with_the_reason(over, signed, code):
    with pytest.raises(Conflict) as caught:
        finalize.check_ready(report(**over), signed)
    assert caught.value.extra["code"] == code


def test_a_signed_draft_is_ready():
    finalize.check_ready(report(), [signature()])


def test_the_wait_between_tries_doubles_and_the_last_try_is_the_limit():
    assert [finalize.backoff(n, 30) for n in (1, 2, 3)] == [30, 60, 120]
    assert not finalize.out_of_tries(2, 3) and finalize.out_of_tries(3, 3)


def test_a_report_finalizing_for_too_long_is_stuck():
    doc = report(status="finalizing", finalizing_at=NOW)
    assert not finalize.is_stuck(doc, NOW + timedelta(minutes=14), 900)
    assert finalize.is_stuck(doc, NOW + timedelta(minutes=15), 900)
    assert not finalize.is_stuck({**doc, "status": "draft"}, NOW + timedelta(hours=2), 900)


def test_the_final_key_is_the_versions_own_and_the_footer_shows_sixteen_characters():
    assert finalize.final_key("r1", 2) == "visits/r1/final-v2.pdf"
    assert finalize.short_hash(HASH) == "3f9a1c2e4b7d8a60" and finalize.short_hash(None) is None


# --- reopening ----------------------------------------------------------------------------------------------


def test_a_reason_is_tidied_and_must_be_five_to_five_hundred_characters():
    assert finalize.reopen_reason("  The priority   was missing ") == "The priority was missing"
    for bad in ("", "four", " " * 10, "x" * 501):
        with pytest.raises(ValidationFailed):
            finalize.reopen_reason(bad)


def test_the_next_version_keeps_the_writing_and_starts_unsigned_and_stale():
    old = report(status="final", pdf_sha256="abc", final_pdf={"key": "k"})
    new = finalize.reopened_draft(old, report_id="r2", reason="Priority missing", by="admin",
                                  now=NOW)
    assert new["version"] == 2 and new["status"] == "draft" and new["_id"] == "r2"
    assert new["number"] == old["number"] and new["supersedes_id"] == "r1"
    assert new["content"]["narrative"] == old["content"]["narrative"]
    assert new["content"]["media_selection"] == old["content"]["media_selection"]
    assert new["content"]["media_selection"] is not old["content"]["media_selection"]
    assert new["facts_stale"] is True and new["content_version"] == 1
    assert new["draft_pdf"] is None and new["final_pdf"] is None and new["pdf_sha256"] is None
    assert new["unlock_pending"] == {"report_id": "r1", "version": 1}
    assert new["content_hash"] == HASH and new["reopened_by"] == "admin"


# --- the final page -----------------------------------------------------------------------------------------


def page(status: str = "final", signed=None, **over: Any) -> dict[str, Any]:
    doc = report(status=status, **over)
    return visit_view.build(
        doc, {}, app_url="https://mms.example", generated_at=NOW,
        signatures=[signature(), signature(vf.OTHER, "attending", typed_name="Test Helper")]
        if signed is None else signed)


def test_the_final_page_lists_each_signature_with_its_words_and_both_times():
    view = page()
    assert view["draft"] is False and view["status_word"] == "Final"
    assert view["hash"] == "3f9a1c2e4b7d8a60"
    lead, helper = view["signatures"]
    assert lead["name"] == "Test Lead" and lead["role"] == "Lead"
    assert helper["name"] == "Test Helper" and helper["role"] == "Attending"
    assert lead["uri"].startswith("data:image/png;base64,")
    assert lead["attestation"] == "I confirm the information in this report is accurate."
    assert lead["utc"] == "05 Oct 2026, 17:00 UTC" and lead["local"] == "05 Oct 2026, 12:00 EST"


def test_a_draft_page_has_no_hash_and_no_signatures():
    view = page("draft", signed=[])
    assert view["draft"] is True and view["hash"] is None and view["signatures"] == []


def test_the_final_html_has_the_footer_hash_the_signature_block_and_no_watermark():
    html = render.render_visit_html(page(), "visit-1")
    assert 'class="watermark"' not in html
    assert "v1 · Final · hash" in html and "3f9a1c2e4b7d8a60" in html
    assert html.count('class="signature"') == 2 and 'alt="Signature of Test Lead"' in html
    assert "I confirm the information in this report is accurate." in html
    assert "(05 Oct 2026, 12:00 EST)" in html and "Not yet signed" not in html


def test_the_final_pdf_says_who_signed_what_and_when_and_nothing_staff_only():
    facts = vf.facts()
    facts["stations"][0]["elements"].append(
        vf.element("note", "Access", description=GATE_NOTE, shared=False))
    doc = report(status="final")
    doc["content"] = {"facts": facts, "narrative": drafts.default_narrative(facts),
                      "media_selection": drafts.default_media_selection(facts)}
    view = visit_view.build(doc, {}, app_url="https://m", generated_at=NOW,
                            signatures=[signature(), signature(vf.OTHER, "attending",
                                                               typed_name="Test Helper")])
    try:
        rendered = render.to_pdf(render.render_visit_html(view, "visit-1"))
    except OSError:
        pytest.skip("WeasyPrint's native libraries (Pango) are not installed here")
    from pypdf import PdfReader

    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(rendered.pdf)).pages)
    for expected in ("VR-2026-0042-02", "v1", "Final", "3f9a1c2e4b7d8a60", "Test Lead",
                     "Test Helper", "I confirm the information in this report is accurate.",
                     "05 Oct 2026, 17:00 UTC", "12:00 EST"):
        assert expected in text, expected
    assert "DRAFT" not in text and GATE_NOTE not in text and "Access" not in text
