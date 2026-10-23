"""Events the report service emits (TRD 8.4, 11.2). Ids and flags only: a report's text never
travels in an event (rule 1; the audit record would keep it for ever).

W16 adds `report.drafted`. `report.finalized`, `report.reopened` and the rest arrive with the
slices that build them (Phase 6, W17 and W18).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from mms_common.events.registry import register


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


@register("report.drafted")
class ReportDrafted(_Data):
    """The first draft PDF of a visit report is ready to preview (PRD RPT-1, Appendix B "Visit
    ended (draft report ready)"). Keyed by `request_id` (TRD 8.1) and versioned by the report."""

    report_id: str
    number: str  # VR-YYYY-NNNN-NN
    version: int
    visit_id: str
    request_id: str
    request_ref: str
    org_id: str
    title: str | None = None  # the request's title
    staff_ids: list[str]
    lead_staff_id: str
