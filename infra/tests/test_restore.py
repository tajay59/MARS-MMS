"""The restore drill (TRD §16.4; W20-8, W20-9, finding F18): back up the running stack, change it,
restore, and prove what the runbook promises.

- an access token and a refresh cookie from before the restore are dead (nobody keeps an old
  session: a dump brings users and sessions back as they were), and signing in again works
- what happened after the backup is gone from the databases (a user who registered since), and the
  consumers applied the events they still held, so the audit chain also has that history
- the audit chain is intact and holds the record the backup noted (restore.sh checks it)
- the drill's duration is recorded for the alert RestoreDrillOld

Slow (a few minutes): it stops and starts the application services. Run on its own:

    docker compose -f compose.yml -f compose.dev.yml -f compose.backup.yml -f compose.backup-host.yml up -d
    ../.venv/Scripts/python -m pytest tests/test_restore.py -q -s

Skipped when the stack is not running.
"""

from __future__ import annotations

import subprocess
import time
import uuid

import pytest
from backup_support import INFRA, available, in_backup, make_key, take_backup
from test_stack import MMS, api, mongo_as, root_mongo, seeded, web  # noqa: F401 - fixtures by name

pytestmark = pytest.mark.skipif(not available(), reason="the local stack is not running")



def sign_in(web, password):  # noqa: F811
    """(access token, the refresh cookie as a Cookie header value)"""
    r = api(web, "POST", "/api/v1/auth/login",
            json={"email": "admin@example.org", "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.headers["set-cookie"].split(";", 1)[0]


@pytest.mark.req("NFR-9")
def test_a_restore_returns_to_the_backup_ends_every_session_and_the_chain_holds(
    web, seeded, tmp_path  # noqa: F811
):
    public, private = make_key(tmp_path)
    token, cookie = sign_in(web, seeded)
    assert api(web, "GET", "/api/v1/auth/me", token).status_code == 200
    backup = take_backup(public)

    # After the backup: someone registers (a user, an outbox row, and an audit record follow)
    email = f"drill-{uuid.uuid4().hex[:8]}@example.org"
    r = api(web, "POST", "/api/v1/auth/register", json={
        "name": "Drill Person", "email": email, "password": "a long test password",
        "organization_name": "Organization A"})
    assert r.status_code == 202, r.text
    with mongo_as("auth") as c:
        user_id = c["auth"].users.find_one({"email": email})["_id"]
    root = root_mongo()
    try:
        for _ in range(60):  # outbox relay -> Kafka -> platform audit consumer
            if root.audit.audit_events.count_documents(
                {"action": "user.registered", "resource.id": user_id}
            ):
                break
            time.sleep(1)
        assert root.audit.audit_events.count_documents(
            {"action": "user.registered", "resource.id": user_id}) == 1
    finally:
        root.close()

    restored = subprocess.run(
        ["bash", "scripts/restore.sh", "--file", backup, "--identity", str(private), "--yes",
         "--drill"],
        cwd=INFRA, capture_output=True, text=True, check=False, timeout=1500,
    )
    print(restored.stdout[-1500:], restored.stderr[-800:])
    assert restored.returncode == 0, restored.stderr[-800:]
    assert "audit chain ok" in restored.stdout

    # 1. Nobody keeps an old session
    assert api(web, "GET", "/api/v1/auth/me", token).status_code == 401
    refresh = web.post("/api/v1/auth/refresh", headers={"Host": MMS, "Cookie": cookie})
    assert refresh.status_code == 401
    time.sleep(2)  # a token must be issued after the moment of the revocation
    fresh, _ = sign_in(web, seeded)
    assert api(web, "GET", "/api/v1/auth/me", fresh).status_code == 200

    # 2. What happened after the backup is gone from the database that held it, and the audit
    #    consumer, reset to the start, applied the event Kafka still held: the history is there
    #    once (processed_events came back with the dump, so nothing is doubled)
    with mongo_as("auth") as c:
        assert c["auth"].users.count_documents({"email": email}) == 0
        assert c["auth"].users.count_documents({"email": "admin@example.org"}) == 1
    root = root_mongo()
    try:
        assert root.audit.audit_events.count_documents(
            {"action": "user.registered", "resource.id": user_id}) == 1
    finally:
        root.close()

    # 3. The restore left the drill's duration for the alert
    prom = in_backup("cat /textfile/mms_backup_drill.prom").stdout
    assert "restore_drill_last_success_timestamp_seconds" in prom
    assert "restore_drill_duration_seconds" in prom

    # 4. The chain checks out through the API as well
    started = api(web, "POST", "/api/v1/audit/verify", fresh)
    assert started.status_code == 202
    for _ in range(60):
        done = api(web, "GET", f"/api/v1/audit/checks/{started.json()['id']}", fresh).json()
        if done["status"] in ("passed", "broken", "failed"):
            break
        time.sleep(2)
    assert done["status"] == "passed", done
