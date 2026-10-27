"""Events the report service emits (TRD 8.4, 11.2). Ids and flags only: a report's text never
travels in an event (rule 1; the audit record would keep it for ever).

W16 adds `report.drafted`. W17 adds the signing and finalize events (TRD 11.2, 11.3): none of
them carries the drawn signature, a typed name or any text of the report, only ids, versions,
counts and a reason. `report.finalized` and `report.reopened` are what operations reads to set a
visit's report status (TRD 3.2). The close-out and client-report events arrive in W18.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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


class _VisitReport(_Data):
    """What every event about one version of a visit report names. `version` is the report's
    own version (the aggregate version), `number` the visit's reference."""

    report_id: str
    number: str  # VR-YYYY-NNNN-NN
    version: int
    visit_id: str
    request_id: str
    org_id: str


@register("report.signed")
class ReportSigned(_VisitReport):
    """A member of the visit signed the draft (PRD RPT-4). Keyed by the request."""

    signer_id: str
    role: Literal["lead", "attending"]
    content_version: int
    valid_signatures: int  # how many valid signatures the draft holds now


@register("report.signatures_cleared")
class ReportSignaturesCleared(_VisitReport):
    """The draft changed after it was signed, so its signatures no longer apply (TRD 11.2 step 3).
    `edit`: the narrative or the photo choice changed; `facts`: the board changed a fact."""

    count: int
    reason: Literal["edit", "facts"]


@register("report.finalized")
class ReportFinalized(_VisitReport):
    """The visit report is final and its PDF is stored (PRD RPT-4, RPT-5). Operations sets the
    visit's report status from this; platform tells the people concerned."""

    type: Literal["visit"] = "visit"
    subject_ref: str  # visit:{id}
    request_ref: str
    title: str | None = None  # the request's title
    staff_ids: list[str]
    lead_staff_id: str
    finalized_at: datetime
    finalized_by: str
    pdf_sha256: str


@register("report.finalize_failed")
class ReportFinalizeFailed(_VisitReport):
    """Finalizing stopped and the report is a draft again (TRD 11.2 step 4.5). `render_failed`:
    the PDF could not be drawn after the retries; `facts_changed`: the board changed while it
    was being finalized, so the signatures were cleared; `lock_failed`: the visit could not be
    locked."""

    reason: Literal["render_failed", "facts_changed", "lock_failed"]
    attempts: int
    request_ref: str
    title: str | None = None
    lead_staff_id: str
    signer_ids: list[str]


@register("report.reopened")
class ReportReopened(_VisitReport):
    """An admin reopened a final report for correction (PRD RPT-6). `version` is the new draft's,
    `previous_version` the one that became superseded. `request_status` is the request's status
    when it was reopened, so platform knows whether the client is told (Client Review or Closed)."""

    previous_version: int
    reason: str
    reopened_by: str
    request_ref: str
    title: str | None = None
    staff_ids: list[str]
    lead_staff_id: str
    request_status: str | None = None


@register("report.finalize_reminder")
class ReportFinalizeReminder(_VisitReport):
    """A draft is still not final after 2 or 5 working days (PRD RPT-7). `staff_ids` are the
    attending people who have not signed; at 5 days platform also tells the admins."""

    working_days: Literal[2, 5]
    request_ref: str
    title: str | None = None
    staff_ids: list[str]
    lead_staff_id: str

