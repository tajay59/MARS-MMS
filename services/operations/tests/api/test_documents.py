"""Documents (DOC-1 to DOC-4, MED-4, rule 6, ADR-19, BSD B4): created once their file is whole,
downloadable once media has checked it, staff-only until someone says otherwise, and shown to a
client only for their own stations and the models installed there."""

from __future__ import annotations

import pytest
from mms_common.events import Envelope
from mms_common.events import media as media_ev
from mms_common.ids import new_id
from mms_common.testing.leak import find_leaks
from mms_common.testing.seed import ORG_A, SEED_USERS

from app.events import consumer


async def make_doc(ops, station_id, *, who="tech1", status="ready", visible=False, **fields):
    media_id = ops.media.add(f"document:station:{station_id}", by=who, status=status)
    body = {
        "id": new_id(), "scope": "station", "scope_id": station_id,
        "doc_type": "installation", "title": "Installation record", "media_id": media_id,
        "client_visible": visible, **fields,
    }
    response = await ops.http.post("/api/v1/documents", json=body, headers=ops.bearer(who))
    return response, body


async def deliver(ops, event_type: str, data):
    """Hand media's event to operations' consumer, the way Kafka does."""
    dead: list[str] = []

    async def dlq(raw: bytes, reason: str) -> None:
        dead.append(reason)

    processor = consumer.processor(ops.app.state.mongo, ops.app.state.db, dlq, ops.clock)
    envelope = Envelope(
        event_id=new_id(), type=event_type, occurred_at=ops.clock.now(), source="media",
        key=data.media_id, aggregate_version=1,
        resource={"type": "media", "id": data.media_id}, data=data.model_dump(),
    )
    await processor.process(envelope.model_dump_json().encode())
    assert dead == []


def processed(media_id: str, scan: str = "clean") -> media_ev.MediaProcessed:
    return media_ev.MediaProcessed(
        media_id=media_id, owner_ref="x:y", kind="pdf", filename="a.pdf", size_bytes=1,
        scan_status=scan, checksum_sha256="0" * 64,
    )


def failed(media_id: str, reason: str = "infected") -> media_ev.MediaFailed:
    return media_ev.MediaFailed(
        media_id=media_id, owner_ref="x:y", kind="pdf", filename="a.pdf", size_bytes=1,
        reason=reason,
    )


@pytest.mark.req("DOC-2")
async def test_a_station_document_is_available_when_its_file_has_passed(ops):
    station = await ops.station()
    response, body = await make_doc(ops, station["id"])
    assert response.status_code == 201
    doc = response.json()
    assert doc["status"] == "available" and doc["scan_status"] == "clean"
    assert doc["client_visible"] is False  # staff-only by default (DOC-4, Q7)
    assert doc["uploaded_by"] == SEED_USERS["tech1"].name
    assert doc["filename"] == "manual.pdf"
    [event] = await ops.outbox("document.uploaded")
    assert event.key == station["id"] and event.org_id == ORG_A
    assert event.data["media_id"] == body["media_id"]
    assert await ops.outbox("media.visibility_requested") == []  # nothing asked of media


@pytest.mark.req("DOC-3")
async def test_a_document_waits_for_media_then_becomes_available(ops):
    station = await ops.station()
    response, body = await make_doc(ops, station["id"], status="processing")
    doc = response.json()
    assert doc["status"] == "pending"
    early = await ops.http.get(f"/api/v1/documents/{doc['id']}/download",
                               headers=ops.bearer("tech1"))
    assert early.status_code == 409 and early.json()["reason"] == "not_ready"

    await deliver(ops, "media.processed", processed(body["media_id"]))
    got = (await ops.http.get(f"/api/v1/documents/{doc['id']}", headers=ops.bearer("tech1"))).json()
    assert got["status"] == "available" and got["scan_status"] == "clean"
    assert got["version"] == 2
    [updated] = await ops.outbox("document.updated")
    assert updated.data["changed_fields"] == ["scan_status", "status"]
    link = await ops.http.get(f"/api/v1/documents/{doc['id']}/download",
                              headers=ops.bearer("tech1"))
    assert link.status_code == 200 and link.json()["filename"] == "manual.pdf"
    assert ops.media.links == [(body["media_id"], True)]
    assert link.headers["Cache-Control"] == "no-store"


async def test_a_verdict_that_beat_the_document_is_not_lost(ops):
    """Media can finish checking before the document that points at the file exists."""
    station = await ops.station()
    media_id = ops.media.add(f"document:station:{station['id']}", status="processing")
    await deliver(ops, "media.processed", processed(media_id, "skipped"))  # no document yet
    body = {"id": new_id(), "scope": "station", "scope_id": station["id"], "doc_type": "other",
            "title": "Late", "media_id": media_id}
    response = await ops.http.post("/api/v1/documents", json=body, headers=ops.bearer("tech1"))
    assert response.json()["status"] == "available"
    assert response.json()["scan_status"] == "skipped"


async def test_a_file_that_failed_its_checks_fails_the_document(ops):
    station = await ops.station()
    response, body = await make_doc(ops, station["id"], status="uploaded")
    doc = response.json()
    await deliver(ops, "media.failed", failed(body["media_id"]))
    got = (await ops.http.get(f"/api/v1/documents/{doc['id']}", headers=ops.bearer("tech1"))).json()
    assert got["status"] == "failed"
    download = await ops.http.get(f"/api/v1/documents/{doc['id']}/download",
                                  headers=ops.bearer("tech1"))
    assert download.status_code == 409 and download.json()["reason"] == "file_failed"


async def test_the_same_event_twice_changes_nothing_more(ops):
    station = await ops.station()
    response, body = await make_doc(ops, station["id"], status="processing")
    event = processed(body["media_id"])
    await deliver(ops, "media.processed", event)
    await deliver(ops, "media.processed", event)  # a new event ID but the same verdict
    got = (await ops.http.get(f"/api/v1/documents/{response.json()['id']}",
                              headers=ops.bearer("tech1"))).json()
    assert got["version"] == 2


@pytest.mark.req("DOC-3")
async def test_creating_the_same_document_twice_gives_the_same_document(ops):
    station = await ops.station()
    first, body = await make_doc(ops, station["id"])
    again = await ops.http.post("/api/v1/documents", json=body, headers=ops.bearer("tech1"))
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert len(await ops.outbox("document.uploaded")) == 1
    other = await ops.http.post("/api/v1/documents", json={**body, "media_id": new_id()},
                                headers=ops.bearer("tech1"))
    assert other.status_code == 409 and other.json()["code"] == "id_reused"


async def test_a_file_belongs_to_one_document(ops):
    station = await ops.station()
    _, body = await make_doc(ops, station["id"])
    second = await ops.http.post("/api/v1/documents", json={**body, "id": new_id()},
                                 headers=ops.bearer("tech1"))
    assert second.status_code == 409 and second.json()["code"] == "file_in_use"


@pytest.mark.parametrize(("what", "code"), [
    ("owner", "wrong_owner"), ("person", "not_yours"), ("kind", "wrong_kind"),
    ("missing", "unknown_file"), ("unfinished", "file_not_uploaded"),
    ("type", "bad_doc_type"), ("station", "unknown_target"),
])
async def test_a_document_must_use_a_file_made_for_it(ops, what, code):
    station = await ops.station()
    ref = f"document:station:{station['id']}"
    media_id = {
        "owner": ops.media.add(f"document:station:{new_id()}"),
        "person": ops.media.add(ref, by="admin"),
        "kind": ops.media.add(ref, kind="config"),
        "missing": new_id(),
        "unfinished": ops.media.add(ref, status="pending"),
        "type": ops.media.add(ref), "station": ops.media.add(ref),
    }[what]
    body = {"id": new_id(), "scope": "station", "scope_id": new_id() if what == "station"
            else station["id"], "doc_type": "datasheet" if what == "type" else "other",
            "title": "x", "media_id": media_id}
    response = await ops.http.post("/api/v1/documents", json=body, headers=ops.bearer("tech1"))
    assert response.status_code == 422 and response.json()["code"] == code


async def test_viewers_and_clients_cannot_upload(ops):
    station = await ops.station()
    for who in ("viewer", "client_a1"):
        response, _ = await make_doc(ops, station["id"], who=who)
        assert response.status_code == 403


@pytest.mark.req("DOC-4")
async def test_a_document_is_shown_to_the_owner_only_when_staff_say_so(ops):
    station = await ops.station()
    response, body = await make_doc(ops, station["id"])
    doc = response.json()
    mine = f"/api/v1/documents/{doc['id']}"
    assert (await ops.http.get(mine, headers=ops.bearer("client_a1"))).status_code == 404
    listing = await ops.http.get(f"/api/v1/documents?scope=station&scope_id={station['id']}",
                                 headers=ops.bearer("client_a1"))
    assert listing.json()["items"] == []

    shown = await ops.http.patch(mine, json={"version": doc["version"], "client_visible": True},
                                 headers=ops.bearer("tech1"))
    assert shown.status_code == 200 and shown.json()["client_visible"] is True
    [ask] = await ops.outbox("media.visibility_requested")
    assert ask.data == {"media_ids": [body["media_id"]], "visibility": "org",
                        "visibility_version": 2}
    got = await ops.http.get(mine, headers=ops.bearer("client_a1"))
    assert got.status_code == 200
    assert got.json()["media_id"] is None  # a client downloads through the document
    assert find_leaks(got.json(), own_ids=frozenset({SEED_USERS["client_a1"].id, ORG_A})) == []
    assert (await ops.http.get(mine, headers=ops.bearer("client_b1"))).status_code == 404
    link = await ops.http.get(f"{mine}/download", headers=ops.bearer("client_a1"))
    assert link.status_code == 200
    assert (await ops.http.get(f"{mine}/download",
                               headers=ops.bearer("client_b1"))).status_code == 404

    hidden = await ops.http.patch(mine, json={"version": 2, "client_visible": False},
                                  headers=ops.bearer("admin"))
    assert hidden.status_code == 200
    last = (await ops.outbox("media.visibility_requested"))[-1]
    assert last.data["visibility"] == "staff" and last.data["visibility_version"] == 3
    assert (await ops.http.get(mine, headers=ops.bearer("client_a1"))).status_code == 404


async def test_a_client_only_sees_files_that_have_passed(ops):
    station = await ops.station()
    response, body = await make_doc(ops, station["id"], status="processing", visible=True)
    doc = response.json()
    mine = f"/api/v1/documents/{doc['id']}"
    assert (await ops.http.get(mine, headers=ops.bearer("client_a1"))).status_code == 404
    await deliver(ops, "media.processed", processed(body["media_id"]))
    assert (await ops.http.get(mine, headers=ops.bearer("client_a1"))).status_code == 200


@pytest.mark.req("DOC-3")
async def test_a_new_version_replaces_the_current_one_and_keeps_the_old(ops):
    station = await ops.station()
    first, _ = await make_doc(ops, station["id"], visible=True, version_label="v1")
    old = first.json()
    second, body = await make_doc(ops, station["id"], visible=True, version_label="v2",
                                  supersedes_id=old["id"])
    assert second.status_code == 201, second.text
    new = second.json()
    assert new["supersedes_id"] == old["id"] and new["is_current"] is True

    current = (await ops.http.get(f"/api/v1/documents?scope=station&scope_id={station['id']}",
                                  headers=ops.bearer("tech1"))).json()["items"]
    assert [d["id"] for d in current] == [new["id"]]
    everything = (await ops.http.get(
        f"/api/v1/documents?scope=station&scope_id={station['id']}&current=false",
        headers=ops.bearer("tech1"))).json()["items"]
    assert {d["id"] for d in everything} == {old["id"], new["id"]}
    # The earlier version is still downloadable by staff, and hidden from clients.
    assert (await ops.http.get(f"/api/v1/documents/{old['id']}/download",
                               headers=ops.bearer("tech1"))).status_code == 200
    assert (await ops.http.get(f"/api/v1/documents/{old['id']}",
                               headers=ops.bearer("client_a1"))).status_code == 404
    asks = await ops.outbox("media.visibility_requested")
    assert [a.data["visibility"] for a in asks] == ["org", "staff", "org"]

    again = await make_doc(ops, station["id"], supersedes_id=old["id"])  # no longer current
    assert again[0].status_code == 422 and again[0].json()["code"] == "bad_supersedes"


@pytest.mark.req("DOC-1")
async def test_model_documents_follow_the_model_to_the_stations_using_it(ops):
    model = await ops.model()
    station = await ops.station()
    unit = await ops.unit(model["id"])
    media_id = ops.media.add(f"document:model:{model['id']}", filename="hmp155-manual.pdf")
    body = {"id": new_id(), "scope": "model", "scope_id": model["id"],
            "doc_type": "operations_manual", "title": "HMP155 manual", "media_id": media_id,
            "client_visible": True, "language": "en"}
    created = await ops.http.post("/api/v1/documents", json=body, headers=ops.bearer("tech1"))
    assert created.status_code == 201, created.text
    # Model-document files carry no organization in media and stay staff-only there.
    assert await ops.outbox("media.visibility_requested") == []

    path = f"/api/v1/documents?scope=model&scope_id={model['id']}"
    # Not installed anywhere yet: a client can't see it (BSD B4).
    assert (await ops.http.get(path, headers=ops.bearer("client_a1"))).json()["items"] == []
    assert (await ops.http.get(f"/api/v1/documents/{created.json()['id']}",
                               headers=ops.bearer("client_a1"))).status_code == 404
    assert (await ops.http.post(
        f"/api/v1/sensor-units/{unit['id']}/install", headers=ops.bearer("tech1"),
        json={"version": unit["version"], "station_id": station["id"], "parameter": "AT"},
    )).status_code == 200

    shown = (await ops.http.get(path, headers=ops.bearer("client_a1"))).json()["items"]
    assert [d["title"] for d in shown] == ["HMP155 manual"]
    assert (await ops.http.get(path, headers=ops.bearer("client_b1"))).json()["items"] == []
    tab = (await ops.http.get(f"/api/v1/stations/{station['id']}/documents",
                              headers=ops.bearer("client_a1"))).json()
    assert tab["station"] == [] and tab["models"][0]["model"] == "HMP155"
    assert tab["models"][0]["documents"][0]["title"] == "HMP155 manual"
    other = await ops.http.get(f"/api/v1/stations/{station['id']}/documents",
                               headers=ops.bearer("client_b1"))
    assert other.status_code == 404
    download = await ops.http.get(f"/api/v1/documents/{created.json()['id']}/download",
                                  headers=ops.bearer("client_a1"))
    assert download.status_code == 200


async def test_staff_see_a_stations_documents_and_its_sensors_manuals(ops):
    model = await ops.model()
    station = await ops.station()
    unit = await ops.unit(model["id"])
    await ops.install(unit, station)
    await make_doc(ops, station["id"], title="Site drawing", doc_type="site_drawing")
    media_id = ops.media.add(f"document:model:{model['id']}")
    await ops.http.post("/api/v1/documents", headers=ops.bearer("tech1"), json={
        "id": new_id(), "scope": "model", "scope_id": model["id"], "doc_type": "datasheet",
        "title": "Datasheet", "media_id": media_id})
    tab = (await ops.http.get(f"/api/v1/stations/{station['id']}/documents",
                              headers=ops.bearer("viewer"))).json()
    assert [d["title"] for d in tab["station"]] == ["Site drawing"]
    assert tab["models"][0]["documents"][0]["media_id"] == media_id  # staff see the file


async def test_editing_a_document_checks_the_version(ops):
    station = await ops.station()
    response, _ = await make_doc(ops, station["id"])
    doc = response.json()
    url = f"/api/v1/documents/{doc['id']}"
    ok = await ops.http.patch(url, json={"version": 1, "title": "Renamed"},
                              headers=ops.bearer("tech1"))
    assert ok.status_code == 200 and ok.json()["title"] == "Renamed"
    stale = await ops.http.patch(url, json={"version": 1, "title": "Again"},
                                 headers=ops.bearer("tech1"))
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    blank = await ops.http.patch(url, json={"version": 2, "title": None},
                                 headers=ops.bearer("tech1"))
    assert blank.status_code == 422
    wrong = await ops.http.patch(url, json={"version": 2, "doc_type": "datasheet"},
                                 headers=ops.bearer("tech1"))
    assert wrong.status_code == 422
    unchanged = await ops.http.patch(url, json={"version": 2, "title": "Renamed"},
                                     headers=ops.bearer("tech1"))
    assert unchanged.status_code == 200 and unchanged.json()["version"] == 2
    [event] = await ops.outbox("document.updated")
    assert event.data["changed_fields"] == ["title"]


async def test_a_media_outage_is_a_503_not_a_wrong_answer(ops):
    station = await ops.station()
    ops.media.down = True
    response, _ = await make_doc(ops, station["id"])
    assert response.status_code == 503 and response.json()["code"] == "media_unavailable"
