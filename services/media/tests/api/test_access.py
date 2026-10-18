"""Who can see and fetch a file: fail-closed visibility (ADR-19), organization scoping and
404 for anything out of scope (rules 3, 4, 6), download links, captions and deletion."""

from __future__ import annotations

import pytest
from mms_common.events import Envelope
from mms_common.events import operations as ev
from mms_common.ids import new_id

from app.events import visibility_consumer
from app.jobs.process import process_media
from tests.conftest import PDF, STATION


async def ready(media, data=PDF, **kw):
    media_id = (await media.upload(data, **kw))["media_id"]
    await process_media(media.svc, media_id)
    return media_id


async def show_to_org(media, media_ids, version=1, visibility="org") -> None:
    """Deliver `media.visibility_requested` the way the Kafka consumer does."""
    async def dlq(raw: bytes, reason: str) -> None:  # pragma: no cover
        raise AssertionError(reason)

    processor = visibility_consumer.processor(
        media.app.state.mongo, media.app.state.db, dlq, media.clock
    )
    envelope = Envelope(
        event_id=new_id(), type="media.visibility_requested", occurred_at=media.clock.now(),
        source="operations", key=STATION, aggregate_version=version,
        resource={"type": "document", "id": new_id()},
        data=ev.MediaVisibilityRequested(
            media_ids=media_ids, visibility=visibility, visibility_version=version
        ).model_dump(),
    )
    await processor.process(envelope.model_dump_json().encode())


@pytest.mark.req("MED-4")
async def test_a_file_is_staff_only_until_the_owner_shows_it(media):
    media_id = await ready(media)
    assert (await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("tech1"))
            ).status_code == 200
    # A client of the owning organization: no event yet, so the file does not exist for them.
    mine = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("client_a1"))
    assert mine.status_code == 404
    listing = await media.http.get(
        "/api/v1/media", params={"owner_ref": f"document:station:{STATION}"},
        headers=media.bearer("client_a1"),
    )
    assert listing.json()["items"] == []

    await show_to_org(media, [media_id])
    shown = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("client_a1"))
    assert shown.status_code == 200 and shown.json()["visibility"] == "org"
    # Another organization's client still can't tell it exists (rule 4).
    other = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("client_b1"))
    assert other.status_code == 404


async def test_only_the_newest_visibility_request_counts(media):
    media_id = await ready(media)
    await show_to_org(media, [media_id], version=2, visibility="org")
    await show_to_org(media, [media_id], version=1, visibility="staff")  # arrives late
    assert (await media.record(media_id))["visibility"] == "org"
    await show_to_org(media, [media_id], version=3, visibility="staff")
    assert (await media.record(media_id))["visibility"] == "staff"
    gone = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("client_a1"))
    assert gone.status_code == 404


async def test_a_request_for_unknown_files_is_not_swallowed(media):
    dead: list[str] = []

    async def dlq(raw: bytes, reason: str) -> None:
        dead.append(reason)

    async def no_sleep(seconds: float) -> None:
        return None

    processor = visibility_consumer.processor(
        media.app.state.mongo, media.app.state.db, dlq, media.clock
    )
    processor._sleep = no_sleep
    envelope = Envelope(
        event_id=new_id(), type="media.visibility_requested", occurred_at=media.clock.now(),
        source="operations", key=STATION, aggregate_version=1,
        resource={"type": "document", "id": new_id()},
        data=ev.MediaVisibilityRequested(
            media_ids=[new_id()], visibility="org", visibility_version=1
        ).model_dump(),
    )
    await processor.process(envelope.model_dump_json().encode())
    assert dead and "unknown media" in dead[0]


async def test_a_file_has_no_links_until_it_is_ready(media):
    media_id = (await media.upload())["media_id"]
    pending = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("tech1"))
    assert pending.json()["status"] == "uploaded" and pending.json()["urls"] == {}
    await process_media(media.svc, media_id)
    done = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("tech1"))
    urls = done.json()["urls"]
    view = await media.store.get(urls["view"])
    assert view.content == PDF
    assert view.headers["content-type"] == "application/pdf"
    assert view.headers["content-disposition"].startswith("inline;")
    download = await media.store.get(urls["download"])
    assert download.headers["content-disposition"].startswith("attachment;")
    assert done.headers["Cache-Control"] == "no-store"  # the links act as passwords


async def test_a_config_file_always_downloads(media):
    media_id = await ready(media, b"<xml/>", kind="config", filename="net.xml",
                           owner_ref=f"config:{STATION}")
    detail = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("tech1"))
    view = await media.store.get(detail.json()["urls"]["view"])
    assert view.headers["content-disposition"].startswith("attachment;")
    assert view.headers["content-type"].startswith("application/octet-stream")


async def test_listing_pages_through_a_station_s_files(media):
    ids = [await ready(media) for _ in range(3)]
    ref = f"document:station:{STATION}"
    first = (await media.http.get("/api/v1/media", params={"owner_ref": ref, "limit": 2},
                                  headers=media.bearer("viewer"))).json()
    assert len(first["items"]) == 2 and first["next_after"]
    second = (await media.http.get(
        "/api/v1/media", params={"owner_ref": ref, "limit": 2, "after": first["next_after"]},
        headers=media.bearer("viewer"))).json()
    got = [i["id"] for i in first["items"] + second["items"]]
    assert sorted(got) == sorted(ids) or set(ids) <= set(got)


async def test_only_the_uploader_or_staff_who_write_can_caption(media):
    media_id = await ready(media)
    ok = await media.http.patch(f"/api/v1/media/{media_id}", json={"caption": "Front panel"},
                                headers=media.bearer("admin"))
    assert ok.status_code == 200 and ok.json()["caption"] == "Front panel"
    await show_to_org(media, [media_id])
    # In scope for the client, but not theirs to change.
    no = await media.http.patch(f"/api/v1/media/{media_id}", json={"caption": "x"},
                                headers=media.bearer("client_a1"))
    assert no.status_code == 403
    out = await media.http.patch(f"/api/v1/media/{media_id}", json={"caption": "x"},
                                 headers=media.bearer("client_b1"))
    assert out.status_code == 404


async def test_an_unfinished_upload_can_be_deleted_and_its_parts_are_freed(media):
    body = (await media.create()).json()
    record = await media.record(body["media_id"])
    gone = await media.http.delete(
        f"/api/v1/media/{body['media_id']}", headers=media.bearer("tech1")
    )
    assert gone.status_code == 204
    assert (await media.record(body["media_id"]))["status"] == "deleted"
    found = media.s3.list_multipart_uploads(
        Bucket=media.settings.bucket_documents, Prefix=record["original_key"]
    )
    assert found.get("Uploads", []) == []
    assert len(await media.outbox("media.deleted")) == 1
    again = await media.http.get(f"/api/v1/media/{body['media_id']}", headers=media.bearer("tech1"))
    assert again.status_code == 404


async def test_a_stored_file_cannot_be_deleted(media):
    media_id = await ready(media)
    response = await media.http.delete(f"/api/v1/media/{media_id}", headers=media.bearer("admin"))
    assert response.status_code == 409 and response.json()["reason"] == "immutable"


async def test_only_the_uploader_or_an_admin_deletes_an_upload(media):
    body = (await media.create(who="tech1")).json()
    other = await media.http.delete(f"/api/v1/media/{body['media_id']}",
                                    headers=media.bearer("tech2"))
    assert other.status_code == 403
    admin = await media.http.delete(f"/api/v1/media/{body['media_id']}",
                                    headers=media.bearer("admin"))
    assert admin.status_code == 204


async def test_operations_can_check_a_file_and_get_a_link_only_when_it_is_ready(media):
    media_id = (await media.upload())["media_id"]
    info = await media.http.get(f"/internal/media/{media_id}", headers=media.service("operations"))
    body = info.json()
    assert body["status"] == "uploaded" and body["owner_ref"] == f"document:station:{STATION}"
    assert body["uploaded_by"]
    early = await media.http.post(f"/internal/media/{media_id}/url", json={},
                                  headers=media.service("operations"))
    assert early.status_code == 409 and early.json()["reason"] == "not_ready"
    await process_media(media.svc, media_id)
    link = await media.http.post(f"/internal/media/{media_id}/url", json={"inline": False},
                                 headers=media.service("operations"))
    assert link.status_code == 200
    assert (await media.store.get(link.json()["url"])).content == PDF
    assert link.headers["Cache-Control"] == "no-store"
    missing = await media.http.get(
        f"/internal/media/{new_id()}", headers=media.service("operations")
    )
    assert missing.status_code == 404
