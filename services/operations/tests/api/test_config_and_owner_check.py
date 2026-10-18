"""Configuration versions (CFG-1 to CFG-3, rule 6), calibration certificates, and the owner
check media makes on every upload (TRD §3.3)."""

from __future__ import annotations

import pytest
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, SEED_USERS

from tests.api.test_sensors import iso


def config_file(ops, station_id, name, *, sha=None, by="tech1", status="ready"):
    return ops.media.add(f"config:{station_id}", by=by, kind="config", filename=name,
                         sha=sha, status=status)


async def new_version(ops, station_id, names, *, who="tech1", **fields):
    files = [config_file(ops, station_id, n, sha=(sha_for(n, fields.pop("content", "a"))))
             for n in names]
    body = {"id": new_id(), "files": [{"media_id": m} for m in files],
            "notes": "Changed the sampling interval", **fields}
    response = await ops.http.post(f"/api/v1/stations/{station_id}/config-versions", json=body,
                                   headers=ops.bearer(who))
    return response, body, files


def sha_for(name: str, content: str) -> str:
    return (name + content).encode().hex().ljust(64, "0")[:64]


@pytest.mark.req("CFG-2")
async def test_versions_are_numbered_per_station(ops):
    station = await ops.station()
    other = await ops.station(code="JM-OTH-001", external_id="X-1")
    one, _, files = await new_version(ops, station["id"], ["logger.cr1", "modem.xml"])
    assert one.status_code == 201, one.text
    body = one.json()
    assert body["version"] == 1 and [f["filename"] for f in body["files"]] == [
        "logger.cr1", "modem.xml"]
    assert body["files"][0]["media_id"] == files[0]
    assert body["created_by"] == SEED_USERS["tech1"].name
    two, _, _ = await new_version(ops, station["id"], ["logger.cr1"])
    assert two.status_code == 201, two.text
    assert two.json()["version"] == 2
    elsewhere, _, _ = await new_version(ops, other["id"], ["x.cfg"])
    assert elsewhere.json()["version"] == 1  # numbering is per station

    listed = (await ops.http.get(f"/api/v1/stations/{station['id']}/config-versions",
                                 headers=ops.bearer("viewer"))).json()
    assert [v["version"] for v in listed] == [2, 1]
    events = await ops.outbox("config.version_created")
    assert [(e.key, e.data["version"], e.data["file_count"]) for e in events] == [
        (station["id"], 1, 2), (station["id"], 2, 1), (other["id"], 1, 1)]
    got = (await ops.http.get(f"/api/v1/stations/{station['id']}", headers=ops.bearer("tech1"))
           ).json()
    assert got["current_config_version"] == 2


async def test_creating_a_version_twice_gives_the_same_version(ops):
    station = await ops.station()
    first, body, _ = await new_version(ops, station["id"], ["a.cfg"])
    again = await ops.http.post(f"/api/v1/stations/{station['id']}/config-versions", json=body,
                                headers=ops.bearer("tech1"))
    assert again.status_code == 200 and again.json()["version"] == first.json()["version"] == 1
    assert len(await ops.outbox("config.version_created")) == 1
    changed = await ops.http.post(
        f"/api/v1/stations/{station['id']}/config-versions",
        json={**body, "files": [{"media_id": config_file(ops, station["id"], "b.cfg")}]},
        headers=ops.bearer("tech1"))
    assert changed.status_code == 409 and changed.json()["code"] == "id_reused"


async def test_only_files_that_passed_their_checks_go_into_a_version(ops):
    station = await ops.station()
    waiting = config_file(ops, station["id"], "a.cfg", status="processing")
    body = {"id": new_id(), "files": [{"media_id": waiting}]}
    url = f"/api/v1/stations/{station['id']}/config-versions"
    early = await ops.http.post(url, json=body, headers=ops.bearer("tech1"))
    assert early.status_code == 409 and early.json()["reason"] == "file_not_ready"
    ops.media.files[waiting] = ops.media.files[waiting].__class__(
        **{**vars(ops.media.files[waiting]), "status": "ready"})
    assert (await ops.http.post(url, json=body, headers=ops.bearer("tech1"))).status_code == 201


async def test_a_file_belongs_to_one_version(ops):
    station = await ops.station()
    _, body, files = await new_version(ops, station["id"], ["a.cfg"])
    again = await ops.http.post(
        f"/api/v1/stations/{station['id']}/config-versions",
        json={"id": new_id(), "files": [{"media_id": files[0]}]}, headers=ops.bearer("tech1"))
    assert again.status_code == 409 and again.json()["code"] == "file_in_use"


@pytest.mark.parametrize(("what", "code"), [
    ("owner", "wrong_owner"), ("person", "not_yours"), ("kind", "wrong_kind"),
    ("missing", "unknown_file"),
])
async def test_a_version_must_use_files_made_for_it(ops, what, code):
    station = await ops.station()
    ref = f"config:{station['id']}"
    media_id = {
        "owner": ops.media.add(f"config:{new_id()}", kind="config"),
        "person": ops.media.add(ref, kind="config", by="admin"),
        "kind": ops.media.add(ref, kind="pdf"), "missing": new_id(),
    }[what]
    response = await ops.http.post(
        f"/api/v1/stations/{station['id']}/config-versions",
        json={"id": new_id(), "files": [{"media_id": media_id}]}, headers=ops.bearer("tech1"))
    assert response.status_code == 422 and response.json()["code"] == code


async def test_a_version_needs_distinct_files(ops):
    station = await ops.station()
    url = f"/api/v1/stations/{station['id']}/config-versions"
    one = config_file(ops, station["id"], "a.cfg")
    twice = await ops.http.post(url, json={"id": new_id(), "files": [{"media_id": one}] * 2},
                                headers=ops.bearer("tech1"))
    assert twice.status_code == 422 and twice.json()["code"] == "duplicate_file"
    same_name = [config_file(ops, station["id"], "A.cfg"), config_file(ops, station["id"], "a.cfg")]
    named = await ops.http.post(url, json={"id": new_id(), "files": [
        {"media_id": m} for m in same_name]}, headers=ops.bearer("tech1"))
    assert named.status_code == 422 and named.json()["code"] == "duplicate_filename"
    empty = await ops.http.post(url, json={"id": new_id(), "files": []},
                                headers=ops.bearer("tech1"))
    assert empty.status_code == 422


async def test_configuration_is_for_staff_and_viewers_cannot_write(ops):
    station = await ops.station()
    url = f"/api/v1/stations/{station['id']}/config-versions"
    assert (await ops.http.get(url, headers=ops.bearer("client_a1"))).status_code == 403
    response, _, _ = await new_version(ops, station["id"], ["a.cfg"], who="viewer")
    assert response.status_code == 403


@pytest.mark.req("CFG-3")
async def test_the_difference_between_two_versions_is_by_checksum(ops):
    station = await ops.station()
    sid = station["id"]
    shared = sha_for("modem.xml", "same")
    one = ops.media
    first = [one.add(f"config:{sid}", kind="config", filename="logger.cr1", sha=sha_for("l", "1")),
             one.add(f"config:{sid}", kind="config", filename="modem.xml", sha=shared),
             one.add(f"config:{sid}", kind="config", filename="old.txt", sha=sha_for("o", "1"))]
    second = [one.add(f"config:{sid}", kind="config", filename="logger.cr1", sha=sha_for("l", "2")),
              one.add(f"config:{sid}", kind="config", filename="modem.xml", sha=shared),
              one.add(f"config:{sid}", kind="config", filename="new.txt", sha=sha_for("n", "1"))]
    url = f"/api/v1/stations/{sid}/config-versions"
    for files in (first, second):
        made = await ops.http.post(url, json={"id": new_id(), "files": [
            {"media_id": m} for m in files]}, headers=ops.bearer("tech1"))
        assert made.status_code == 201, made.text
    diff = (await ops.http.get(f"{url}/2/diff", headers=ops.bearer("viewer"))).json()
    assert diff == {"version": 2, "against": 1, "added": ["new.txt"], "removed": ["old.txt"],
                    "changed": ["logger.cr1"], "unchanged": ["modem.xml"]}
    first_diff = (await ops.http.get(f"{url}/1/diff", headers=ops.bearer("viewer"))).json()
    assert first_diff["against"] is None and len(first_diff["added"]) == 3
    explicit = (await ops.http.get(f"{url}/2/diff?against=1", headers=ops.bearer("viewer"))).json()
    assert explicit == diff
    assert (await ops.http.get(f"{url}/2/diff?against=7", headers=ops.bearer("viewer"))
            ).status_code == 404
    assert (await ops.http.get(f"{url}/9", headers=ops.bearer("viewer"))).status_code == 404
    assert (await ops.http.get(f"{url}/1", headers=ops.bearer("viewer"))).json()["version"] == 1


# --- the owner check media makes ---------------------------------------------------------------


async def attachable(ops, owner_ref, who="tech1", service="media"):
    user = SEED_USERS[who]
    return await ops.http.get(
        "/internal/attachable",
        params={"owner_ref": owner_ref, "user_id": user.id, "roles": ",".join(user.roles),
                "org_id": user.org_id or ""},
        headers=ops.service(service),
    )


async def test_staff_may_attach_to_a_station_and_the_file_takes_its_organization(ops):
    station = await ops.station()
    for ref in (f"document:station:{station['id']}", f"config:{station['id']}"):
        for who in ("tech1", "admin"):
            response = await attachable(ops, ref, who)
            assert response.status_code == 200 and response.json() == {"org_id": ORG_A}


async def test_viewers_may_not_attach_and_unknown_owners_are_not_found(ops):
    station = await ops.station()
    assert (await attachable(ops, f"config:{station['id']}", "viewer")).status_code == 403
    assert (await attachable(ops, f"config:{new_id()}")).status_code == 404
    assert (await attachable(ops, f"document:station:{new_id()}")).status_code == 404
    assert (await attachable(ops, "visit:abc")).status_code == 404  # Phase 4
    assert (await attachable(ops, "config")).status_code == 404


async def test_clients_cannot_attach_to_staff_owners(ops):
    station = await ops.station()  # organization A's
    own = await attachable(ops, f"document:station:{station['id']}", "client_a1")
    assert own.status_code == 403  # their station, but not theirs to write to
    foreign = await attachable(ops, f"document:station:{station['id']}", "client_b1")
    assert foreign.status_code == 404


async def test_model_documents_belong_to_no_organization(ops):
    model = await ops.model()
    response = await attachable(ops, f"document:model:{model['id']}", "admin")
    assert response.status_code == 200 and response.json() == {"org_id": None}
    assert (await attachable(ops, f"document:model:{model['id']}", "client_a1")
            ).status_code == 404
    assert (await attachable(ops, f"document:model:{new_id()}", "admin")).status_code == 404


async def test_only_media_may_ask(ops):
    station = await ops.station()
    response = await attachable(ops, f"config:{station['id']}", service="platform")
    assert response.status_code == 403


# --- calibration certificates -------------------------------------------------------------------


@pytest.mark.req("CAL-1")
async def test_a_calibration_can_carry_its_certificate(ops):
    model = await ops.model()
    unit = await ops.unit(model["id"])
    cert = ops.media.add(f"calibration:{unit['id']}", filename="certificate.pdf")
    body = {"sensor_unit_id": unit["id"], "at": iso(ops.clock.now()), "method": "lab",
            "result": "pass", "certificate_media_id": cert}
    made = await ops.http.post("/api/v1/calibrations", json=body, headers=ops.bearer("tech1"))
    assert made.status_code == 201, made.text
    assert made.json()["certificate_media_id"] == cert
    bad = {**body, "certificate_media_id": ops.media.add(f"calibration:{new_id()}")}
    wrong = await ops.http.post("/api/v1/calibrations", json=bad, headers=ops.bearer("tech1"))
    assert wrong.status_code == 422 and wrong.json()["code"] == "wrong_owner"
    pending = {**body, "certificate_media_id": ops.media.add(
        f"calibration:{unit['id']}", status="processing")}
    waiting = await ops.http.post("/api/v1/calibrations", json=pending,
                                  headers=ops.bearer("tech1"))
    assert waiting.status_code == 409 and waiting.json()["reason"] == "file_not_ready"
