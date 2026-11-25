# CLAUDE.md

AWS-MMS (Automatic Weather Station Maintenance Management System, shown to users as **MARS-MMS**, decision W4-6). A self-hosted web app for maintaining weather stations the organization runs for external client organizations in several countries. Clients request work and sign it off. Staff plan, record (offline as well) and report site visits.

## Think like a PWA expert first (required)

AWS-MMS is a PWA: technicians record whole visits on iPhones and Android phones with no signal, and nothing may be lost or duplicated. **Before starting any task in this repo (code, review, plan or document), load the `pwa` skill ([.claude/skills/pwa/](.claude/skills/pwa/SKILL.md)) with the Skill tool and answer its pre-flight questions.** For back-end-only work this takes seconds, but still check the effect on the device: sync contracts, idempotency, auth refresh, caching headers, CSP, presigned uploads. The skill holds the PWA rules from the TRD, verified browser facts (iOS Safari first), the vite-plugin-pwa, Workbox and Dexie patterns, PWA work per phase, the open findings and the sources. When browser reality and a planning document disagree, raise it as a finding; don't work around it silently. A `SessionStart` hook in [.claude/settings.json](.claude/settings.json) repeats this reminder at the start of every session and after `/clear` or compaction (text in [.claude/hooks/pwa-session-start.json](.claude/hooks/pwa-session-start.json)).

## Where things stand (2026-11-25)

**Phases 0 to 7 are built and on `main`; Phase 8 (pilot) is under way. Staging is the pilot site** (decision W23-8): `rnd.yanacreations.com` runs `MMS_ENVIRONMENT=staging` with the real import of 18 Oct (8 organizations, 50 stations), cleaned of test data. So **every merge to `main` is a release to pilot users**: `seed`, `seed-requests` and the load test are never run there. Release 0.8.0 is the current app version. When a week's work is done, its plan in `docs/plans/` and the docs site hold the detail; this file keeps only what a new session needs.

| Week | What | Plan | State |
|---|---|---|---|
| W1–W4 (P0, P1) | Stack, `mms_common`, service template, auth, platform audit + account emails, app shell, minimal service worker, release pipeline, Kafka SASL/SCRAM | IP, TRD | Built; staging checks passed 2026-10-18 (audit chain, update prompt, Android install) |
| W5–W7 (P2) | Stations, sensors, import (W5-8), documents + media service, configuration versions, calibration, QR labels, scan, map with own tiles (W7-9), report service skeleton (label sheets) | — (decisions W5-1…W7-10 in the docs site) | Built, deployed |
| W8–W9 (P3) | Requests (`derive_status`), assign/claim/queue, comments + PDF attachments, notifications + WebSocket, email preferences + weekly digest | `W9-plan.md` | Built, deployed |
| W10–W12 (P4) | Visits online; the **visit board** (Note, Task, Recommendation, Config elements) replaced work records, sensor reconciliation, media phases and checklists (W11-16…W11-38); photo/video pipeline; visit in the field shell | `W10-plan.md`, `W11-plan.md`, `visit-board-plan.md` | Built, deployed |
| W13–W15 (P5) | Dexie device store, PIN unlock, prepare for field, offline lookup; outbox, `POST /sync`, local-first board, `/sync` screens; field test | `W13`, `W14`, `W15-plan.md` | Built; real-phone field test still owed |
| W16–W18 (P6) | Visit report drafts + read model + PDF; edit, sign, finalize saga, lock, reopen, verify; client review, auto-close, client reports, close-out report | `W16`, `W17`, `W18-plan.md` | Built, deployed |
| W19–W22 (P7) | Summary reports + CSV + charts, dashboards, audit viewer + History tab; metrics, monitoring, backups, production stack, ASVS L2 review, load test; Mongo 9.0.8; TOTP for admins | `W19`…`W22-plan.md` | Built; production never run (no host) |
| W23 (P8) | Production runbook + `readiness.sh`, pilot device check, guides + `/help/client`, triage routine, pilot on staging | `W23-plan.md` | Slices 1–5 built; waiting on people |

### Still open (check before saying a phase is closed)

- **Waiting on people:** a production host and a backup host (#3, #5), the backup key holder, alert recipients, the `production` environment with reviewers, the pilot organizations and technicians, the email relay (T3) before any client is invited, decisions from organization IT (#2), document sign-off (#1). The open security deviations are D-3 and D-4 in `docs/security/asvs-l2.md`.
- **Before clients upload files:** 2 GB more RAM on the shared server, then `MEDIA_SCAN_MODE=clamd` (staging runs `off`, T8).
- **Known gap:** staging (the pilot site) has **no backups and no monitoring**.
- **Real-phone checks owed** (the iPhone ones postponed by choice on 2026-10-20; most can start on Android): `docs/checks/pilot-device-check.md` gathers them per pilot phone: install and offline shell on an iPhone (Phase 1), F15 (W6), a printed label scanned by camera apps and the in-app scanner (W7, `docs/checks/W7-label-scan-check.md`), WebSocket resume after backgrounding and `wss://` under `connect-src 'self'` on Safari (W9), the W13 checks (install, prepare, airplane mode, restart, unlock, scan, storage check with 50 photos and 3 videos), the W15 field test (`docs/field-test.md`), drawing and sending a signature and uploading a PDF client report (W17, W18), the phone keyboard suggesting the 6-digit code (W22).
- **Staging checks owed:** a real email through the Gmail sender for an assignment or decision and the Monday 07:00 America/Jamaica digest (`digest_runs`) (W9); two browsers following a claim, comment or visit start live (W9, W10); a visit with all four board kinds from an Android phone, a 2-minute video processed, its Config version on the station, the client view (W11); release 0.6 checks: a client accepts one request and rejects another, an admin reopens a report during Client Review, the day-30 close with `OPS_AUTO_CLOSE_DAYS` of a few minutes (W18); the TOTP browser journeys against staging (W22; `e2e/totp.spec.ts` ran in CI only); the full load run on the production host and a restore into staging (W20).
- **MongoDB feature compatibility stays 8.0 on purpose** (W21): raising it (`setFeatureCompatibilityVersion: "9.0"` with `confirm: true`, by hand, never in `infra/mongo/init.js`) is the point of no return. It waits for a soak, a real backup and restore drill, and the product owner's go-ahead.
- **Held dependency updates:** Python 3.15 (#174; the TRD says 3.13), Pinia 4 (#176), jsdom 31 (#177). `frontend/package.json` `overrides` force glob 14 and editorconfig 4 under `workbox-build` and `js-beautify` (#213, advisories with no backport): remove them once those packages move to glob 14.
- Open GitHub issues #8 (test phones), #9 (map tiles; F1 is built and deployed), #10 (optional iPhone SeaweedFS run), #13 (docs site Phase 1 charts).

## Repository, CI and hosts

- **Repository:** GitHub `tajay59/MARS-MMS`, **public** since 2026-10-16: never commit client names, real station data, credentials or internal addresses (keep them in the organization's systems or uncommitted `.env` files). Secret scanning blocks pushes with secrets. Text files are LF (`.gitattributes`, `.editorconfig`); shell scripts and configs run in Linux containers.
- **`main` is protected:** no direct pushes, even for admins. Branch, open a pull request, merge by squash or rebase once checks are green and the branch is up to date. Every merge makes the other open pull requests BEHIND, so a batch is: `gh pr update-branch`, a full CI run (about 25–30 minutes; `compose stack` is the longest), merge, one at a time. Dependabot may not answer `@dependabot rebase`; `gh pr update-branch` works. Dependabot asks for a `dependencies` label that does not exist (harmless).
- **Tracking:** project board [AWS-MMS](https://github.com/users/tajay59/projects/2), milestones P0–P8. New issues get a milestone and go on the board. Pilot defects use the issue form `.github/ISSUE_TEMPLATE/pilot-defect.yml` (references only, never names or places) and labels `pilot`, `triage`, `severity:*`; the routine is in the docs site (`#infrastructure-triage`).
- **CI:** [frontend.yml](.github/workflows/frontend.yml) (lint, Vitest, API type drift, type-check, build; job `check`) and [backend.yml](.github/workflows/backend.yml) (`mms_common`, one job per service with Ruff, mypy, tests and coverage ≥ 70%, the service template, `nginx -t`, `compose stack` with `infra/tests` and the Playwright journeys, `backup and restore`, `load smoke`) run on every pull request. [release.yml](.github/workflows/release.yml) on pushes to `main`: checks → [images.yml](.github/workflows/images.yml) (Trivy; GHCR `ghcr.io/tajay59/mars-mms/<image>:<sha>`) → staging deploy over SSH with [infra/compose.prod.yml](infra/compose.prod.yml) (repository variables `STAGING_HOST`, `STAGING_USER`, `STAGING_URL`, secrets `STAGING_SSH_KEY`, `STAGING_KNOWN_HOSTS`) → Playwright `@smoke`. [security.yml](.github/workflows/security.yml): `pip-audit` (any advisory fails), `npm audit --omit=dev --audit-level=high`, a nightly passive ZAP baseline of staging (counts only; details with `infra/scripts/zap-baseline.sh`, `zap-report/` git-ignored). [production.yml](.github/workflows/production.yml) is by hand with a release SHA and approval (never run). `restore-drill.yml` weekly, `loadtest.yml` by hand (`LOAD_URL`, secret `LOAD_PASSWORD`).
- **Staging host (W4-8):** `https://rnd.yanacreations.com`, files host `files.yanacreations.com`, on a **shared** server `84.247.187.64` (Ubuntu 22.04, kernel 5.15, 6 GB RAM, about 2 GB free; also runs PrintIT and Kreativ Wrist; root SSH alias `kw-server`). Its edge Nginx `printit-nginx` owns 80/443 and the Let's Encrypt certificates (`/srv/edge-sites/*.conf`; ours is `mms-staging.conf` from [infra/nginx/staging-edge.conf](infra/nginx/staging-edge.conf)) and proxies to our Nginx as `mms-gateway` on `kong-net`. [infra/compose.staging.yml](infra/compose.staging.yml) adds that network, `snippets/real-ip.conf` and memory caps (`report-worker` 768 MB for Chromium charts). Deploy user `mms`; `/opt/mms/{infra,secrets,tls,tiles}`; the deploy writes `/opt/mms/.deployed-tag`. The map reads our own Protomaps extract of the Caribbean (`/opt/mms/tiles`, mounted through `MMS_TILES_DIR`; cut on the host with `/opt/mms/bin/pmtiles` because uploading 552 MB took far too long; the map is blank without it). Compose override tags: `!reset` empties a value, `!override` replaces it. **Changes to the edge or certbot affect the other sites: ask first.** Snap's certbot runs `/etc/letsencrypt/renewal-hooks/` even for `certonly`: issue new certificates with `--webroot -w /srv/edge-sites/acme --no-directory-hooks`, then set the renewal to `standalone`. Clients get email through the Gmail sender for the pilot. Read-only data checks: copy a mongosh script into `mms-mongo-1` and run it with the container's `MONGO_INITDB_ROOT_*` (never printed).
- **Staging deploys:** the host's `infra/.env` must hold every key `compose.yml` requires (it refuses to start otherwise). A deploy that fails on `required variable … is missing` changed nothing: add the key (as the root alias, keeping the file `mms`-owned, mode 600), then `gh run rerun <id> --failed`. The deploy tries `compose up` five times, 30 s apart; if it still fails it prints `compose ps -a` and the logs. It recreates `seaweedfs` when `seaweedfs-entrypoint.sh`'s checksum differs from `/opt/mms/.seaweedfs-entrypoint.sha256` (a mounted script is not part of a container's config; do the same for any other mounted script that sets flags). `AUTH_TOTP_KEY` (32 random bytes, base64) must be on every host and kept with the other secrets: losing it resets every enrolled admin. `REPORT_APP_URL` must be the site's address (labels hold it). Rollback over a migration, an event schema or a `mongo:` image change needs `--allow-older-schema` (`infra/scripts/rollback-guard.sh`); 0.8.0 added migration `0004` and new event types.
- **Is a site ready?** `bash infra/scripts/readiness.sh https://rnd.yanacreations.com --expect-version 0.8.0` (GET only); local: `--files files.mms.localhost --insecure --via 127.0.0.1:443`; on a host in the `docker` group: `readiness.sh --on-host` (never prints a value).
- **Production:** defined but never run: `infra/compose.production.yml` (limits totalling 18.9 GB, ClamAV always on), the day-one runbook in the docs site (`#infrastructure-day-one`). Labels printed from staging open staging: print them again from production. A dump from production (FCV 9.0) into staging (FCV 8.0) has not been tried.
- **Tools on this PC:** Docker Desktop 29.8.2 (CLI at `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin`, not on PATH in old terminals), draw.io desktop 32.4.1. Information requested from the organization: [Claude Doc](https://claude.ai/code/artifact/245278ff-5250-48fb-859d-6bcdba80d911) (T, B, P, Q, V items).

## Developer documentation site (required)

[docs/index.html](docs/index.html) is the living, interactive reference for how AWS-MMS is wired: architecture, services and routes, gateway, data and schemas, events, each feature's flows, frontend, security, configuration, infrastructure, CI/CD, decisions, a diagram guide and a changelog. The planning documents say what to build; this site describes what was built.

**Every phase updates it, and a phase is not done until it has.** Also update it in any change that alters how the system is wired:

1. "Build status", the section badges (`badge built` / `progress` / `planned`) and the sidebar dots (`dot built` / `dot progress`).
2. Built shapes instead of designed ones: schemas from the Pydantic models, routes from OpenAPI, events from `mms_common.events`, settings with their real env var names, file and folder tables.
3. The diagrams chosen for the phase, and any diagram the phase changed.
4. New decisions in "Decisions" and in the source document.
5. A "Changelog" entry.
6. Open the page in light and dark and check no diagram shows "could not be drawn". If the code and the TRD disagree, fix one of them in the same change.

**Constraints:** the page opens from disk (`file://`) with no server, build step or network. Mermaid is vendored and pinned (`docs/assets/vendor/mermaid-11.17.2.min.js`), fonts are in `docs/assets/fonts/`. Content lives in `index.html` (one `section.doc` per sidebar entry; `.sub[id]` blocks are what search finds), behaviour in `docs/assets/docs.js`, styles in `docs/assets/docs.css`. It is developer tooling, so the UI-skills workflow doesn't apply, but it uses the DBD tokens and fonts. "Maintaining these docs" in the page has copy-paste snippets. **Don't read `docs/index.html` or `docs/TRD.md` in full:** find the anchor with `grep -n`, then edit (ids: `#services`, `#media`, `#decisions`, `#config`, `#status`, `#changelog`; TRD §3.2 operations, §3.3 media, §9 jobs, §10 storage, R6 risks).

**Diagrams:** Mermaid by default, inside `<pre class="mermaid-def">` in a `figure.diagram` with `data-title` (the answer, in a few words) and `data-kind` (a chart type). Escape `<` as `&lt;` and `&` as `&amp;`; no `;` in sequence messages, no raw `<host>`-style text in labels. **draw.io** for hand-laid diagrams (true swimlanes, deployment pictures, anything for clients): `docs/diagrams/<name>.drawio.svg`, shown as an `<img>`; when a Mermaid and a draw.io version of one flow exist, they are tabs on one figure and must match. Names exactly as in the code. One question per diagram. Brand colours only; status colours only for statuses.

**Charts: at the start of each phase, propose which to add** from the catalogue in the site's "Diagram guide" (Figma's 17 [types of flow charts](https://www.figma.com/resource-library/types-of-flow-charts/) plus sequence, state, ER, C4 and gantt); the user picks. Typical uses: process flow (one actor's steps), workflow (staff routines), data flow (events, secrets, backups), swimlane (hand-offs between roles, draw.io), decision tree (`derive_status`, conflicts, access rules), system flowchart (gateway, media pipeline), document flowchart (signatures), product flowchart (sensor inventory), PERT/gantt (phases), use case (roles × actions), event storming (commands → events → consumers), customer journey (the client's path), logical model (reports), code flowchart (branch-by-branch logic), website flowchart (pages and guards). Not used: production and e-commerce flowcharts. Left for **P8**: hypercare workflow, client onboarding customer journey, go-live gantt.

## What is built (orientation: read this instead of exploring)

**Services** (each `services/<name>/app/{api,domain,repo,events,jobs,migrations}`; operations groups each layer by module):

- [libs/mms_common/](libs/mms_common/): `ids` (UUIDv7), `time` (injectable clock), `errors` (problem details), `logging`, `events` (envelope + `(type, version)` registry), `mongo`, `outbox` + `relay` (under the Redis leader lease), `consumer` (dedupe, retry, DLQ), `snapshot` (backfill, `aggregate_version` guard), `kafka`, `web` (request IDs, `/health` `/ready` `/metrics`), `checks` (no-direct-produce), `auth` (EdDSA tokens, JWKS, Redis revocation list, `require_roles`/`require_staff`/`require_service`, `scoped`), `migrations` (forward-only, `_migrations` lock), `cron` (Redis lock per run), `jobs` (Redis job queue; **don't install `arq`**: it pins `redis<6`), `signature` (PNG check), `safecsv`, `testing`.
- [templates/service/](templates/service/): the copier template (migrations on startup, relay under its lease, JWT from JWKS, import-linter layers `api → jobs → events → repo → domain`, the no-direct-produce check, an empty authorization matrix).
- [services/auth/](services/auth/): TRD §3.1. Users, organizations (`short_name`, `external_id`), tokens, `POST /internal/account-links` (**links are minted on send**, never put in an event), branding (`GET`/`PUT /api/v1/auth/branding`), TOTP for admins (W22: `POST /login` answers `{mfa_required, enrol, challenge}` and makes no session until `/login/totp`; the code is asked at sign-in only, never on refresh, the PIN unlock, the service worker or `/sync`; required for `admin` after `AUTH_TOTP_GRACE_DAYS`; ten recovery codes; `POST /users/{id}/totp/reset`; secret sealed with `AUTH_TOTP_KEY`; an app without `supports_mfa` gets 401 `update_required`). CLI: `create-admin | seed | import-orgs FILE [--commit] | reset-totp --email … | revoke-all-sessions`.
- [services/operations/](services/operations/): stations (scoped by `owner_org_id`; clients get `qr_token` and `current_config_version` empty), sensor models, units (`POST /sensor-units/{id}/install|remove` are the only way in and out of `installed`), calibrations, documents and configuration versions, QR (`GET /api/v1/qr/{token}`, 410 for a replaced token), requests (`domain/requests/state.py` moves, `derive.py` = `derive_status`, idempotent create by device-made `id`), staffing (assign, claim, release, `/queue`), comments, visits (`domain/visits/state.py`, `lifecycle.py`, the board in `elements.py`; the end makes configuration versions), `POST /api/v1/sync` (a dispatcher over the route functions; `sync_operations` written in the op's own transaction; answers `applied|duplicate|conflict|error|skipped`), client review (`accept|reject`, review clock `jobs/review_clock.py`), client reports. Keeps a copy of organizations from auth's events and snapshot. CLI: `import-stations FILE [--sensors FILE] [--commit] | seed | seed-requests | remove-example-requests | backfill-orgs`.
- [services/media/](services/media/): presigned multipart uploads to the files host (`POST /uploads` idempotent by `media_id`; `complete` takes no part list), checks in `media-worker` (SHA-256, magic bytes, ClamAV; `MEDIA_SCAN_MODE=clamd|off`, **`off` refused in production**), image and video derivatives (ffmpeg), fail-closed visibility from `media.visibility_requested`, crons `abort_stale_uploads`, `reconcile`, `purge_originals`, `purge_deleted`.
- [services/report/](services/report/): label sheets, visit reports (draft, edit, sign, the finalize saga in the worker, reopen, `POST /reports/verify`), client-form and close-out reports, summary reports (PDF with Chromium charts from vendored ApexCharts, or CSV), the dashboard read model (`GET /api/v1/dashboard`), finalize reminders. WeasyPrint + Jinja; `report-worker` = `python -m app.worker`. Rebuild the read model: `python -m app.cli backfill`.
- [services/platform/](services/platform/): the audit module (hash chain, `verify()`, the viewer API `GET /audit/events|resources`, nightly check, `python -m app.cli verify-audit`) and notification (in-app + WebSocket via Redis `ws:user:{id}`, email queue and sender, preferences, weekly calibration digest).
- [infra/](infra/): `compose.yml` + `compose.dev.yml` (Nginx gateway, MongoDB 9.0.8 `rs0` with one user per service database and an insert-only audit role, Redis, Kafka KRaft with SASL/SCRAM (users and ACLs in `infra/kafka/users.yml`), SeaweedFS with per-service S3 keys, Mailpit, self-signed TLS, `dev-secrets`), `compose.monitoring.yml`, `compose.backup.yml` (profile `backup`: start `backup` and `filer-sync` by name) + `compose.backup-host.yml`, `compose.production.yml`, `infra/backup/`, `infra/scripts/` (`restore.sh`, `rollback-guard.sh`, `readiness.sh`, `export_openapi.py`, `extract-tiles.sh`, `zap-baseline.sh`, `pilot-labels.sh`), `infra/loadtest/`, `infra/tests/`.

**Frontend** ([frontend/src/](frontend/src/)): `app/` (shells, router guards and `next`, `auth/session.ts`: access token in memory, refresh under the Web Lock `mms-auth-refresh`, BroadcastChannel `mms-auth`; `theme/`; `motion.ts`; `pwa/`; `realtime/`; `format.ts`; `ids.ts` `newId()`; `navigation.ts`), `api/` (typed clients generated from `openapi/*.json`, aliases in `models.ts`, `download()` for files that need the token), `features/<area>/` (pages), `offline/` (no Vue: `db.ts` Dexie `aws-mms` with the six TRD §7.1 tables, `session.ts` PIN, `bundles.ts` prepare, `ops.ts`/`outbox.ts`/`sync.ts` under the Web Lock `mms-sync`, `upload.ts`/`transport.ts`/`hash*.ts`), `components/`, `stores/`, `sw/`. The local-first visit board is `features/visits/local/` (decision W14-6). **Stations** (redesigned 2026-11-19/20 with Impeccable) opens on **Needs attention** (counts and ranked rows with a next step, rules in `features/stations/attention.ts`) with **All stations** as the register (`?view=`, `?problem=`); every filter is a counted button in the pane; `/stations/new` is the short `StationQuickForm.vue` with `PinMap.vue` and `usePaneless()`, the edit form keeps every field. Public pages use the split panel (`PublicShell`, `wide` mode for `/help/client`).

**Where things go.** Route: `app/api/<module>/<x>_routes.py` + schemas; rules with no I/O: `app/domain/<module>/`; Mongo and HTTP clients: `app/repo/<module>/`; events: a schema in `libs/mms_common/mms_common/events/<service>.py` with `@register`, sent through `Emitter` in `app/events/publish.py` inside `ctx.tx(...)`; indexes: a new `app/migrations/NNNN_*.py`. Every new route goes in `tests/api/test_authorization_matrix.py` (`TABLE`; path params use the real names); the audit consumer records every event type by default (`AUD1` in `services/platform/app/domain/audit.py`). After an API change: `.venv/Scripts/python infra/scripts/export_openapi.py`, then `npm run api:types` in `frontend/` (CI fails on drift). **A new service** needs: the copier template, a Kafka user in `infra/kafka/users.yml` with its password in every `.env` and in `kafka-init`'s environment and `<PREFIX>_KAFKA_USERNAME`/`_PASSWORD` on its container, an `AUTH_SERVICE_SECRETS` entry, compose services plus `compose.prod.yml` and `compose.staging.yml` overrides, the `images.yml` and `backend.yml` matrices, the `release.yml` health loop, `export_openapi.py`, tests in `infra/tests`, and its keys on the staging host before its first deploy.

**Test helpers.** `mms_common.testing.containers` gives `mongo_uri`, `redis_url`, `kafka_bootstrap`, `seaweedfs` and `clamd` (about a minute to start) as session fixtures, skipped without Docker. `ManualClock.advance(minutes=16)` takes keyword arguments. Seed users: `tech1`, `tech2`, `admin`, `admin_mfa` (a public test TOTP secret), `viewer`, `client_a1`, `client_b1`, `disabled` (`TestIssuer.token(name)`, `.service_token(name)`). Fakes live in each service's `tests/conftest.py` (`FakeMedia`, `FakeOwners`, `FakeJobs`, `FakeScanner`, `FakeStaff`, `FakeRenderer`). Tests that build an app with a lifespan must use the app's own `app.state.mongo`/`app.state.db`. Test audit records go straight into the chain with `audit.record_own(…, to_record(envelope, now))` (the consumer dead-letters unregistered types). Test reports need a unique `subject_ref` per document. Tests carry requirement IDs (`@pytest.mark.req("REQ-3")`, Playwright tag `@REQ-3`); `@smoke` tests need no seed users and run against staging after each deploy; `@phone` runs in the `phone` project, `@webkit` in `webkit`.

## Gotchas (each cost a debugging round)

**This PC (Windows, Git Bash).**
- Docker is not on PATH: `export PATH="$PATH:$LOCALAPPDATA/Programs/DockerDesktop/resources/bin"`. Git Bash rewrites absolute container paths: `MSYS_NO_PATHCONV=1` for `docker compose exec <svc> /abs/path` and `docker run --entrypoint /bin/sh`. Port 27017 is taken by a local MongoDB (the stack uses `MONGO_DEV_PORT`, default 27018, with `directConnection=true`). `jq` is not installed: use `gh … --jq` or `node -e`.
- Python on Windows writes CRLF and cp1252: use `newline="\n"` and `encoding="utf-8"` (a `§` or `…` written as cp1252 makes Vite fail with "stream did not contain valid UTF-8"; CRLF breaks shell scripts mounted into containers; keep `infra/` LF). A Bash heredoc in this tool breaks on an apostrophe and turns `\d` into `d`: write files with the Write tool or a script in the scratchpad.
- The user usually has `npm run dev` running in `frontend/`; it holds `lightningcss`'s `.node` file, so `npm ci` fails with EPERM partway and leaves `node_modules` half-installed (`--silent` hides it). Ask before stopping it. Lockfile-only work (`--package-lock-only`) does not need that; `npm update` does not re-resolve deep dependencies there (delete their lockfile entries and `npm install --package-lock-only`).
- Run each service's tests from its own folder (every service's package is `app`; a script that imports one needs `PYTHONPATH=.` and that folder as working directory). Rough durations: `mms_common` 30 s, platform 40 s, operations 75 s (a full run crawls when another runs beside it: run subsets), auth 2 min, media 2 min (+1 with ClamAV), `infra/tests` 90 s, readiness tests 3 min here, Vitest 6 s, ESLint 1 min, the CI `media` job about 19 of its 20 minutes (a failure at 20 m is the timeout: rerun). A killed pytest run leaves `mms-test-*` containers: `docker ps -a --filter name=mms-test- -q | xargs docker rm -f`. `docker system df` once showed 77 GB of dead test volumes.
- A PC antivirus can cut a loopback connection carrying the EICAR string: the EICAR test goes straight to clamd. Headless Edge `--dump-dom` prints nothing from Git Bash: run it from PowerShell with `Start-Process` and its own `--user-data-dir`. A headless screenshot of an `#anchor` is blank.

**Mongo, Redis, Kafka, SeaweedFS.**
- Inside a Mongo transaction a duplicate-key error aborts the transaction even when caught, and the driver retries until its 120 s timeout: read first (`upsert_if_newer`). `upsert_if_newer` skips equal versions, so a new field on old read-model rows needs a migration that marks them version 0. `stamp()` sets `version: 1`: a collection whose `version` means something else overrides it after stamping.
- mongod 8+ refuses to start on Linux kernels 6.19 to 7.0.13 (SERVER-121912): the test fixture and `compose.dev.yml` set `GLIBC_TUNABLES=glibc.pthread.rseq=1`, and the fixture restarts a container that has not started after 45 s, once. Whether mongod 9 still needs it is unknown: drop it only after a CI run on a failing kernel passes without it. If staging's kernel is upgraded to 6.19+, apply the variable to `compose.yml`.
- A restarted container keeps its `/tmp`, and `fs.protected_regular=2` stops even root from reopening another user's file in a sticky folder: delete such a file before rewriting it (the Mongo key file took staging down, W4-18). A full disk cuts Redis's append-only file short: `redis-check-aof --fix` on the volume, don't delete it.
- Kafka's admin tools run inside the broker against `127.0.0.1:9094` (loopback plaintext), not `kafka:9092`. To replay audit dead letters: stop platform, `kafka-consumer-groups.sh --reset-offsets --to-earliest --group audit --all-topics --execute`, start it. `mms.report.events` must be in a consumer's topic list to reach it (platform's `notification_topics` once missed it).
- SeaweedFS needs `-volume.max=0` and 256 MB volumes (the default 8 slots ran out: "No writable volumes"). WebKit cannot reach `files.mms.localhost` (F6).

**Services and Python.**
- Open Redis with `mms_common.redisconn.connect(url)`, never `Redis.from_url(url)`: the bare client kept dead idle connections, and auth answered 500 *after* committing an organization's deactivation (#204). A revocation written after a commit goes through `revocation.after_commit(...)`, which logs and counts a failure (`revocation_write_failures_total`, alert `RevocationFailed`) instead of failing a saved change. Jobs on `mms_common.jobs` must be safe to repeat.
- Our seven containers run with `cap_drop: [ALL]` and `no-new-privileges`; keep that on any new one.
- FastAPI includes routers lazily: `app.routes` doesn't list them; use `fastapi.routing.iter_route_contexts`. `ValidationFailed(..., code=...)` puts the code in `.extra`. Give `uvicorn[standard]` a lower bound (`>=0.40`) or pip backtracks for 15 minutes. Service images uninstall pip (its vendored copies fail Trivy) and run `apt-get -y upgrade` (Trivy reports a Debian package the day a fix ships). CI installs unpinned libraries: a new release can make a `# type: ignore` unused (redis 8.2, #210); write `[code, unused-ignore]` when the local and CI versions differ.
- Dependabot: `group-by: dependency-name` makes one pull request per dependency for all services; `versioning-strategy: increase-if-necessary` stops it raising `>=` floors.
- The report image is 1.51 GB; Chromium runs as a subprocess with `HOME` and the XDG folders set to its temporary folder (without them it dies with SIGTRAP). `tests/unit/test_charts.py` draws only where `REPORT_CHROMIUM_PATH` or `chromium` resolves (Edge works locally). The PDF test skips where Pango is missing. The pypdfium2 version is pinned in `services/report/visual/Dockerfile` (5.15.0 moved the baselines). A test that sends `visit.rescheduled` needs `changed_fields`. `RCLONE_LOG_LEVEL` is set in the backup image, so no `rclone` call may also pass `--quiet`.
- An existing `infra/.env` needs every key added to `.env.example` since it was copied (`compose.yml` refuses to start without them).

**Nginx and the gateway.**
- A `location ^~ /api/` hides every regex location (all API routes 404): the catch-all stays a plain prefix. Routes of a service that is down answer 503 problem+json. Any change to the CSP also needs `EXPECTED_CSP` in `infra/tests/test_stack.py`.
- The gateway allows **10 sign-ins and public auth requests a minute per address** (`limit_req_status 429`): pages map 429 to "Too many attempts" (`e2e/throttle.spec.ts`); keep a Playwright journey to one login per role and set `test.setTimeout` for long ones; the load test ramps slowly and a virtual user picks its seed user before signing in.

**Frontend, Vite and the service worker.**
- **The precache must stay under 30 files** (`e2e/offline.spec.ts`, F14); it is 29: the next new worker or chunk must make room. Lazy heavy modules are left out through `globIgnores` in `vite.config.mts` (the brand-colour generator, pdf.js, `signature_pad`). Every file under `src/` goes into the one `app` chunk (`codeSplitting`), even behind `import()`: a heavy library stays out only if the importing module is excluded from the `app` group (as `qrCode.ts` is) or the component imports the library with `import()` (Leaflet in `MapView.vue`). jsQR is imported only by `qr.worker.ts`; `qr-scanner` is not used (F16: its `blob:` worker breaks `worker-src 'self'`).
- The app version comes from `frontend/package.json` (`__APP_VERSION__`); bump it for a release, never stamp a commit SHA (every deploy would prompt every phone to reload). "Reload now" reloads on `controllerchange` (F19). After editing `frontend/src`, `npm run build` before Playwright: it tests the built app Nginx serves.
- ESLint is strict: `npm run lint:fix` first, then by hand (one statement per line, `toSorted`, `addEventListener`, catch parameter names, class member order, `String.raw` over escaped backslashes). `tsconfig.app.json` targets ES2023 libs. Leaflet's `L.map` trips `unicorn/no-array-callback-reference`; `leaflet.markercluster` needs `globalThis.L` first. Dates go through `app/format.ts` (September is `Sep`).
- Vitest: `src/test/setup.ts` loads fake-indexeddb for every file (don't import it per file). fake-indexeddb clones a jsdom Blob to an empty object: tests that read a blob back use Node's `File` (`node:buffer`). Mount Vuetify components with `global: { plugins: [createVuetify()] }` and select ids with dots as `[id="a.b"]`.
- Vuetify: `v-chip` with a click handler has no button role (use a real `<button>`); `VTooltip` leaves empty `role="tooltip"` nodes that fail axe (rail tooltips are CSS); `VAppBar` makes buttons `text` (set `variant`). Since **4.3.4 a controlled switch or checkbox stays put until its model changes**: update the model at once, then reconcile with the server (`EmailPreferences.vue`).
- axe: an `aria-label` that differs from the visible text fails `label-content-name-mismatch` (put extra words in `sr-only`); links in running text need an underline; links under 24 px need `inline-flex min-h-6 items-center`. A table row's accessible name is the cells' text as written (CSS uppercase doesn't count).
- Playwright: `page.route` doesn't see requests a service worker makes (the map test blocks service workers); regexes are not whitespace-normalized (`/^Saved/` fails on indented text); leftover visits from earlier runs sort first, so open visits by URL, not `.first()`; WebKit needs a persistent context for Blobs in IndexedDB; Chromium runs with `--ignore-certificate-errors` (no service worker on a self-signed certificate otherwise). A role mismatch on a route shows "We can’t find that page" in place, it doesn't redirect. Global setup seeds auth's users and operations' demo stations.
- In the docs and guides, the password minimum is 12 (W21-3), not 10.

## Planning documents

Read these before writing a new document or any code. Requirement IDs (AUTH-1, REQ-2, VIS-7, …) belong to the PRD. Service, container and route names belong to the TRD. Journey IDs J1–J10 and page routes belong to the AFD.

| File | Document | Version (2026-11-25) |
|---|---|---|
| [docs/PRD.md](docs/PRD.md) | Product Requirements | 1.6 |
| [docs/TRD.md](docs/TRD.md) | Technical Requirements | 2.25 |
| [docs/AFD.md](docs/AFD.md) | App Flow (journeys J1–J10, routes, menus, edge states) | 1.9 |
| [docs/DBD.md](docs/DBD.md) | Design Brief (colour, type, shells, components) | 1.9 |
| [docs/BSD.md](docs/BSD.md) | Background Schema (data location, schemas, access, retention) | 1.12 |
| [docs/IP.md](docs/IP.md) | Implementation Plan (phases 0–8, 25 weeks) | 1.2 |
| [docs/TP.md](docs/TP.md) | Test Plan (levels, rule-enforcement tests, seed users, CI stages, tests by phase) | 1.5 |

Also: the week plans in [docs/plans/](docs/plans/), [docs/security/asvs-l2.md](docs/security/asvs-l2.md), [docs/checks/](docs/checks/), [docs/guides/](docs/guides/), [docs/field-test.md](docs/field-test.md).

- The App Flow file is `docs/AFD.md`. Some older notes call it "APD"; it is the same document.
- [docs/drafts/](docs/drafts/) holds the earlier drafts (Claude, DeepSeek, GPT) and the original `Specification.txt`. The final documents supersede them. Don't edit them, and don't treat them as a source of truth.
- **The local files are the source of truth.** The Claude Doc live copies made in October are stale and carry a note pointing to the local file. Update only `docs/*.md` unless the user asks for the live copies to be brought back in step.
- The documents were written one at a time, each consistent with the ones before it. A new document reuses existing IDs, route names, journey numbers, status names and colour tokens rather than inventing new ones.
- When a decision closes an open question, update every document that refers to it.

### Open-question prefixes

| Prefix | Document | Status |
|---|---|---|
| Q | PRD §12 | Open |
| T | TRD §22 | Open, with defaults; T7 decided (SeaweedFS) |
| A | AFD §7 | A7, A9, A10 decided |
| D | DBD | D1–D4 decided (D1: logo, name and brand colours, 2026-10-17); D5, D6 open |
| B | BSD | B2–B6 closed or decided; B1 open |
| P | IP | P5 decided; P1–P4 open |
| V | TP | V1–V5 open, with defaults |

### Decisions already made (don't reopen them)

- **D2:** dark mode ships in v1. A Light / Dark / System setting is stored per user.
- **D3:** ApexCharts (`vue3-apexcharts`) for dashboards, and for summary-report charts in PDFs via headless Chromium.
- **D4:** clients see staff names (`{id, name}`) on requests and visits. Never send staff email or phone to clients.
- **B5:** stations never change owner organization.
- **B6:** there are no personal-data erasure requests.
- **UI framework:** Vuetify 4 + Tailwind CSS 4 replaced PrimeVue 4 (TRD ADR-11, DBD 1.1). Icons are Material Design Icons (`@mdi/js`), not PrimeIcons.
- **Plan:** one developer working with Claude Code. Phase 0 + PRD phases 1–7 (19 weeks) + 2-week buffer + Phase 8 pilot = **25 weeks** to go-live. A staging release goes out after each build phase, for staff only; clients first use the system in the pilot. Notification email is in Phase 1.
- **Engineering review, 2026-10-16** (TRD 2.0, PRD 1.1):
  - **Five services** instead of nine (ADR-1). No integration stub; Nginx returns 501 on `/api/v1/integrations/`.
  - **Kong removed**: Nginx is the gateway (ADR-5).
  - **SeaweedFS** replaces MinIO (ADR-6, T7).
  - **One owner per station** on a visit; no offline merge (ADR-18, OFF-11).
  - **Parallel visits** are allowed; request status is derived from them (ADR-17).
  - **Reopening a report** during Client Review returns the request to In progress; after Closed it stays Closed (RPT-6).
  - **Offline PIN unlock** for staff (ADR-20, AUTH-12).
  - **Files fail closed**: staff-only until the owning service shares them (ADR-19).
- **Motion, Settings and brand colours, 2026-10-17** (DBD 1.5, TRD 2.2, AFD 1.4, PRD 1.3, BSD 1.3; docs site decisions W4-10 to W4-13):
  - **GSAP** animates the app shell; every tween uses `dur()` from `app/motion.ts`, so reduced motion makes it instant.
  - **Brand colours are a Material 3 theme**, changeable by admins **for everyone** on Settings. Status, success and warning colours never come from the theme.
  - **Person avatars** may use a brand gradient: the one exception to DBD's "no decorative gradients".
- **Building auth, 2026-10-17** (TRD 2.1, PRD 1.2, AFD 1.2, DBD 1.3, BSD 1.2; docs site decisions W3-1 to W3-9):
  - **Account links are minted on send**: no token in any event; notification calls auth `POST /internal/account-links` when it sends the email.
  - **`/register` takes the organization name as free text**; there is no public list of client organizations. The admin links or creates the organization at approval.
  - **Access tokens are revoked at once** (disabling, org deactivation, reset, role change) through a Redis list every service checks.
  - Refresh expiry slides (30 days from the last refresh); the grace successor is sealed; the breached-password check fails open with a fallback and a metric; audit appends serialize on the `audit_state` head.

## Architecture (TRD)

- **Five FastAPI services**, split by business capability:
  - `auth`: users, organizations, tokens.
  - `operations`: stations, sensors, documents and configs; requests; visits and sync. Its modules share one database and change together in one transaction.
  - `media` (+ `media-worker`).
  - `report` (+ `report-worker`): visit, close-out, client-form, label and summary PDFs; the dashboard read model.
  - `platform`: the notification and audit modules, with two databases and two DB users.
- **Edge and gateway:** Nginx handles TLS, the SPA, path routing to services, `limit_req` rate limits, `X-Request-ID`, and the `files.` host for SeaweedFS. Nginx does not verify JWTs; each service does.
- **Data:**
  - A single MongoDB 9 replica set (`rs0`) with **one database and one DB user per service** (`platform` has two).
  - Files go to SeaweedFS (S3 API) through presigned direct uploads.
  - Kafka 4.x (KRaft) carries domain events between services.
  - Redis 7.4 holds jobs (`mms_common.jobs`, not arq), cache, leader leases, the login throttle and WebSocket pub/sub.
- **Frontend:** a Vue 3.5 + TypeScript PWA built with Vite, Vuetify 4 (`vite-plugin-vuetify`, brand themes + global defaults), Tailwind CSS 4 (no preflight, in a cascade layer before `vuetify-final`), Material Design Icons (`@mdi/js`), Pinia, Dexie (offline), Workbox (`injectManifest`) and Web Locks.
- **Runtime:** Docker Compose on the organization's own servers. Python 3.13.

## Rules that are not negotiable

1. **Never access another service's database.** To get another service's data, call its `/internal/*` endpoint with a service token, or consume its events. (Modules inside `operations` share its database.)
2. **All state changes go through the domain state machine and the outbox.** Update the record and insert the outbox event in **one Mongo transaction**. Never produce to Kafka directly from a request handler. The outbox relay runs only under the service's Redis leader lease.
3. **Org scoping lives in the repository layer** (`repo/`). For a client, every query is merged with `{"org_id": user.org_id}` (`owner_org_id` for stations, `current_org_id` for sensor units). Endpoint code must not be able to bypass it.
4. **A resource outside the user's scope returns 404, not 403** (ADR-16).
5. **Viewers never mutate.** Every mutating route uses `require_roles(...)` without `viewer`, and a test asserts it.
6. Internal comments, draft reports, staff-only documents and config versions are filtered out for clients in the repo layer. **Files start `visibility = staff`** and become client-visible only through `media.visibility_requested`.
7. `domain/` has no FastAPI, Mongo or Kafka imports.
8. Times are stored in UTC. Each station has an IANA time zone that is used for display only.
9. IDs are UUIDv7, generated on the client for anything that can be created offline. Sync operations carry idempotency keys (`op_id`).
10. The audit collection is insert-only and hash-chained. No code updates or deletes audit records.
11. Finalized visit-report versions are immutable. A change means reopening the report as a new version.
12. Mongo queries are built from typed values only. Never pass raw operators from user input.

Also by design (TRD 2.0):

- Request status from Assigned to closure comes only from `derive_status` (TRD §3.2.2), never set by hand.
- Only a station's owner writes its work record.
- Consumers write `processed_events` in their own transaction and guard read models with `aggregate_version`.
- Read models are rebuilt from `/internal/snapshot/*` with `backfill.py`, never by replaying the outbox.
- The service worker never caches API responses.

## Code layout (TRD §3.0, §13.1, §19)

```
services/<name>/app/
  main.py  config.py  api/  domain/  repo/  events/  jobs/  migrations/
  (operations groups each layer by module: stations/ requests/ visits/)
services/<name>/tests/   unit (domain) · api (httpx + testcontainers) · contract (events)
libs/mms_common/         auth, events, outbox, kafka, consumer, mongo, logging, errors, ids, time, snapshot
templates/service/       copier template; create new services from it
frontend/src/            app/ api/ features/ offline/ charts/ components/ stores/ sw/
infra/                   compose*.yml, nginx/, kafka/topics.yml, seaweedfs/, scripts/
```

Every service exposes `GET /health`, `GET /ready`, `GET /metrics` and OpenAPI at `/docs` (disabled in production).

## Naming conventions

- **Public API:** `/api/v1/<plural-kebab-resource>` (for example `/api/v1/sensor-units`). Actions are `POST /{id}/<verb>` (`/approve`, `/claim`, `/verify`). Services mount their own prefix; Nginx routes by prefix and passes the path unchanged. Declare literal paths (`/geo`, `/mine`, `/due`) before `/{id}`.
- **Internal API:** `/internal/...`. Nginx never routes it (returns 404).
- **Kafka topics:** `mms.<service>.events` (`auth`, `operations`, `media`, `report`). Dead letters: `mms.dlq.<consumer-service>`. The message key is the root aggregate ID: `request_id` for request, comment and visit events; `station_id` for station and sensor events.
- **Event types:** `<entity>.<past_tense>` (`request.approved`, `visit.ended`, `report.finalized`). Schemas are Pydantic models in `mms_common.events`, keyed by `(type, version)`, and every envelope carries `aggregate_version`. A breaking change gets a new `version`.
- **Environment variables:** a prefix per service via `pydantic-settings`: `AUTH_`, `OPS_`, `MEDIA_`, `REPORT_`, `PLATFORM_` (for example `OPS_MONGO_URI`, `OPS_AUTO_CLOSE_DAYS`).
- **Migrations:** forward-only `migrations/NNNN_*.py`, run on startup under a lock in `_migrations`.
- **Mongo fields:** snake_case. Use the field and collection names in TRD §5 and docs/BSD.md.

## Frontend and design

- docs/DBD.md is the design source of truth. Brand tokens live in [frontend/src/app/theme/brand.ts](frontend/src/app/theme/brand.ts), which defines Vuetify's `light` and `dark` themes. Tailwind reads the same colours through `@theme` mapped to Vuetify's `--v-theme-*` variables ([tailwind.css](frontend/src/app/theme/tailwind.css)); Tailwind's default palette is removed.
- Brand and neutral colours come from a **Material 3 theme** (W4-12): built in from `app/theme/material-theme.json` (primary `#0A6780`, seed `#026D88`), replaceable by admins for everyone; `app/theme/material.ts` maps it onto the token names, so pages only ever use tokens. **Status colours are reserved** for request and station status (chips, map markers, timeline dots) and are never used for decoration.
- Fonts (decided 2026-10-20, permanent): **Google Sans** for titles (h1 to h4, `legend`, KPI numbers via `font-heading`), **Roboto Flex** for all other text, **JetBrains Mono** for references, serials, hashes and file names; all from `@fontsource-variable`, bundled (no CDN), only the Latin subsets precached. Icons are Material Design Icons as SVG from `@mdi/js` (outline variants), listed in `app/theme/icons.ts`. No icon font.
- Staff and clients use the **app shell** (DBD "The shells"): rail · interactive pane · view, as square tiles on `ground`. A page fills the view with `PageBody` (title, subtitle, `#actions`, `back` for phones) and puts its list or controls in the pane with `<PaneContent>`; a record it opens goes in the URL and is reported with `usePaneSelection()`. No bordered cards inside tiles. Rail tooltips are CSS (`RailTip`): Vuetify's `VTooltip` leaves empty `role="tooltip"` nodes that fail axe. Below 1024 px a docked bottom bar replaces the rail (W4-14). The field shell (phone: top bar from `app/shells/fieldBar.ts`, bottom nav, sync badge) holds `/visits/:id/field`: the visit's stations, then a station's board (`?station=`), and a sticky End visit that lands on `/sync` (W12-1 to W12-3). Buttons are pills, secondary buttons tonal (DBD 1.9). Public pages, including `/unlock`, use the split panel.
- Dark mode switches Vuetify's theme (`useTheme().change()`) and the `.app-dark` class on `<html>` together ([stores/theme.ts](frontend/src/stores/theme.ts)); Tailwind's `dark:` variant uses `.app-dark`. `public/theme-init.js` is an external script because the CSP is `script-src 'self'`, which rules out inline scripts.
- The cascade layer order lives in `public/layers.css`, which must stay the first stylesheet in `index.html`: a production build links lazy chunks' CSS before the main bundle, and the first file to name a layer fixes its place. The CSS import order in `main.ts` is still deliberate (an ESLint import-sort exception).
- Tailwind's preflight is off, so `base.css` adds the few resets Vuetify's leaves out (plain `button` and `a`, in the `vuetify-core` layer), the `on-*` text colour for `bg-*` (filled buttons rely on it), full-contrast field hints, the focus ring and reduced motion. `VAppBar` makes buttons inside it `text`: set `variant` explicitly there.
- Use Vuetify for components and Tailwind for layout and spacing. Avoid custom component CSS unless there is no other way.
- Vuetify's own utility and colour classes are off (`$utilities: false`, `$color-pack: false`, `theme.utilities: false`), so `rounded-*`, `bg-*`, `text-*` and spacing classes are always Tailwind's. Set the look through global `defaults` in `app/theme/vuetify.ts`, not per-page props. Classes Vuetify adds from props (`rounded-md`, `rounded-card`, `elevation-8`) are safelisted in `tailwind.css`. Vuetify's display thresholds match Tailwind's breakpoints (640/768/1024/1280/1536).
- Viewers see read-only views. Action buttons are hidden, not disabled.
- [design/awesome-design-md/](design/awesome-design-md/) is a reference library of other brands' DESIGN.md files (the `design-md-reference` skill). It is for inspiration only and never overrides DBD.md.

## UI skills (required when building UI)

The project skills in [.claude/skills/](.claude/skills/) **must be used** when designing, building or reviewing any screen, PDF or email. Load each skill with the Skill tool at the step where it applies.

**Order of precedence:** docs/DBD.md, then TRD §13.2 conventions, then the skill. Several skills have their own house style (warm monochrome palettes, custom fonts, gradients, GSAP motion, asymmetric or randomised layouts, CDN assets). Use their quality rules, such as hierarchy, spacing, avoiding generic AI patterns and polish, but keep DBD's tokens, palette, fonts, shells and components. Follow Vuetify + Tailwind with no custom component CSS, the CSP (`script-src 'self'`, self-hosted fonts) and `prefers-reduced-motion`.

Claude Code has **no image-generation tool**. The skills that generate images (`imagegen-frontend-web`, `imagegen-frontend-mobile`, `brandkit`, and the image step of `image-to-code`) can't run here. Mock-ups are HTML pages instead.

### Workflow for each screen

1. **Read** the screen's section in DBD.md and its journey in AFD.md.
2. **Reference:** use `design-md-reference` to borrow a specific pattern (a table, card, dark palette or token scale).
3. **Mock up:** build a static HTML mock-up of the screen from DBD tokens (Google Sans, Roboto Flex, slate neutrals, Horizon blue, status colours; a phone frame for field screens; light and dark), applying the quality rules from `design-taste-frontend`, `high-end-visual-design` and `minimalist-ui`. Publish it as a private artifact and get the user's approval before building.
4. **Build:** implement the approved mock-up in Vue with Vuetify components and Tailwind layout, matching it closely.
5. **Review:** run `web-design-guidelines` on every screen, together with the axe check in the definition of done. Check UI text and email copy against DBD's "Voice and microcopy" with `writing-guidelines`.
6. **Polish:** use `redesign-existing-projects` for improvement passes on screens that already exist.

### When each skill applies

| Skill | Use it for | Limits in this project |
|---|---|---|
| `design-md-reference` | Patterns from other design systems | Inspiration only |
| `design-taste-frontend` | Avoiding generic AI patterns on every screen and mock-up; art direction for public pages (login, register, reset, unlock) | Its landing-page directions and palettes don't apply to app screens |
| `high-end-visual-design` | Spacing, depth and card treatment | Keep DBD surfaces, corners and shadows |
| `minimalist-ui` | Calm document-style layouts: request detail, visit report editor, station pages | Slate neutrals, not warm monochrome |
| `stitch-design-taste` | Turning DBD.md into an agent-friendly `DESIGN.md` and keeping it in sync | DBD.md remains the source |
| `industrial-brutalist-ui` | Structure for dense data views: audit log, summary tables, calibration due list | Rigid grids and tabular figures only; none of its decay effects or terminal styling |
| `gpt-taste` | Composition ideas for public pages | No GSAP scroll effects or AIDA structure in app screens; respect reduced motion |
| `image-to-code` | Its implementation and quality rules only (matching a design closely, no cards inside cards), applied to approved HTML mock-ups | Its image-generation step can't run here |
| `redesign-existing-projects` | Audit and upgrade passes on built screens | Must not break behaviour or role rules |
| `impeccable` (4.8.2, from impeccable.style; agents `impeccable-*` in `.claude/agents/`) | `/impeccable critique`, `audit`, `polish`, `harden`, `clarify`, `adapt` on built screens and mock-ups; reads `PRODUCT.md` and `DESIGN.md` (root; North Star "The Field Logbook", built-in primary "Caribbean Depth") and `.impeccable/design.json` | DBD.md wins. Root `DESIGN.md` is **derived** from `frontend/src/app/theme/` by `/impeccable document` (2026-11-19): after a change to the theme tokens, DBD or the shells, run it again (choose refresh) so it does not drift. `design/DESIGN.md` is a separate Stitch export. Never let Impeccable replace the visual world ("world discovery", redesign): the world is DBD and the built app. Its design hooks are not switched on. Its engine binary is git-ignored and downloaded and checked on first use; update with `npx impeccable update` and commit the result |
| `pwa` | Loaded first for every task (see "Think like a PWA expert first"); field screens, install and update prompts, `/unlock`, `/sync` | Project skill; TRD and AFD win over it |
| `web-design-guidelines` | Required review of every screen | — |
| `writing-guidelines` | Microcopy, empty states, errors and emails | DBD voice wins |
| `imagegen-frontend-web`, `imagegen-frontend-mobile`, `brandkit` | Not used: they need an image-generation tool | Revisit only if one becomes available (for example for D1 branding) |

`design-taste-frontend-v1` and `design-taste-frontend-v2-experimental` are older versions kept for compatibility. Use `design-taste-frontend` instead.

## Commands

Developer docs: open [docs/index.html](docs/index.html) in a browser (no server needed). To check every diagram renders, with Edge:

```sh
msedge --headless=new --virtual-time-budget=40000 --dump-dom "file:///<repo>/docs/index.html" | grep -c 'id="mmd-'   # = number of diagrams
```

Frontend (run in `frontend/`):

```sh
npm install
npm run dev          # dev server on http://localhost:3000 (no service worker; build + preview for that)
npm run type-check   # vue-tsc (app, worker, tests)
npm run lint         # ESLint (eslint-config-vuetify); lint:fix to fix
npm test             # Vitest unit tests
npm run build        # type-check + production build (Nginx serves frontend/dist)
npm run test:e2e     # Playwright against the running local stack (seeds it first); --project=chromium
npm run api:types    # regenerate src/api/types from openapi/*.json
npm run brand        # rebuild the logo files and PWA icons from /logo
```

OpenAPI schemas for the frontend (run from the repo root): `.venv/Scripts/python infra/scripts/export_openapi.py`, then `npm run api:types`. CI fails if either drifts. Playwright needs `npx playwright install chromium` once; its Chromium runs with `--ignore-certificate-errors` because Chromium won't register a service worker on the stack's self-signed certificate.

SeaweedFS spike (run in `infra/spikes/seaweedfs/`; needs Docker):

```sh
docker compose up -d --build
docker compose run --rm spike python check.py   # then open http://localhost:8080
docker compose down -v
```

Python setup (once, from the repo root; one venv for the library, the template and infra tests). On Windows the venv's tools are in `.venv/Scripts/`, elsewhere `.venv/bin/`:

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -e "libs/mms_common[dev]" --config-settings editable_mode=compat
.venv/Scripts/python -m pip install copier import-linter pytest-cov uvicorn pydantic-settings boto3
```

`editable_mode=compat` lets mypy see `mms_common` from a service.

Shared library (run in `libs/mms_common/`; tests that need MongoDB, Redis or Kafka start throwaway containers on the stack's pinned images, and skip without Docker):

```sh
../../.venv/Scripts/python -m pytest -q
../../.venv/Scripts/ruff check .
../../.venv/Scripts/mypy mms_common
```

Create a service from the template, then check it (run from the repo root):

```sh
.venv/Scripts/copier copy templates/service services/<name> --data service_name=<name> --data env_prefix=<PREFIX>
cd services/<name>
../../.venv/Scripts/python -m pip install -e . --config-settings editable_mode=compat
../../.venv/Scripts/python -m pytest -q        # includes the architecture checks
../../.venv/Scripts/ruff check . && ../../.venv/Scripts/mypy app
```

A service (run in `services/<name>/`, for example `auth` or `platform`; API tests start throwaway Mongo and Redis):

```sh
../../.venv/Scripts/python -m pip install -e ".[dev]" --config-settings editable_mode=compat
../../.venv/Scripts/python -m pytest -q --cov      # unit, API, matrix, architecture
../../.venv/Scripts/ruff check . && ../../.venv/Scripts/mypy app
```

Local stack (run in `infra/`; needs Docker; Nginx serves the last `npm run build` from `frontend/dist`):

```sh
cp .env.example .env                              # dev-only values; never commit .env
docker compose -f compose.yml -f compose.dev.yml up -d --build
docker compose -f compose.yml -f compose.dev.yml exec -e AUTH_SEED_PASSWORD=dev-seed-password-1 auth python -m app.cli seed
../.venv/Scripts/python -m pytest tests -q        # gateway, CSP, DB isolation, audit role, topics, buckets, J1/J2 into the audit chain
docker compose -f compose.yml -f compose.dev.yml down      # add -v to delete the data volumes
```

- Demo stations (after auth's seed): `docker compose -f compose.yml -f compose.dev.yml exec operations python -m app.cli seed` (five made-up stations for organizations A and B, with sensors). A station export: copy it in (`docker compose cp stations.xlsx operations:/tmp/`), then `exec operations python -m app.cli import-stations /tmp/stations.xlsx` (a dry run; add `--commit`). Example requests for the requests screens: `exec operations python -m app.cli seed-requests [--count 50]` (made-up "[Example] ..." requests in every status for the stations already there, written with no events so nothing fake enters the audit chain; refuses production), and `exec operations python -m app.cli remove-example-requests` to delete them (it keeps and names an example someone worked on). **Never run `seed`, `seed-requests` or the load test on staging: it is the pilot site.** Never commit a real export: the repo is public. The existing system's exports (W5-8): `exec auth python -m app.cli import-orgs /tmp/org.json`, then `exec operations python -m app.cli import-stations /tmp/site.json` (each a dry run; add `--commit`). Its `entities` documents hold MQTT usernames and passwords (`web`, `device`): ask for the export without them (it may come with them anyway: keep only `id`, `name`, `organization` and `code` before copying it anywhere), never put them in the repo, a fixture or a log, and delete the files from the containers afterwards (`exec -u root auth rm -f /tmp/org.json`: `docker compose cp` leaves them owned by root, so the service user can't).
- Seed users (TP): `admin@example.org`, `tech1@example.org`, `client.a1@example.org`, `viewer@example.org` and the rest of `mms_common.testing.seed.SEED_USERS`, all with `AUTH_SEED_PASSWORD`. On staging and production, create the first admin with `python -m app.cli create-admin --email … --name …` (password from `AUTH_ADMIN_PASSWORD` or a prompt); `seed` refuses production.

- App: `https://mms.localhost` (accept the self-signed certificate once). Files host: `https://files.mms.localhost`. Mailpit: `http://127.0.0.1:8025`.
- Published on 127.0.0.1 only, for debugging: MongoDB on `MONGO_DEV_PORT` (default **27018**, because a locally installed MongoDB often holds 27017; connect with `directConnection=true`), Redis 6379, SeaweedFS S3 8333.
- To check the gateway config alone: `docker compose -f compose.yml -f compose.dev.yml exec nginx nginx -t`.
- Rebuild the report read model: `exec report python -m app.cli backfill` (there is no cross-service wrapper). Check the audit chain: `exec platform python -m app.cli verify-audit`.
- The local stack has no hot reload: rebuild the changed service (`up -d --build <svc>`), and `npm run build` for the frontend.

## Definition of done (IP)

A feature is done when:

- unit and API tests pass, including org scoping and 404 for out-of-scope records
- new routes are in the authorization matrix, and new tests carry the requirement IDs they cover (`@pytest.mark.req("REQ-3")`, Playwright tag `@REQ-3`); see docs/TP.md
- Ruff, mypy, ESLint and vue-tsc report no errors
- OpenAPI is regenerated, and the event schemas in `mms_common.events` and the audit mapping (PRD AUD-1) are updated
- screens work in light and dark themes and pass an axe check (WCAG 2.2 AA)
- new or changed screens have passed a `web-design-guidelines` review
- changes to `frontend/src/sw/`, `frontend/src/offline/`, caching headers or the CSP pass the `pwa` skill's merge checklist ([checklists.md](.claude/skills/pwa/references/checklists.md))
- the developer docs site ([docs/index.html](docs/index.html)) describes what was built: status, schemas, routes, events, config, decisions, the phase's chosen charts and a changelog entry (see "Developer documentation site")
- CI is green and the build is deployed to staging

Coverage targets: 90% for `domain/`, 70% overall.

## Working with the user

- Planning documents are written **one at a time**, in the order the user names them ("now let's work on: …"). All seven live in `docs/` as Markdown; edit the local files.
