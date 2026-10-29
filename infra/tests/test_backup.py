"""The backup container against the running stack (TRD §16.4; W20-6, W20-7): a dump is encrypted
and described by a manifest, the backup host holds exactly what was made, a damaged file is
refused before anything is deleted, the container will not run without a key, and a lost object
on the replica is noticed.

    docker compose -f compose.yml -f compose.dev.yml -f compose.backup.yml -f compose.backup-host.yml up -d
    ../.venv/Scripts/python -m pytest tests/test_backup.py -q

Skipped when the stack is not running.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid

import pytest
from backup_support import INFRA, available, in_backup, make_key, take_backup

pytestmark = pytest.mark.skipif(not available(), reason="the local stack is not running")


@pytest.fixture(scope="module")
def key(tmp_path_factory):
    return make_key(tmp_path_factory.mktemp("age"))


@pytest.fixture(scope="module")
def backup(key):
    public, _ = key
    return take_backup(public)


@pytest.mark.req("NFR-9")
def test_the_dump_is_encrypted_and_the_manifest_describes_it(backup):
    out = in_backup(
        f'head -c 40 /backups/mongo/{backup}; echo; echo ---; cat /backups/mongo/{backup[:-4]}.json;'
        f' echo; echo ---; sha256sum /backups/mongo/{backup}'
    ).stdout
    header, manifest_text, digest = out.split("---")
    assert header.startswith("age-encryption.org/v1")  # not a mongodump archive
    manifest = json.loads(manifest_text)
    assert manifest["file"] == backup and manifest["size"] > 100_000
    assert digest.split()[0] == manifest["sha256"]
    assert manifest["audit_head"]["seq"] >= 0
    assert len(manifest["audit_head"]["hash"] or "x" * 64) == 64


@pytest.mark.req("NFR-9")
def test_only_the_private_key_opens_it(backup, key):
    _, private = key
    other_public, other_private = None, None  # a second key pair, to prove the wrong one fails
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        other_public, other_private = make_key(Path(tmp))
        wrong = in_backup(
            f'age -d -i /id/key.txt /backups/mongo/{backup} > /dev/null',
            volumes=(f"{other_private}:/id/key.txt:ro",),
        )
    assert wrong.returncode != 0
    right = in_backup(
        f'age -d -i /id/key.txt /backups/mongo/{backup} | mongorestore --archive --gzip --dryRun'
        f' --uri "mongodb://root:dev-root-password@mongo:27017/?authSource=admin&directConnection=true"',
        volumes=(f"{private}:/id/key.txt:ro",),
    )
    assert right.returncode == 0, right.stderr[-300:]


@pytest.mark.req("NFR-9")
def test_a_backup_writes_the_readings_the_alerts_watch(backup):
    prom = in_backup("cat /textfile/mms_backup_mongo.prom").stdout
    assert 'backup_last_success_timestamp_seconds{kind="mongo"}' in prom
    stamp = int(prom.split('backup_last_success_timestamp_seconds{kind="mongo"} ')[1].split()[0])
    assert abs(time.time() - stamp) < 3600


def test_the_container_will_not_run_without_a_key():
    r = in_backup("/opt/backup/loop.sh", env={"BACKUP_AGE_RECIPIENT": ""})
    assert r.returncode == 1 and "BACKUP_AGE_RECIPIENT" in r.stderr


@pytest.mark.req("NFR-9")
def test_a_damaged_backup_is_refused_before_anything_is_stopped(backup, key):
    """restore.sh checks the file against its manifest first (decision W20-8)."""
    _, private = key
    in_backup(f'printf X | dd of=/backups/mongo/{backup} bs=1 seek=100 conv=notrunc 2>/dev/null')
    try:
        r = subprocess.run(
            ["bash", "scripts/restore.sh", "--file", backup, "--identity", str(private), "--yes"],
            cwd=INFRA, capture_output=True, text=True, check=False, timeout=300,
        )
        assert r.returncode == 1
        assert "does not match its manifest" in r.stderr
        assert "2/7" not in r.stdout  # it never reached "stopping the services"
    finally:
        in_backup(f'rm -f /backups/mongo/{backup} /backups/mongo/{backup[:-4]}.json')


@pytest.mark.req("NFR-9")
def test_the_replica_matches_and_a_lost_object_is_noticed():
    """`weed filer.sync` fills the replica; the nightly check proves it and finds a loss."""
    bucket = f"drill-{uuid.uuid4().hex[:8]}"
    scope = {"BACKUP_BUCKETS": bucket}
    setup = (
        "export RCLONE_CONFIG_PRIMARY_TYPE=s3 RCLONE_CONFIG_PRIMARY_PROVIDER=Other"
        " RCLONE_CONFIG_PRIMARY_ENDPOINT=http://seaweedfs:8333"
        " RCLONE_CONFIG_PRIMARY_ACCESS_KEY_ID=$BACKUP_S3_ACCESS_KEY"
        " RCLONE_CONFIG_PRIMARY_SECRET_ACCESS_KEY=$BACKUP_S3_SECRET_KEY"
        " RCLONE_CONFIG_REPLICA_TYPE=s3 RCLONE_CONFIG_REPLICA_PROVIDER=Other"
        " RCLONE_CONFIG_REPLICA_ENDPOINT=$BACKUP_REPLICA_S3_ENDPOINT"
        " RCLONE_CONFIG_REPLICA_ACCESS_KEY_ID=$BACKUP_S3_ACCESS_KEY"
        " RCLONE_CONFIG_REPLICA_SECRET_ACCESS_KEY=$BACKUP_S3_SECRET_KEY; "
    )
    made = in_backup(setup + f"rclone mkdir primary:{bucket} && echo drill | rclone rcat primary:{bucket}/a.txt")
    assert made.returncode == 0, made.stderr[-300:]

    def check() -> subprocess.CompletedProcess[str]:
        return in_backup("/opt/backup/backup.sh objects", env=scope)

    for _ in range(40):  # the sync is continuous: seconds
        if check().returncode == 0:
            break
        time.sleep(3)
    else:
        pytest.fail("the replica never matched the primary")
    assert 'backup_check_ok{kind="objects"} 1' in in_backup("cat /textfile/mms_backup_objects.prom").stdout

    in_backup(setup + f"rclone deletefile replica:{bucket}/a.txt")
    lost = check()
    assert lost.returncode == 1 and "differs from its replica" in lost.stdout
    assert 'backup_check_ok{kind="objects"} 0' in in_backup("cat /textfile/mms_backup_objects.prom").stdout
    in_backup(setup + f"rclone purge primary:{bucket}; rclone purge replica:{bucket} || true")
