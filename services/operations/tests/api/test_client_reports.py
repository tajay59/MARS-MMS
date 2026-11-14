"""Client reports, W18 slice 2 (PRD CRP-1 to CRP-5; TRD 3.2; decisions W18-9, W18-10), over the
real app: drafts private to their author, submit once and read-only for good, the events, and the
report service's answer for a form report's PDF."""

from __future__ import annotations

from typing import Any

import pytest
from mms_common.consumer import Outcome
from mms_common.events import Envelope
from mms_common.events import report as report_ev
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from app.events import consumer
from tests.api.test_config_and_owner_check import attachable
from tests.api.test_requests import act, make, two_orgs

CLIENT_A1 = SEED_USERS["client_a1"].id


async def an_approved_request(ops, who: str = "client_a1") -> dict[str, Any]:
    a, _ = await two_orgs(ops)
    request = await make(ops, who, [a["id"]])
    approved = await act(ops, "admin", request["id"], "approve")
    assert approved.status_code == 200, approved.text
    out: dict[str, Any] = approved.json()
    return out


async def start(ops, request: dict[str, Any], kind: str = "form", who: str = "client_a1",
                **fields: Any):
    return await ops.http.post(
        "/api/v1/client-reports",
        json={"request_id": request["id"], "kind": kind, **fields}, headers=ops.bearer(who),
    )


async def draft(ops, request: dict[str, Any], kind: str = "form", who: str = "client_a1",
                **fields: Any) -> dict[str, Any]:
    response = await start(ops, request, kind, who, **fields)
    assert response.status_code == 201, response.text
    out: dict[str, Any] = response.json()
    return out


async def patch(ops, report: dict[str, Any], who: str = "client_a1", **fields: Any):
    return await ops.http.patch(
        f"/api/v1/client-reports/{report['id']}", json={"version": report["version"], **fields},
        headers=ops.bearer(who),
    )


async def edited(ops, report: dict[str, Any], who: str = "client_a1", **fields: Any):
    response = await patch(ops, report, who, **fields)
    assert response.status_code == 200, response.text
    out: dict[str, Any] = response.json()
    return out


async def submit(ops, report_id: str, who: str = "client_a1"):
    return await ops.http.post(f"/api/v1/client-reports/{report_id}/submit",
                               headers=ops.bearer(who))


async def read(ops, report_id: str, who: str):
    return await ops.http.get(f"/api/v1/client-reports/{report_id}", headers=ops.bearer(who))


def upload(ops, report_id: str, who: str = "client_a1", **fields: Any) -> str:
    return ops.media.add(f"client_report:{report_id}", by=who, **fields)


async def ready_form(ops, request: dict[str, Any]) -> dict[str, Any]:
    report = await draft(ops, request, title="  Rain gauge   readings ")
    return await edited(ops, report, summary="The gauge read low for two weeks.")


def generated(report: dict[str, Any], request: dict[str, Any], outcome: str = "ready",
              attempt: int = 1) -> Envelope:
    data = report_ev.ReportGenerated(
        client_report_id=report["id"], request_id=request["id"], org_id=request["org_id"],
        report_id=new_id(), number="CR-2026-0001-01", outcome=outcome,
        pdf_sha256="b" * 64 if outcome == "ready" else None, attempt=attempt,
    )
    return Envelope(
        event_id=new_id(), type="report.generated", occurred_at=report["updated_at"],
        source="report", key=request["id"], aggregate_version=1,
        resource={"type": "report", "id": data.report_id}, data=data.model_dump(mode="json"),
    )


async def deliver_generated(ops, envelope: Envelope) -> Outcome:
    dead: list[str] = []

    async def dlq(raw: bytes, reason: str) -> None:
        dead.append(reason)

    processor = consumer.processor(ops.app.state.mongo, ops.app.state.db, dlq, ops.clock)
    outcome = await processor.process(envelope.model_dump_json().encode())
    assert dead == []
    return outcome


# --- Drafts (CRP-1, CRP-2) ----------------------------------------------------------------------


@pytest.mark.req("CRP-1")
@pytest.mark.req("CRP-2")
async def test_a_client_starts_a_draft_on_their_own_request(ops):
    request = await an_approved_request(ops)
    report = await draft(ops, request, title="  Rain gauge   readings ")
    assert report["status"] == "draft" and report["kind"] == "form"
    assert report["title"] == "Rain gauge readings"
    assert report["request_ref"] == request["ref"]
    assert report["station_ids"] == [s["id"] for s in request["stations"]]  # all, by default
    assert report["render"] == "none" and report["can_edit"] is True
    assert report["form"] == {"summary": "", "observations": [], "data_quality_notes": "",
                              "images": []}


@pytest.mark.req("CRP-1")
async def test_starting_twice_with_one_id_makes_one_draft(ops):
    request = await an_approved_request(ops)
    report_id = new_id()
    first = await start(ops, request, id=report_id)
    again = await start(ops, request, id=report_id)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"] == report_id
    clash = await start(ops, request, id=report_id, who="client_a2")
    assert clash.status_code == 409 and clash.json()["code"] == "id_taken"
    assert await ops.db["client_reports"].count_documents({}) == 1


@pytest.mark.req("CRP-1")
async def test_a_request_that_is_not_under_way_takes_no_report(ops):
    a, _ = await two_orgs(ops)
    request = await make(ops, "client_a1", [a["id"]])  # Submitted
    response = await start(ops, request)
    assert response.status_code == 409 and response.json()["code"] == "request_not_reportable"
    approved = await act(ops, "admin", request["id"], "approve")
    assert approved.status_code == 200
    assert (await start(ops, request)).status_code == 201
    cancelled = await act(ops, "admin", request["id"], "cancel", reason="Not needed")
    assert cancelled.status_code == 200, cancelled.text
    assert (await start(ops, request)).status_code == 409


@pytest.mark.req("CRP-1")
async def test_a_closed_request_still_takes_a_late_report(ops):
    request = await an_approved_request(ops)
    await ops.db["requests"].update_one({"_id": request["id"]}, {"$set": {"status": "closed"}})
    assert (await start(ops, request)).status_code == 201


@pytest.mark.req("CRP-1")
async def test_another_organizations_request_is_not_found(ops):
    request = await an_approved_request(ops)
    assert (await start(ops, request, who="client_b1")).status_code == 404
    assert (await start(ops, {"id": new_id()})).status_code == 404


@pytest.mark.req("CRP-2")
async def test_a_form_is_filled_in_a_little_at_a_time(ops):
    request = await an_approved_request(ops)
    report = await draft(ops, request)
    station = report["station_ids"][0]
    report = await edited(
        ops, report, title="Q3 check", report_date="2026-09-30",
        summary="  Readings were steady.  ", data_quality_notes="Gap on the 4th.",
        observations=[{"station_id": station, "text": " Cups worn. "},
                      {"station_id": station, "text": ""}][:1],
    )
    assert report["report_date"] == "2026-09-30"
    assert report["form"]["summary"] == "Readings were steady."
    assert report["form"]["observations"] == [{"station_id": station, "text": "Cups worn."}]
    assert report["version"] == 2
    # A change that changes nothing is not a new version
    same = await edited(ops, report, summary="Readings were steady.")
    assert same["version"] == 2


@pytest.mark.req("CRP-2")
async def test_a_stale_page_cannot_overwrite_a_newer_draft(ops):
    request = await an_approved_request(ops)
    report = await draft(ops, request)
    await edited(ops, report, summary="First")
    stale = await patch(ops, report, summary="Second")  # still holds version 1
    assert stale.status_code == 409


@pytest.mark.req("CRP-2")
async def test_stations_must_belong_to_the_request_and_notes_follow_them(ops):
    request = await an_approved_request(ops)
    report = await draft(ops, request)
    station = report["station_ids"][0]
    outside = await patch(ops, report, station_ids=[new_id()])
    assert outside.status_code == 422 and outside.json()["code"] == "unknown_station"
    noted = await edited(ops, report, observations=[{"station_id": station, "text": "Dusty"}])
    elsewhere = await patch(ops, noted, observations=[{"station_id": new_id(), "text": "x"}])
    assert elsewhere.status_code == 422
    twice = await patch(ops, noted, observations=[{"station_id": station, "text": "a"},
                                                  {"station_id": station, "text": "b"}])
    assert twice.status_code == 422 and twice.json()["code"] == "duplicate"


@pytest.mark.req("CRP-2")
async def test_a_pdf_report_has_no_form_and_a_form_report_has_no_pdf(ops):
    request = await an_approved_request(ops)
    pdf = await draft(ops, request, "pdf")
    refused = await patch(ops, pdf, summary="Text")
    assert refused.status_code == 422 and refused.json()["code"] == "wrong_kind"
    form = await draft(ops, request, "form")
    refused = await patch(ops, form, media_id=upload(ops, form["id"]))
    assert refused.status_code == 422 and refused.json()["code"] == "wrong_kind"


# --- Files --------------------------------------------------------------------------------------


@pytest.mark.req("CRP-1")
async def test_a_pdf_must_be_the_authors_clean_pdf_for_this_report(ops):
    request = await an_approved_request(ops)
    pdf = await draft(ops, request, "pdf")
    other = await draft(ops, request, "pdf")
    cases = {
        "wrong_owner": upload(ops, other["id"]),
        "not_yours": upload(ops, pdf["id"], who="client_a2"),
        "wrong_kind": upload(ops, pdf["id"], kind="image", filename="p.png"),
        "unknown_file": new_id(),
    }
    for code, media_id in cases.items():
        response = await patch(ops, pdf, media_id=media_id)
        assert response.status_code == 422 and response.json()["code"] == code, code
    waiting = await patch(ops, pdf, media_id=upload(ops, pdf["id"], status="processing"))
    assert waiting.status_code == 409
    big = await patch(ops, pdf, media_id=upload(ops, pdf["id"], size=26 * 1024 * 1024))
    assert big.status_code == 422 and big.json()["code"] == "too_large"
    good = await edited(ops, pdf, media_id=upload(ops, pdf["id"], filename="readings.pdf"))
    assert good["file"]["name"] == "readings.pdf"
    cleared = await edited(ops, good, media_id=None)
    assert cleared["file"] is None


@pytest.mark.req("CRP-1")
async def test_a_file_can_belong_to_one_report_only(ops):
    request = await an_approved_request(ops)
    first = await draft(ops, request, "pdf")
    media_id = upload(ops, first["id"])
    await edited(ops, first, media_id=media_id)
    second = await draft(ops, request, "pdf")
    # Media would never let this one through its owner check; the repo guards it anyway
    ops.media.files[media_id] = ops.media.files[media_id].__class__(
        **{**ops.media.files[media_id].__dict__, "owner_ref": f"client_report:{second['id']}"})
    clash = await patch(ops, second, media_id=media_id)
    assert clash.status_code == 409 and clash.json()["code"] == "file_in_use"


@pytest.mark.req("CRP-2")
async def test_a_form_takes_up_to_ten_pictures(ops):
    request = await an_approved_request(ops)
    form = await draft(ops, request)
    ids = [upload(ops, form["id"], kind="image", filename=f"p{i}.jpg") for i in range(10)]
    full = await edited(ops, form, image_ids=ids)
    assert [i["name"] for i in full["form"]["images"]] == [f"p{i}.jpg" for i in range(10)]
    extra = upload(ops, form["id"], kind="image", filename="p10.jpg")
    refused = await patch(ops, full, image_ids=[*ids, extra])
    assert refused.status_code == 422 and refused.json()["code"] == "too_many_files"
    fewer = await edited(ops, full, image_ids=ids[:2])
    assert len(fewer["form"]["images"]) == 2


# --- Submitting (CRP-3, CRP-4) ------------------------------------------------------------------


@pytest.mark.req("CRP-2")
async def test_a_report_must_be_complete_to_submit(ops):
    request = await an_approved_request(ops)
    form = await draft(ops, request)
    no_title = await submit(ops, form["id"])
    assert no_title.status_code == 422 and no_title.json()["field"] == "title"
    titled = await edited(ops, form, title="Check")
    no_summary = await submit(ops, titled["id"])
    assert no_summary.status_code == 422 and no_summary.json()["field"] == "summary"
    pdf = await edited(ops, await draft(ops, request, "pdf"), title="Gauge scan")
    no_file = await submit(ops, pdf["id"])
    assert no_file.status_code == 422 and no_file.json()["field"] == "media_id"
    assert await ops.outbox("client_report.submitted") == []


@pytest.mark.req("CRP-3")
@pytest.mark.req("CRP-4")
async def test_submitting_sends_the_report_for_drawing_and_locks_it(ops):
    request = await an_approved_request(ops)
    picture = None
    form = await ready_form(ops, request)
    picture = upload(ops, form["id"], kind="image", filename="gauge.jpg")
    form = await edited(ops, form, image_ids=[picture])
    done = await submit(ops, form["id"])
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["status"] == "submitted" and out["render"] == "rendering"
    assert out["submitted_by"] == {"id": CLIENT_A1, "name": SEED_USERS["client_a1"].name}
    assert out["can_edit"] is False

    (event,) = await ops.outbox("client_report.submitted")
    assert event.key == request["id"] and event.org_id == ORG_A
    assert event.data["client_report_id"] == form["id"] and event.data["kind"] == "form"
    assert event.data["attempt"] == 1 and event.data["submitted_by_id"] == CLIENT_A1
    assert "gauge read low" not in event.model_dump_json()  # the text never travels (rule 1)
    (shown,) = await ops.outbox("media.visibility_requested")
    assert shown.data["media_ids"] == [picture] and shown.data["visibility"] == "org"


@pytest.mark.req("CRP-3")
async def test_a_pdf_report_is_submitted_without_drawing(ops):
    request = await an_approved_request(ops)
    pdf = await draft(ops, request, "pdf", title="Gauge scan")
    media_id = upload(ops, pdf["id"], filename="scan.pdf")
    pdf = await edited(ops, pdf, media_id=media_id)
    out = (await submit(ops, pdf["id"])).json()
    assert out["status"] == "submitted" and out["render"] == "none"
    (shown,) = await ops.outbox("media.visibility_requested")
    assert shown.data["media_ids"] == [media_id]


@pytest.mark.req("CRP-4")
async def test_a_submitted_report_cannot_be_changed_or_sent_again(ops):
    request = await an_approved_request(ops)
    form = await ready_form(ops, request)
    first = (await submit(ops, form["id"])).json()
    again = await submit(ops, form["id"])
    assert again.status_code == 200 and again.json()["version"] == first["version"]
    assert len(await ops.outbox("client_report.submitted")) == 1
    refused = await patch(ops, first, summary="Changed my mind")
    assert refused.status_code == 409 and refused.json()["code"] == "not_a_draft"
    stored = await ops.db["client_reports"].find_one({"_id": form["id"]})
    assert stored["form"]["summary"] == "The gauge read low for two weeks."


@pytest.mark.req("CRP-4")
async def test_a_colleague_can_read_a_submitted_report_but_not_send_or_change_it(ops):
    request = await an_approved_request(ops)
    pdf = await edited(ops, await draft(ops, request, "pdf"), title="Scan")
    pdf = await edited(ops, pdf, media_id=upload(ops, pdf["id"]))
    assert (await submit(ops, pdf["id"], "client_a2")).status_code == 404  # a draft: not theirs
    await submit(ops, pdf["id"])
    assert (await read(ops, pdf["id"], "client_a2")).status_code == 200
    assert (await patch(ops, pdf, "client_a2", title="Mine")).status_code == 409


@pytest.mark.req("CRP-1")
async def test_a_request_cancelled_after_the_draft_takes_no_submission(ops):
    request = await an_approved_request(ops)
    form = await ready_form(ops, request)
    await act(ops, "admin", request["id"], "cancel", reason="Not needed")
    refused = await submit(ops, form["id"])
    assert refused.status_code == 409 and refused.json()["code"] == "request_not_reportable"


# --- Who sees what (rules 3, 4, 6) --------------------------------------------------------------


@pytest.mark.req("CRP-5")
async def test_a_draft_is_private_and_a_submitted_report_is_shared(ops):
    request = await an_approved_request(ops)
    form = await ready_form(ops, request)
    for who in ("client_a2", "client_b1", "tech1", "admin", "viewer"):
        assert (await read(ops, form["id"], who)).status_code == 404, who
        listed = await ops.http.get("/api/v1/client-reports", headers=ops.bearer(who))
        assert listed.json()["items"] == [], who
    assert (await read(ops, form["id"], "client_a1")).status_code == 200

    await submit(ops, form["id"])
    for who in ("client_a1", "client_a2", "tech1", "admin", "viewer"):
        assert (await read(ops, form["id"], who)).status_code == 200, who
    assert (await read(ops, form["id"], "client_b1")).status_code == 404  # another organization
    listed = await ops.http.get("/api/v1/client-reports", headers=ops.bearer("client_b1"))
    assert listed.json()["items"] == []


@pytest.mark.req("CRP-5")
async def test_reports_are_listed_newest_first_by_request_and_station(ops):
    request = await an_approved_request(ops)
    first = await ready_form(ops, request)
    second = await ready_form(ops, request)
    await submit(ops, first["id"])
    await submit(ops, second["id"])
    other = await ready_form(ops, request)  # a draft stays out of the staff's list
    listing = await ops.http.get(
        "/api/v1/client-reports", params={"request_id": request["id"]},
        headers=ops.bearer("tech1"))
    assert [i["id"] for i in listing.json()["items"]] == [second["id"], first["id"]]
    by_station = await ops.http.get(
        "/api/v1/client-reports", params={"station_id": request["stations"][0]["id"]},
        headers=ops.bearer("client_a1"))
    assert [i["id"] for i in by_station.json()["items"]] == [other["id"], second["id"], first["id"]]
    elsewhere = await ops.http.get(
        "/api/v1/client-reports", params={"station_id": new_id()}, headers=ops.bearer("tech1"))
    assert elsewhere.json()["items"] == []


@pytest.mark.req("NFR-6")
async def test_staff_cannot_write_client_reports(ops):
    request = await an_approved_request(ops)
    for who in ("tech1", "admin", "viewer"):
        assert (await start(ops, request, who=who)).status_code == 403


# --- The PDF of a form report -------------------------------------------------------------------


@pytest.mark.req("CRP-3")
async def test_the_report_services_answer_marks_the_pdf_ready_once(ops):
    request = await an_approved_request(ops)
    form = await ready_form(ops, request)
    await submit(ops, form["id"])
    event = generated(form, request)
    assert (await deliver_generated(ops, event)) is not None
    out = (await read(ops, form["id"], "client_a1")).json()
    assert out["render"] == "ready" and out["report_id"] == event.data["report_id"]
    version = out["version"]
    await deliver_generated(ops, generated(form, request))  # a second answer changes nothing
    assert (await read(ops, form["id"], "client_a1")).json()["version"] == version


@pytest.mark.req("CRP-3")
async def test_a_failed_pdf_can_be_tried_again_without_changing_the_report(ops):
    request = await an_approved_request(ops)
    form = await ready_form(ops, request)
    await submit(ops, form["id"])
    await deliver_generated(ops, generated(form, request, "failed"))
    failed = (await read(ops, form["id"], "client_a1")).json()
    assert failed["render"] == "failed" and failed["status"] == "submitted"

    again = (await submit(ops, form["id"])).json()
    assert again["render"] == "rendering" and again["form"] == failed["form"]
    events = await ops.outbox("client_report.submitted")
    assert [e.data["attempt"] for e in events] == [1, 2]
    assert len(await ops.outbox("media.visibility_requested")) == 0  # no files, none repeated

    # The answer to the first try arriving late is not the answer to this one
    await deliver_generated(ops, generated(form, request, "failed", attempt=1))
    assert (await read(ops, form["id"], "client_a1")).json()["render"] == "rendering"
    await deliver_generated(ops, generated(form, request, "ready", attempt=2))
    assert (await read(ops, form["id"], "client_a1")).json()["render"] == "ready"


@pytest.mark.req("CRP-3")
async def test_only_the_author_asks_for_another_try(ops):
    request = await an_approved_request(ops)
    form = await ready_form(ops, request)
    await submit(ops, form["id"])
    await deliver_generated(ops, generated(form, request, "failed"))
    assert (await submit(ops, form["id"], "client_a2")).status_code == 403


@pytest.mark.req("CRP-3")
async def test_the_report_service_reads_a_submitted_form_and_nothing_else(ops):
    request = await an_approved_request(ops)
    form = await ready_form(ops, request)
    facts = f"/internal/client-reports/{form['id']}"
    assert (await ops.http.get(facts, headers=ops.service("report"))).status_code == 404  # draft
    picture = upload(ops, form["id"], kind="image", filename="gauge.jpg")
    form = await edited(ops, form, image_ids=[picture], data_quality_notes="Gap on the 4th")
    await submit(ops, form["id"])
    got = await ops.http.get(facts, headers=ops.service("report"))
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["summary"] == "The gauge read low for two weeks."
    assert body["title"] == "Rain gauge readings" and body["attempt"] == 1
    assert body["org_name"] == "Organization A" and body["request"]["ref"] == request["ref"]
    assert body["images"] == [{"media_id": picture, "name": "gauge.jpg"}]
    assert body["stations"][0]["time_zone"] and body["data_quality_notes"] == "Gap on the 4th"
    assert (await ops.http.get(facts, headers=ops.service("platform"))).status_code == 403
    assert (await ops.http.get(facts, headers=ops.bearer("client_a1"))).status_code == 401

    pdf = await edited(ops, await draft(ops, request, "pdf"), title="Scan")
    pdf = await edited(ops, pdf, media_id=upload(ops, pdf["id"]))
    await submit(ops, pdf["id"])
    got = await ops.http.get(f"/internal/client-reports/{pdf['id']}", headers=ops.service("report"))
    assert got.status_code == 404  # a PDF report has nothing to draw


# --- Downloads ----------------------------------------------------------------------------------


@pytest.mark.req("CRP-5")
async def test_a_pdf_reports_file_and_a_forms_pictures_are_downloaded_through_links(ops):
    request = await an_approved_request(ops)
    pdf = await edited(ops, await draft(ops, request, "pdf"), title="Scan")
    media_id = upload(ops, pdf["id"], filename="scan.pdf")
    pdf = await edited(ops, pdf, media_id=media_id)
    await submit(ops, pdf["id"])
    for who in ("client_a2", "tech1"):
        got = await ops.http.get(f"/api/v1/client-reports/{pdf['id']}/download",
                                 headers=ops.bearer(who))
        assert got.status_code == 200 and got.json()["filename"] == "scan.pdf"
    foreign = await ops.http.get(f"/api/v1/client-reports/{pdf['id']}/download",
                                 headers=ops.bearer("client_b1"))
    assert foreign.status_code == 404

    form = await ready_form(ops, request)
    picture = upload(ops, form["id"], kind="image", filename="gauge.jpg")
    form = await edited(ops, form, image_ids=[picture])
    mine = await ops.http.get(f"/api/v1/client-reports/{form['id']}/attachments/{picture}/download",
                              headers=ops.bearer("client_a1"))
    assert mine.status_code == 200 and mine.json()["filename"] == "gauge.jpg"
    unknown = f"/api/v1/client-reports/{form['id']}/attachments/{new_id()}/download"
    other = await ops.http.get(unknown, headers=ops.bearer("client_a1"))
    assert other.status_code == 404
    pdf_route = await ops.http.get(f"/api/v1/client-reports/{form['id']}/download",
                                   headers=ops.bearer("client_a1"))
    assert pdf_route.status_code == 409 and pdf_route.json()["code"] == "use_report_download"


# --- The owner check media makes ----------------------------------------------------------------


async def test_only_the_author_may_upload_for_a_draft(ops):
    request = await an_approved_request(ops)
    form = await draft(ops, request)
    owner = f"client_report:{form['id']}"
    mine = await attachable(ops, owner, "client_a1")
    assert mine.status_code == 200 and mine.json() == {"org_id": ORG_A}
    for who in ("client_a2", "client_b1", "tech1", "admin", "viewer"):
        assert (await attachable(ops, owner, who)).status_code == 404, who
    assert (await attachable(ops, f"client_report:{new_id()}", "client_a1")).status_code == 404
    form = await edited(ops, form, title="Check", summary="Done")
    await submit(ops, form["id"])
    assert (await attachable(ops, owner, "client_a1")).status_code == 403  # read-only now
