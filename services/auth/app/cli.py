"""Operator commands, run inside the auth container:

    python -m app.cli create-admin --email ops@example.org --name "Ops Admin"
        The first admin of an installation (nobody can approve or invite before one exists).
        Reads the password from AUTH_ADMIN_PASSWORD, or asks for it.

    python -m app.cli seed
        The TP seed users and organizations A and B, for local and staging only. Password from
        AUTH_SEED_PASSWORD. Idempotent.

    python -m app.cli reset-totp --email ops@example.org
        Removes someone's second factor (lost phone and recovery codes, and no other admin to reset
        it from the Users page). Ends their sessions and restarts their setup window. Recorded as
        `auth.totp_reset` with `via: cli`.

    python -m app.cli import-orgs FILE [--commit]
        Organizations from the existing system's `entities` export (decision W5-8). A dry run unless
        --commit; organizations already there are skipped, so it can run again.

    python -m app.cli revoke-all-sessions [--reason restore]
        Ends every session: all refresh tokens, and every access token issued so far. Run it after
        a restore from backup (the dump brings back users and sessions as they were) and when a
        signing key may have leaked. Everyone signs in again. Recorded as `auth.sessions_revoked`.

All go through the same rules and the outbox, so the audit trail records them (`user.created`,
`org.created`).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from typing import Any

from mms_common import migrations, mongo
from mms_common.events import Actor
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS
from mms_common.time import SystemClock
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app import migrations as app_migrations
from app.config import Settings
from app.domain import org_import
from app.domain import users as rules
from app.domain.passwords import MIN_LENGTH, Hasher
from app.events.publish import Emitter, ev
from app.repo import organizations
from app.repo import users as users_repo

CLI = Actor(name="auth cli", roles=["service"])


def _user_doc(
    *, user_id: str, email: str, name: str, roles: list[str], org_id: str | None, status: str,
    password_hash: str, now: Any,
) -> dict[str, Any]:
    return {
        "_id": user_id, "email": email, "password_hash": password_hash, "name": name,
        "phone": None, "time_zone": None, "theme": "system", "roles": roles, "org_id": org_id,
        "proposed_org_name": None, "status": status, "rejection_reason": None,
        "last_login_at": None, "created_at": now, "updated_at": now, "created_by": None,
        "updated_by": None, "version": 1,
    }


async def _create_user(
    client: Any, db: AsyncDatabase[dict[str, Any]], emitter: Emitter, doc: dict[str, Any]
) -> bool:
    if await users_repo.find_by_email(db, doc["email"]) is not None:
        return False

    async def save(s: AsyncClientSession) -> None:
        await users_repo.insert(db, doc, s)
        await emitter.user("user.created", ev.UserCreated, doc, s, via="cli")

    await mongo.in_transaction(client, save)
    return True


async def create_admin(email: str, name: str, password: str) -> int:
    settings = Settings()
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    db = client[settings.mongo_db]
    try:
        await migrations.run(db, app_migrations, clock)
        hasher = Hasher(settings.argon2_time_cost, settings.argon2_memory_kib,
                        settings.argon2_parallelism)
        from mms_common.ids import new_id

        doc = _user_doc(
            user_id=new_id(), email=rules.normalize_email(email), name=name, roles=["admin"],
            org_id=None, status="active", password_hash=hasher.hash(password), now=clock.now(),
        )
        emitter = Emitter(db, clock, CLI, correlation_id=None)
        if not await _create_user(client, db, emitter, doc):
            print(f"{doc['email']} already has an account", file=sys.stderr)
            return 1
        print(f"Admin {doc['email']} created")
        return 0
    finally:
        await client.close()


async def revoke_all_sessions(reason: str) -> int:
    from mms_common.auth import revocation
    from redis.asyncio import Redis

    from app.repo import sessions

    settings = Settings()
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    db = client[settings.mongo_db]
    redis = Redis.from_url(settings.redis_url)
    try:
        now = clock.now()
        emitter = Emitter(db, clock, CLI, correlation_id=None)
        counted = 0

        async def save(s: AsyncClientSession) -> None:
            nonlocal counted
            counted = await sessions.revoke_all(db, now, session=s)
            await emitter.emit(
                ev.SessionsRevoked(reason=reason, count=counted), type_="auth.sessions_revoked",
                key="sessions", resource=("auth", "sessions"), aggregate_version=0, org_id=None,
                session=s,
            )

        await mongo.in_transaction(client, save)
        # After the database: a token refused for a session that was not ended is only a login
        # again, but the other order could leave a session open.
        await revocation.revoke_all(redis, now)
        print(f"{counted} session(s) ended; every access token issued before now is refused")
        return 0
    finally:
        await redis.aclose()
        await client.close()


async def _enrol_seed_admin(
    db: AsyncDatabase[dict[str, Any]], settings: Settings, now: Any
) -> bool:
    """`admin_mfa` (tests and Playwright) has two-step sign-in with the public secret from
    `mms_common.testing.seed`, when `AUTH_TOTP_KEY` is set. Written straight to the record: it is
    a test account, so no audit event."""
    from mms_common.testing.seed import ADMIN_MFA_TOTP_SECRET

    from app.domain import recovery, totp
    from app.repo import totp as totp_repo

    key = settings.totp_key_bytes
    user = SEED_USERS["admin_mfa"]
    current = await users_repo.get(db, user.id)
    if key is None or current is None or current.get("totp"):
        return False
    sealed = totp_repo.seal(key, totp.from_base32(ADMIN_MFA_TOTP_SECRET), user.id)
    _, records = recovery.generate()
    fields = totp_repo.enrolment_fields(sealed, records, now, 0)
    await users_repo.col(db).update_one({"_id": user.id}, {"$set": fields})
    return True


async def reset_totp(email: str) -> int:
    from mms_common.auth import revocation
    from redis.asyncio import Redis

    from app.events import totp_reset

    settings = Settings()
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    db = client[settings.mongo_db]
    redis = Redis.from_url(settings.redis_url)
    try:
        user = await users_repo.find_by_email(db, rules.normalize_email(email))
        if user is None:
            print(f"No account for {email}", file=sys.stderr)
            return 1
        if not user.get("totp"):
            print(f"{user['email']} has no two-step sign-in to reset", file=sys.stderr)
            return 1
        now = clock.now()

        async def tx(body: Any) -> Any:
            return await mongo.in_transaction(client, body)

        await totp_reset.apply(
            tx, db, settings, user, Emitter(db, clock, CLI, correlation_id=None),
            now=now, via="cli", by=None,
        )
        await revocation.revoke_user(redis, user["_id"], now)
        print(f"Two-step sign-in removed for {user['email']}; they sign in again and set it up")
        return 0
    finally:
        await redis.aclose()
        await client.close()


async def seed(password: str) -> int:
    settings = Settings()
    if settings.environment == "production":
        print("Refusing to seed production", file=sys.stderr)
        return 1
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    db = client[settings.mongo_db]
    try:
        await migrations.run(db, app_migrations, clock)
        hasher = Hasher(settings.argon2_time_cost, settings.argon2_memory_kib,
                        settings.argon2_parallelism)
        password_hash = hasher.hash(password)
        emitter = Emitter(db, clock, CLI, correlation_id=None)
        now = clock.now()
        for org_id, name, country in ((ORG_A, "Organization A", "JM"),
                                      (ORG_B, "Organization B", "TT")):
            if await organizations.get(db, org_id) is None:
                org = {
                    "_id": org_id, "name": name, "name_key": rules.org_name_key(name),
                    "country": country, "contact_email": None, "phone": None, "address": None,
                    "status": "active", "created_at": now, "updated_at": now,
                    "created_by": None, "updated_by": None, "version": 1,
                }

                async def save(s: AsyncClientSession, org: dict[str, Any] = org) -> None:
                    await organizations.insert(db, org, s)
                    await emitter.org("org.created", ev.OrgCreated, org, s)

                await mongo.in_transaction(client, save)
        created = 0
        for seed_user in SEED_USERS.values():
            doc = _user_doc(
                user_id=seed_user.id, email=seed_user.email, name=seed_user.name,
                roles=list(seed_user.roles), org_id=seed_user.org_id, status=seed_user.status,
                password_hash=password_hash, now=now,
            )
            created += await _create_user(client, db, emitter, doc)
        enrolled = await _enrol_seed_admin(db, settings, now)
        print(f"Seeded {created} users" + (", admin_mfa has two-step sign-in" if enrolled else ""))
        return 0
    finally:
        await client.close()


async def import_orgs(path: str, content: bytes, commit: bool) -> int:
    """Organizations from the existing system's `entities` export (decision W5-8). Dry run unless
    `commit`. Only names, country and IDs are read: never the credentials in the documents."""
    try:
        docs = org_import.read_export(content)
    except org_import.ExportError as exc:
        print(f"Can't read {path}: {exc}", file=sys.stderr)
        return 1
    settings = Settings()
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    db = client[settings.mongo_db]
    try:
        await migrations.run(db, app_migrations, clock)
        ids, names = await organizations.known_keys(db)
        result = org_import.plan(docs, existing_external_ids=ids, existing_name_keys=names)
        for problem in result.errors:
            print(f"error    #{problem.number}: {problem.message}")
        for problem in result.skipped:
            print(f"skipped  #{problem.number}: {problem.message}")
        if not commit:
            for row in result.create:
                short = row.short_name or "-"
                print(f"would add #{row.number}: {row.name} ({short}, {row.country})")
            print(f"Dry run: {len(result.create)} to add, {len(result.skipped)} skipped, "
                  f"{len(result.errors)} with errors. Add --commit to write them.")
            return 0
        emitter = Emitter(db, clock, CLI, correlation_id=None)
        now = clock.now()
        for row in result.create:
            org = {
                "_id": new_id(), "name": row.name, "name_key": rules.org_name_key(row.name),
                "short_name": row.short_name, "external_id": row.external_id,
                "country": row.country, "contact_email": None, "phone": None, "address": None,
                "status": "active", "created_at": now, "updated_at": now,
                "created_by": None, "updated_by": None, "version": 1,
            }

            async def save(s: AsyncClientSession, org: dict[str, Any] = org) -> None:
                await organizations.insert(db, org, s)
                await emitter.org("org.created", ev.OrgCreated, org, s)

            await mongo.in_transaction(client, save)
            print(f"added    #{row.number}: {row.name}")
        print(f"Added {len(result.create)}, skipped {len(result.skipped)}, "
              f"{len(result.errors)} with errors")
        return 0
    finally:
        await client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    commands.add_parser("seed")
    revoke = commands.add_parser("revoke-all-sessions",
                                 help="end every session (after a restore from backup)")
    revoke.add_argument("--reason", default="restore", choices=["restore", "key_rotation"])
    reset = commands.add_parser("reset-totp", help="remove someone's second factor (lost phone)")
    reset.add_argument("--email", required=True)
    orgs = commands.add_parser("import-orgs",
                               help="organizations from the existing system's export")
    orgs.add_argument("file")
    orgs.add_argument("--commit", action="store_true", help="write them (default: dry run)")
    args = parser.parse_args(argv)
    if args.command == "import-orgs":
        try:
            with open(args.file, "rb") as file:
                content = file.read()
        except OSError as exc:
            print(f"Can't read {args.file}: {exc}", file=sys.stderr)
            return 1
        return asyncio.run(import_orgs(args.file, content, args.commit))
    if args.command == "reset-totp":
        return asyncio.run(reset_totp(args.email))
    if args.command == "revoke-all-sessions":
        return asyncio.run(revoke_all_sessions(args.reason))
    if args.command == "create-admin":
        password = os.environ.get("AUTH_ADMIN_PASSWORD") or getpass.getpass("Password: ")
        if len(password) < MIN_LENGTH:
            print(f"Use at least {MIN_LENGTH} characters", file=sys.stderr)
            return 1
        return asyncio.run(create_admin(args.email, args.name, password))
    password = os.environ.get("AUTH_SEED_PASSWORD", "")
    if len(password) < MIN_LENGTH:
        print(f"Set AUTH_SEED_PASSWORD (at least {MIN_LENGTH} characters)", file=sys.stderr)
        return 1
    return asyncio.run(seed(password))


if __name__ == "__main__":
    sys.exit(main())
