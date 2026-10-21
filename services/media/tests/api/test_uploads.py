"""The upload flow against a real store: create, send parts the way a browser does, resume,
complete, and every way it can go wrong (PRD MED-3, MED-6, OFF-6; TRD §3.3, §7.3)."""

from __future__ import annotations

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A

from tests.conftest import MODEL, PDF, STATION, MiB, sha256

OWNER_STATION = f"document:station:{STATION}"


def open_uploads(media, record):
    """The store's open multipart uploads for this file (the bucket is shared by all tests)."""
    found = media.s3.list_multipart_uploads(
        Bucket=media.settings.bucket_documents, Prefix=record["original_key"]
    )
    return found.get("Uploads", [])


@pytest.mark.req("MED-6")
async def test_a_file_goes_up_in_one_part_and_is_queued_for_its_checks(media):
    created = await media.create()
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["part_count"] == 1
    assert [u["part_number"] for u in body["urls"]] == [1]
    assert body["media"]["visibility"] == "staff"  # fail closed (ADR-19)

    await media.put_all(body, PDF)
    done = await media.complete(body["media_id"])
    assert done.status_code == 200
    assert done.json()["status"] == "uploaded"
    assert media.jobs.queued == [body["media_id"]]

    record = await media.record(body["media_id"])
    assert record["org_id"] == ORG_A
    assert record["uploaded_by"]
    assert record["original_key"].startswith(f"{ORG_A}/document-station/{STATION}/")
    assert record["original_key"].endswith("/original.pdf")
    [event] = await media.outbox("media.uploaded")
    assert event.key == body["media_id"]
    assert event.org_id == ORG_A


async def test_model_documents_belong_to_no_organization(media):
    created = await media.create(owner_ref=f"document:model:{MODEL}")
    assert created.status_code == 201
    record = await media.record(created.json()["media_id"])
    assert record["org_id"] is None
    assert record["original_key"].startswith("shared/document-model/")


async def test_creating_the_same_upload_twice_gives_the_same_upload(media):
    media_id = new_id()
    first = (await media.create(media_id=media_id)).json()
    second = (await media.create(media_id=media_id)).json()
    assert second["media_id"] == first["media_id"] == media_id
    assert not second["resumed"]
    assert len(open_uploads(media, await media.record(media_id))) == 1


async def test_a_reused_id_for_another_file_is_refused(media):
    media_id = new_id()
    await media.create(media_id=media_id)
    other = b"%PDF-1.7\n" + b"y" * 300
    response = await media.create(other, media_id=media_id)
    assert response.status_code == 409
    assert response.json()["reason"] == "media_id_reused"


async def test_someone_elses_id_is_not_found(media):
    media_id = new_id()
    await media.create(media_id=media_id, who="tech1")
    response = await media.create(media_id=media_id, who="admin")
    assert response.status_code == 404
    response = await media.http.post(
        f"/api/v1/uploads/{media_id}/parts", headers=media.bearer("admin")
    )
    assert response.status_code == 404


@pytest.mark.req("OFF-6")
async def test_parts_resume_from_what_the_store_holds(media):
    data = b"%PDF-1.7\n" + bytes(range(256)) * (11 * MiB // 256)  # 11 MiB: three 5 MiB parts
    body = (await media.create(data)).json()
    assert body["part_count"] == 3 and body["part_size"] == 5 * MiB
    urls = {u["part_number"]: u["url"] for u in body["urls"]}
    size = body["part_size"]
    await media.put_part(urls[1], data[:size])
    await media.put_part(urls[3], data[2 * size :])

    # The connection dropped. Ask where things stand.
    again = (await media.http.post(f"/api/v1/uploads/{body['media_id']}/parts",
                                   headers=media.bearer("tech1"))).json()
    assert again["parts_done"] == [1, 3]
    assert [u["part_number"] for u in again["urls"]] == [2]

    early = await media.complete(body["media_id"])
    assert early.status_code == 409
    assert early.json()["reason"] == "incomplete_upload"
    assert early.json()["missing"] == [2]
    assert (await media.record(body["media_id"]))["status"] == "pending"  # not failed

    await media.put_part(again["urls"][0]["url"], data[size : 2 * size])
    done = await media.complete(body["media_id"])
    assert done.status_code == 200 and done.json()["status"] == "uploaded"
    stored = media.s3.get_object(Bucket=media.settings.bucket_documents,
                                 Key=(await media.record(body["media_id"]))["original_key"])
    assert sha256(stored["Body"].read()) == sha256(data)


async def test_picking_the_same_file_again_continues_the_open_upload(media):
    data = b"%PDF-1.7\n" + b"z" * (6 * MiB)
    first = (await media.create(data)).json()
    await media.put_part(first["urls"][0]["url"], data[: first["part_size"]])
    # The page was reloaded: the device made a new media_id for the same file.
    second = (await media.create(data)).json()
    assert second["resumed"] is True
    assert second["media_id"] == first["media_id"]
    assert second["parts_done"] == [1]
    assert [u["part_number"] for u in second["urls"]] == [2]


async def test_complete_twice_changes_nothing(media):
    body = (await media.create()).json()
    await media.put_all(body, PDF)
    first = await media.complete(body["media_id"])
    second = await media.complete(body["media_id"])
    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == "uploaded"
    assert media.jobs.queued == [body["media_id"]]
    assert len(await media.outbox("media.uploaded")) == 1


async def test_a_file_bigger_than_announced_fails_and_is_cleaned_up(media):
    body = (await media.create(PDF, size=100)).json()  # announces 100 bytes, sends 209
    await media.put_all(body, PDF)
    response = await media.complete(body["media_id"])
    assert response.status_code == 409
    assert response.json()["reason"] == "size_mismatch"
    record = await media.record(body["media_id"])
    assert record["status"] == "failed" and record["error"] == "size_mismatch"
    assert open_uploads(media, record) == []
    [event] = await media.outbox("media.failed")
    assert event.data["reason"] == "size_mismatch"


async def test_a_lost_multipart_upload_can_not_be_resumed(media):
    body = (await media.create()).json()
    record = await media.record(body["media_id"])
    media.s3.abort_multipart_upload(
        Bucket=media.settings.bucket_documents, Key=record["original_key"],
        UploadId=record["upload_id"],
    )
    response = await media.complete(body["media_id"])
    assert response.status_code == 409 and response.json()["reason"] == "upload_lost"
    assert (await media.record(body["media_id"]))["status"] == "failed"


@pytest.mark.parametrize(("fields", "reason"), [
    ({"kind": "pdf", "filename": "manual.docx"}, "bad_type"),
    ({"kind": "document", "filename": "notes.exe"}, "bad_type"),
    ({"kind": "config", "filename": "setup.sh"}, "bad_type"),
    ({"kind": "config", "filename": "page.html"}, "bad_type"),
    ({"kind": "image", "filename": "a.exe"}, "bad_type"),
    ({"kind": "image", "filename": "a.mp4"}, "bad_type"),
    ({"kind": "video", "filename": "a.jpg"}, "bad_type"),
    ({"kind": "video", "filename": "clip"}, "bad_type"),
    ({"owner_ref": "spaceship:abc"}, "bad_owner"),
    ({"owner_ref": "nothing"}, "bad_owner"),
    ({"owner_ref": "document:station:../etc"}, "bad_owner"),
    ({"size": 50 * MiB + 1}, "too_large"),
    ({"size": 0}, None),
])
async def test_uploads_that_break_a_rule_are_refused(media, fields, reason):
    response = await media.create(**fields)
    assert response.status_code == 422
    if reason:
        assert response.json()["reason"] == reason


async def test_a_bad_checksum_or_id_is_refused_by_the_schema(media):
    for patch in ({"sha256": "ABC"}, {"media_id": "not-a-uuid"}, {"extra": 1}):
        body = {"media_id": new_id(), "owner_ref": OWNER_STATION, "kind": "pdf",
                "filename": "a.pdf", "size_bytes": 10, "sha256": sha256(b"x"), **patch}
        response = await media.http.post(
            "/api/v1/uploads", headers=media.bearer("tech1"), json=body
        )
        assert response.status_code == 422


async def test_the_filename_never_picks_the_key(media):
    body = (await media.create(filename="../../etc/passwd.pdf")).json()
    record = await media.record(body["media_id"])
    assert record["filename"] == "passwd.pdf"
    assert ".." not in record["original_key"]


@pytest.mark.req("AUTH-9")
async def test_the_owner_check_decides_who_may_attach(media):
    viewer = await media.create(who="viewer")
    assert viewer.status_code == 403  # the route refuses the role before the owner check
    other_org = await media.create(who="client_b1")
    assert other_org.status_code == 404  # outside their scope: not found (rule 4)
    unknown = await media.create(owner_ref=f"document:station:{new_id()}")
    assert unknown.status_code == 404
    assert media.owners.calls  # media asked the owning service


async def test_api_answers_are_never_cached(media):
    response = await media.create()
    assert response.headers["Cache-Control"] == "no-store"
