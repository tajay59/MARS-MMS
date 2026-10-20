# CLAUDE.md

AWS-MMS (Automatic Weather Station Maintenance Management System). A self-hosted web app for maintaining weather stations the organization runs for external client organizations in several countries. Clients request work and sign it off. Staff plan, record (offline as well) and report site visits.

## Think like a PWA expert first (required)

AWS-MMS is a PWA: technicians record whole visits on iPhones and Android phones with no signal, and nothing may be lost or duplicated. **Before starting any task in this repo (code, review, plan or document), load the `pwa` skill ([.claude/skills/pwa/](.claude/skills/pwa/SKILL.md)) with the Skill tool and answer its pre-flight questions.** For back-end-only work this takes seconds, but still check the effect on the device: sync contracts, idempotency, auth refresh, caching headers, CSP, presigned uploads. The skill holds the PWA rules from the TRD, verified browser facts (iOS Safari first), the vite-plugin-pwa, Workbox and Dexie patterns, PWA work per phase, the open findings (F1–F14) and the sources. When browser reality and a planning document disagree, raise it as a finding; don't work around it silently. A `SessionStart` hook in [.claude/settings.json](.claude/settings.json) repeats this reminder at the start of every session and after `/clear` or compaction (text in [.claude/hooks/pwa-session-start.json](.claude/hooks/pwa-session-start.json)).

## Current state

**Planning is done; Phase 1 (Foundations) W2, W3 and W4 are built**: the frontend shells, auth and admin screens, the minimal service worker, Playwright J1/J2, the account emails, the release pipeline, Kafka SASL/SCRAM (W4-16) and all twelve Phase 1 charts. Staging is live and every merge to `main` deploys to it. **The W4 checks on staging passed on 2026-10-18**: register → approve → log in → reset into the audit chain (36 records, `verify()` clean; the IP Phase 1 exit criterion), and the update prompt between two real releases (release 0.1, `Version 0.1.0` on the public pages, decision W4-17). **The Android phone check passed on 2026-10-18** (issue #8): install, offline shell, session, the update prompt in the installed app. It measured the first install at 180 s; fixed by W4-19 (F14: six files at a time, 19 precached files instead of 71, a failed install retried): 31 s on the same phone. **Still open for Phase 1:** the same check on an iPhone. **Phase 2 W6 (documents and the media service): the backend and the upload engine are built** (branch `feat/p2-w6-documents`, 2026-10-19): `services/media` (documents path), operations' documents, configuration versions and calibration certificates, a Redis job queue (`mms_common.jobs`), `src/offline/upload.ts`, and the screens, approved from the "AWS-MMS W6 screens" canvas and now built (2026-10-19): the station Documents and Configurations tabs with their upload and new-version dialogs (`ModalSheet`: a dialog, a bottom sheet on phones), the Sensors catalogue (`/sensors/:id?`, with model documents and units) and Calibration due (`/calibration`). Decisions W6-1 to W6-9 in the docs site. **Phase 2 (Stations) W5: the backend is built** (branch `feat/p2-w5-stations`): the `operations` service's stations module, the station import and a demo seed. The **station list and page are built** (`/stations/:id?`, from the approved [mock-up](https://claude.ai/artifact/RHYuVaenPystMRuSvLrAH4)) and so is the **station form** (branch `feat/p2-w5-station-form`, decision W5-10: `/stations/new` and `/stations/:id/edit` on the same route, from the approved [mock-up](https://claude.ai/artifact/5dQNyBebUPmfTUowrdXhWr); `GET /api/v1/stations/places` gives the time zones), and **T4 is answered** (decision W5-8): the organization's existing system is a MongoDB with `entities` and `sites` collections; a one-off `mongoexport` of each (credentials removed) goes in with `import-orgs` then `import-stations`. **The export arrived on 2026-10-18** (8 organizations, 50 stations; kept outside the repo): the dry run is clean after raising parameter codes to 32 characters and checking the 40-parameter limit in the import. **Imported into staging on 2026-10-18** (decision W5-9: real data on staging, not anonymized): 8 organizations and 50 stations, no errors; a rerun skips all 50, and the files were deleted from the host and the containers. The repo holds the planning documents, the design reference library, project skills (including the `pwa` expert skill), the **frontend** in [frontend/](frontend/) and the backend.

- [frontend/](frontend/) (W4, from the approved mock-ups in the "AWS-MMS W4 screens" design canvas): the public split panel, the **app shell** for staff and clients (decision W4-9, DBD 1.4: square tiles 5 px apart on the `ground` colour: a 64 px rail of section icons with CSS tooltips, an interactive pane with the section's pages as tabs and the page's list or controls via `PaneContent`, and a view filled by `PageBody`; phones get full-bleed panes, and below 1024 px a docked bottom bar replaces the rail (W4-14); sections in `app/navigation.ts`), the field shell, router guards and `next` (AFD §5.2), `app/auth/session.ts` (access token in memory, refresh under the Web Lock `mms-auth-refresh`, BroadcastChannel `mms-auth`), typed API clients generated from `openapi/auth.json`, the pages Log in, Register, Waiting for approval, Forgot password, Set password (reset and invitation), My profile, Registrations (message-style rows with a gradient initials avatar, `UserAvatar`, and a short list time, `formatListTime`; decisions W4-13, W4-15), Users, **Settings** (`/admin/settings/:part?`: Appearance and Brand colours, W4-11), Sync, a first Dashboard and **Stations** (`features/stations/`: the list with filters in the URL, search on code, name and external ID, and the station page's Overview, Sensors and Calibration tabs; W5); pages of later phases show `PlannedPage`. **Brand colours** (W4-12) come from a Material 3 theme: the built-in `app/theme/material-theme.json`, or the organization's from `GET /api/v1/auth/branding` (kept in `localStorage` `mms-branding`; `stores/branding.ts`), mapped onto the DBD tokens by `app/theme/material.ts`; status colours stay fixed in `brand.ts`. **Motion** (W4-10) is GSAP through `app/motion.ts` (pane width on Material 3's emphasized curve, page and pane-list entrances, a record rising in through `PageBody`'s `record`, row press `pressDown`/`pressUp`, rail hover, sliding indicator, tooltips; W4-15), instant under reduced motion or Settings › Animations off. The minimal service worker and manifest (F5: precache, navigation fallback, update prompt; F9 chunk errors, F13 safe areas). The MARS-MMS logo from `/logo` (`npm run brand`). 88 Vitest tests and 12 Playwright tests (J1, J2, invitations, offline shell, the update prompt between two releases, gateway smoke, rail tooltips, stations for a technician and a client; axe light and dark, CSP). Playwright's global setup seeds auth's users and operations' demo stations. Dates go through `app/format.ts`, which writes September as `Sep` (newer ICU writes `Sept` in en-GB). Tests tagged `@smoke` need no seed users and run against staging after each deploy.

The backend:

- [libs/mms_common/](libs/mms_common/): `ids` (UUIDv7, seeded for tests), `time` (injectable clock), `errors` (problem details), `logging`, `events` (envelope + `(type, version)` registry), `mongo`, `outbox` (transactional add, relay under the Redis leader lease), `consumer` (TRD §8.5 rules: dedupe, retry, DLQ), `snapshot` (backfill paging, `aggregate_version` guard), `kafka`, `web` (request IDs, error handlers, `/health` `/ready` `/metrics`), `checks` (no-direct-produce); since W3 also `auth` (EdDSA tokens, JWKS cache, Redis revocation list, `require_roles`/`require_staff`/`require_service`, `actor_for`, `scoped`), `events.auth` (auth event schemas), `migrations` (forward-only, `_migrations` lock), `cron` (Redis lock per run), `relay` (the outbox run loop) and `testing` (seed users + `TestIssuer`, authorization `Matrix`, `find_leaks`, container fixtures as the pytest plugin `mms_common.testing.containers`).
- [templates/service/](templates/service/): the copier service template. A generated service runs migrations on startup, the outbox relay under its lease and JWT auth from JWKS. Its tests run import-linter (rule 7; layers `api → jobs → events → repo → domain`), the no-direct-produce check (rule 2) and an empty authorization matrix, and pass unchanged in both variants (`produces_events` true and false).
- [services/auth/](services/auth/) (W3): everything in TRD §3.1, plus `POST /internal/account-links` (reset and invitation links are **minted on send**, never put in an event), `GET`/`PUT /api/v1/auth/branding` (the organization's brand colours in the `settings` collection, `branding.updated` audited; W4-12) and `python -m app.cli create-admin | seed | import-orgs FILE [--commit]` (organizations from the existing system's `entities` export; W5-8). Organizations have `short_name` and `external_id` (unique where set). 143 tests, including the authorization matrix, the client leak check, the refresh race, JWT attacks and injection.
- [services/operations/](services/operations/) (W5): the stations module (TRD §3.2; decisions W5-1 to W5-7). Layers are grouped by module (`app/{domain,repo,api}/stations/`). Stations (scoped by `owner_org_id`; clients get `qr_token` and `current_config_version` empty), `GET /stations/facets`, sensor models (`key` unique), sensor units with `POST /sensor-units/{id}/install` and `/remove` (the only way in and out of `installed`; W5-1), installations, calibrations (newest sets the due date; a fail flags `calibration_failed`), `GET /calibrations/due`, `POST /stations/import` (dry run by default; W5-4) and `/internal/snapshot/{stations|sensor_units|calibrations}`. It keeps a copy of the organizations (`organizations`, W5-3): consumer group `operations` on `mms.auth.events`, plus auth's snapshot at every start with `OPS_SERVICE_SECRET`. `python -m app.cli import-stations FILE [--sensors FILE] [--commit] | seed | backfill-orgs`; the import also reads the existing system's `sites` export (`.json`, one station per device, matched to organizations by `entity` → `external_id`; W5-8). Stations have `external_id` (unique where set; the list's search matches it). Countries and time zones come from `tzdata` (W5-7). 84 tests (95%).
- [services/media/](services/media/) (W6): the documents path of TRD §3.3 (images and video: Phase 4). Presigned multipart uploads straight to the files host; `POST /uploads` is idempotent by `media_id` and joins an open upload of the same file by the same person; `complete` takes no part list (media lists the parts and checks their sizes); the checks (SHA-256, magic bytes, ClamAV) run in `media-worker` (`python -m app.worker`) from a Redis queue; `MEDIA_SCAN_MODE=clamd|off`, **`off` is refused in production** (staging runs `off`: T8). Fail-closed visibility from `media.visibility_requested`; cron `abort_stale_uploads` and `reconcile`. 116 tests against real SeaweedFS, Mongo and Redis, plus a real ClamAV. Operations' side (W6): `/api/v1/documents` (created `pending`, `available` after `media.processed`; versions by `supersedes_id`; clients see current, client-visible, clean documents, and a model's only while it is installed at their stations), `/api/v1/stations/{id}/config-versions` (only `ready` files; the `version` field is the number), `GET /internal/attachable`, a calibration's `certificate_media_id`. The frontend engine is `src/offline/{upload,transport,hash}.ts` (no Vue; 34 tests); it refuses files over 64 MiB until the incremental hasher (F4).
- [services/report/](services/report/) (W7): the skeleton of TRD §3.4 with the label sheet (QR-6). `POST /api/v1/reports/labels` (admin; 1 to 200 stations, optional `contact_phone`, default `REPORT_LABEL_CONTACT_PHONE`) writes a `report_jobs` record and queues it on Redis; `report-worker` (`python -m app.worker`) reads the labels from operations' `POST /internal/labels` with a service token, draws A4 sheets of 10 (2 x 5, 98 x 55 mm, black on white) with Jinja and WeasyPrint (`app/templates/{base,labels}.html.j2`, `print.css`; the image installs Pango, Inter and JetBrains Mono), stores `labels/{job_id}.pdf` in `mms-reports` and `GET /api/v1/reports/jobs/{id}` (the requester only) returns a 10-minute inline link. Layers as media: `domain/labels.py` (pagination, phone check), `repo/{jobs,operations,render,storage}.py`, `jobs/labels.py`, `api/reports.py`. 59 tests; the PDF test skips where Pango is missing. No events yet.
- [services/platform/](services/platform/) (W3, W4): the audit module (consumer group `audit` → hash chain in the `audit` database, `verify()`) and the notification module's account emails (consumer group `notification` → `email_queue` → the sender job, which calls auth `/internal/account-links` at send time and sends over SMTP; Mailpit locally). The emails say MARS-MMS (decision W4-6). The rest of notification: Phase 3.
- [infra/](infra/): `compose.yml` + `compose.dev.yml` (Nginx gateway, MongoDB `rs0` with one user per service database and an insert-only audit role, Redis, Kafka KRaft with SASL/SCRAM (one user per service, ACLs from `infra/kafka/users.yml`, applied by `kafka-init`; controller and plaintext listeners on loopback only, W4-16), SeaweedFS with per-service S3 keys and the four buckets, Mailpit, self-signed TLS) and `infra/tests/test_stack.py`. Since W3 it also runs the `auth` and `platform` containers, and since W5 `operations` (built from the repo root; `.dockerignore` keeps the context small) and a `dev-secrets` one-shot that makes the auth signing key in `infra/secrets/` (git-ignored). Routes of a service that is down answer 503 problem+json.
- **Verified 2026-10-17 (W3):** `mms_common` 91 tests, auth 122 (88% coverage, domain 97–100%), platform 26, and `infra/tests` 35 on the running stack, including register → approve → log in → refresh → reset through Nginx into the audit chain. Ruff and mypy are clean everywhere. **Verified 2026-10-18 (W4 close-out):** `mms_common` 102, auth 135 (89%), platform 53 (85%), template 8 + 8, `infra/tests` 43 (including Kafka: anonymous, wrong password, another service's topic or group all refused), Vitest 63, Playwright 10. **Verified 2026-10-18 (W5 backend, local):** operations 84 (95% coverage; domain 92–100%), `mms_common` 105, platform 53, `infra/tests` 44 on the running stack (new: the demo stations scoped by organization through Nginx and `station.created` into the audit chain). **Verified 2026-10-18 on staging:** J1/J2 by hand into the audit chain (`verify()` clean over 36 records), the update prompt between two real releases, and `infra/tests` 44 in CI (new: Mongo comes back after a plain restart).
- **Gotchas (W7):** Every file under `src/` goes into the one `app` chunk (`codeSplitting` in `vite.config.mts`), even behind a dynamic `import()`: a heavy library stays out of it only if the module that imports it is excluded from the `app` group (as `qrCode.ts` is) or the library is imported in the component with `import()` (Leaflet in `MapView.vue`). jsQR is imported only by `qr.worker.ts`. A Python one-liner that writes a file on Windows needs `encoding='utf-8'` (the default is cp1252 and a `§` makes Vite fail with "stream did not contain valid UTF-8"). Leaflet's `L.map` trips `unicorn/no-array-callback-reference`; `leaflet.markercluster` needs `globalThis.L` set before it loads. Playwright's `page.route` does not see requests a service worker makes: the map test blocks service workers.
- **Gotchas (CI, 2026-10-20):** some GitHub runners have a Linux kernel from 6.19 to 7.0.13, and mongod 8 refuses to start there (SERVER-121912; jobs fail at random with "mongo did not start in 90 s"). The test fixture and `compose.dev.yml` set `GLIBC_TUNABLES=glibc.pthread.rseq=1` for Mongo; the fixture also keeps a crashed container and prints its log. Staging (kernel 5.15) is unaffected; if the host's kernel is ever upgraded to 6.19 or newer, apply the same variable to `compose.yml` or wait for kernel 7.0.14.
- **Gotchas (W6):** A script mounted into a container (the SeaweedFS entrypoint) is not part of the container's config, so `compose up` leaves the old container running when only the script changed: the staging deploy now recreates `seaweedfs` when `seaweedfs-entrypoint.sh`'s checksum differs from `/opt/mms/.seaweedfs-entrypoint.sha256` on the host (found on the first W6 deploy, which ran the old volume flags). Do the same for any other mounted script that sets flags. A deploy that fails on `required variable … is missing` stopped before changing anything: add the key to the host's `infra/.env` (as the root alias, keeping the file `mms`-owned, mode 600), then `gh run rerun <id> --failed`. SeaweedFS needs `-volume.max=0` and 256 MB volumes: the default 8 volume slots ran out on the second bucket written to ("No writable volumes"). Do not install `arq`: it pins `redis<6` and pip downgrades the shared Redis client. Jobs run on `mms_common.jobs` and must be safe to repeat. A PC's antivirus can cut a connection that carries the EICAR test string over loopback HTTP, so the EICAR test goes straight to clamd only. `docker run --entrypoint /bin/sh` in Git Bash needs `MSYS_NO_PATHCONV=1`. A new service's `AUTH_SERVICE_SECRETS` entry, Kafka user and `.env` keys (`KAFKA_MEDIA_PASSWORD`, `MEDIA_SERVICE_SECRET`, `MEDIA_SCAN_MODE`) must be on the staging host before its first deploy with media. `stamp()` sets `version: 1`: a collection whose `version` means something else (config versions) overrides it after stamping.
- **Gotchas:** Python's `open(p, "w")` on Windows writes CRLF, which breaks shell scripts mounted into containers; keep `infra/` files LF. In Nginx, a `location ^~ /api/` would hide every regex location (all API routes 404); the catch-all stays a plain prefix. FastAPI 0.143 includes routers lazily, so `app.routes` doesn't list their routes: use `fastapi.routing.iter_route_contexts` (the matrix does). In Git Bash, `docker compose exec <svc> /abs/path` needs `MSYS_NO_PATHCONV=1`. Give `uvicorn[standard]` a lower bound (`>=0.40`): unbounded, pip backtracked through every old uvicorn for over 15 minutes in the image build. An existing local `infra/.env` needs the keys added to `.env.example` since it was copied (`PLATFORM_SERVICE_SECRET`, `AUTH_BREACHED_CHECK`, `AUTH_SEED_PASSWORD`, `KAFKA_AUTH_PASSWORD`, `KAFKA_PLATFORM_PASSWORD`, and since W5 `KAFKA_OPERATIONS_PASSWORD`, `OPS_SERVICE_SECRET`); so does the staging host's (`compose.yml` refuses to start without them). Inside a Mongo transaction a duplicate-key error aborts the transaction even when caught, and the driver then retries it until its 120 s timeout: read first instead of insert-and-catch (W5-6, `upsert_if_newer`). A killed pytest run leaves its `mms-test-*` containers running: `docker ps -a --filter name=mms-test- -q | xargs docker rm -f`. A new service needs a Kafka user: an entry in `infra/kafka/users.yml`, its password in every `.env` and in `kafka-init`'s environment, and `<PREFIX>_KAFKA_USERNAME`/`_PASSWORD` on its container. Service images uninstall pip (its vendored copies fail Trivy). Kafka's admin tools run inside the broker against `127.0.0.1:9094` (the loopback plaintext listener), not `kafka:9092`. A restarted container keeps its `/tmp`, and `fs.protected_regular=2` (Ubuntu and Docker Desktop) stops even root from reopening another user's file in a sticky folder: delete such a file before rewriting it (the Mongo key file took staging down after a host reboot, W4-18). The staging deploy tries `compose up` five times, 30 s apart, before failing (a store still restarting after a reboot); if it still fails, it prints `compose ps -a` and the service's logs: fix the cause and rerun the failed job (`gh run rerun <id> --failed`). The app version comes from `frontend/package.json` (`__APP_VERSION__`); bump it for a release, never stamp a commit SHA into the bundle (every deploy would prompt every phone to reload). To replay audit dead letters after a fix: stop platform, reset the `audit` group to earliest (`kafka-consumer-groups.sh --reset-offsets --to-earliest --group audit --all-topics --execute`), start it again.

- **Repository:** GitHub `tajay59/MARS-MMS`, branch `main` (remote `origin`). Text files are LF (`.gitattributes`, `.editorconfig`); keep it that way, because shell scripts and configs run in Linux containers.
- **CI:** [.github/workflows/frontend.yml](.github/workflows/frontend.yml) runs lint, Vitest, the API type drift check, type-check and build (job `check`, `ubuntu-24.04`) on pushes to `main` that touch `frontend/` and on **every** pull request, so `check` can be a required status. [.github/workflows/backend.yml](.github/workflows/backend.yml) does the same for the back end: `mms_common` (Ruff, mypy, tests with throwaway containers), one job per service (`auth`, `operations`, `platform`: Ruff, mypy, tests, coverage ≥ 70%), `service template` (generates both variants and runs their checks unchanged), `nginx -t`, and `compose stack` (builds and starts the stack, waits for auth, operations and platform to be healthy, runs `infra/tests`, then the Playwright journeys). The auth and operations jobs also check `frontend/openapi/<service>.json` matches the service. Both run on every pull request and are called by [release.yml](.github/workflows/release.yml) on pushes to `main`: checks → [images.yml](.github/workflows/images.yml) (`auth`, `operations`, `platform`, `web`; Trivy; pushed to GHCR `ghcr.io/tajay59/mars-mms/<image>:<sha>`) → staging deploy over SSH with [infra/compose.prod.yml](infra/compose.prod.yml) → Playwright `@smoke`. The deploy job is skipped until the repository variables `STAGING_HOST`, `STAGING_USER`, `STAGING_URL` and secrets `STAGING_SSH_KEY`, `STAGING_KNOWN_HOSTS` exist; host preparation is in the docs site, Infrastructure › Staging.
- **Staging host (decision W4-8, 2026-10-17):** `https://rnd.yanacreations.com`, files host `files.yanacreations.com` (CNAME), on a **shared** server `84.247.187.64` (Ubuntu 22.04, 6 GB RAM, about 2 GB free; also runs PrintIT and Kreativ Wrist; root SSH alias `kw-server`). Its edge Nginx `printit-nginx` owns 80/443 and the Let's Encrypt certificates (`/srv/edge-sites/*.conf`; ours is `mms-staging.conf` from [infra/nginx/staging-edge.conf](infra/nginx/staging-edge.conf)) and proxies to our Nginx as `mms-gateway` on `kong-net`. [infra/compose.staging.yml](infra/compose.staging.yml) adds that network, `snippets/real-ip.conf` and the memory caps. Deploy user `mms`; `/opt/mms/{infra,secrets,tls}`; the host's `infra/.env` has fresh secrets. The repository variables and secrets are set. Changes to the edge or certbot affect the other sites: ask first. Snap's certbot there runs `/etc/letsencrypt/renewal-hooks/` (which stop and start printit-nginx) even for `certonly`: issue new certificates with `--webroot -w /srv/edge-sites/acme --no-directory-hooks`, then set the renewal to `standalone` like the others. Compose override tags: `!reset` empties a value, `!override` replaces it.
- **GitHub tracking:** project board [AWS-MMS](https://github.com/users/tajay59/projects/2) (linked to the repo), milestones P0–P8 (one per IP phase); Phase 0 work is issues #1–#10. New issues get a milestone and are added to the board. **`main` is protected** (the repo is public since 2026-10-16): no direct pushes, even for admins. Work on a branch, open a pull request, and merge by squash or rebase once the checks are green and the branch is up to date. Secret scanning blocks pushes that contain secrets. **The repo is public:** never commit client names, real station data, credentials or internal addresses; keep those in the organization's systems or in uncommitted `.env` files.
- **SeaweedFS spike:** [infra/spikes/seaweedfs/](infra/spikes/seaweedfs/) (throwaway, Phase 0). Not part of the app stack. **Passed 2026-10-16** on SeaweedFS 4.48 (T7 confirmed); Chrome, Firefox 158 and a 152.8 MiB video from an Android phone all passed the same day. All checks done; an iPhone run is optional.
- **Tools installed:** Docker Desktop 29.8.2 (Compose v5.6.0) and draw.io desktop 32.4.1. Docker's CLI is at `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin`; terminals opened before the install don't have it on PATH.
- **Information requested from the organization:** [Claude Doc](https://claude.ai/code/artifact/245278ff-5250-48fb-859d-6bcdba80d911) listing every open input (T, B, P, Q, V items) with owner, due week and default.
- **Developer docs site:** [docs/index.html](docs/index.html), the interactive reference for how the app is wired. **It must be updated every phase** (see "Developer documentation site" below).

When code is added, follow the rules below and update this file.

## Developer documentation site (required)

[docs/index.html](docs/index.html) is the living, interactive reference that lets any future developer see how AWS-MMS is wired: architecture, services and routes, gateway, data and schemas, events, each feature's flows, frontend, security, configuration, infrastructure, CI/CD, decisions, a diagram guide and a changelog. The planning documents say what to build; this site describes what was built.

**Requirement: every phase updates it, and a phase is not done until it has** (it is in the definition of done below). Also update it in any change that alters how the system is wired. Each phase:

1. Update "Build status", the section badges (`badge built` / `progress` / `planned`) and the sidebar dots (`dot built` / `dot progress`).
2. Replace designed shapes with built ones: schemas from the Pydantic models, routes from OpenAPI, events from `mms_common.events`, settings with their real env var names, file and folder tables.
3. Add the diagrams chosen for the phase (see "Charts" below) and update any diagram the phase changed.
4. Record new decisions in the "Decisions" section and in the source document.
5. Add a "Changelog" entry.
6. Open the page in a browser in light and dark and check that no diagram shows "could not be drawn". If the code and the TRD disagree, fix one of them in the same change.

**Constraints:** the page opens straight from disk (`file://`) with **no server, no build step and no network**. Mermaid is vendored and pinned (`docs/assets/vendor/mermaid-11.17.2.min.js`), and the fonts are copied into `docs/assets/fonts/`. Content lives in `index.html` (one `section.doc` per sidebar entry; `.sub[id]` blocks are what search finds); behaviour lives in `docs/assets/docs.js`, styles (brand tokens, light and dark) in `docs/assets/docs.css`. The site is developer tooling, not an app screen, so the UI-skills workflow doesn't apply to it; it still uses the DBD tokens and fonts. The "Maintaining these docs" section in the page has copy-paste snippets.

### Diagrams

- **Mermaid is the default.** Write the source inside `<pre class="mermaid-def">` in a `figure.diagram` with `data-title` (the answer, in a few words) and `data-kind` (a chart type from the catalogue below). Escape `<` as `&lt;` and `&` as `&amp;`. Don't put `;` in sequence messages, or raw `<host>`-style text in labels (it's read as HTML).
- **draw.io** for hand-laid diagrams: true swimlanes, deployment pictures, anything for clients or training. Save as `docs/diagrams/<name>.drawio.svg` (an SVG with the editable diagram inside; GitHub shows it as an image). Edit it in draw.io desktop, app.diagrams.net or VS Code's Draw.io Integration (`hediet.vscode-drawio`). Show it in the site as an `<img>` view; when a Mermaid and a draw.io version of one flow both exist, they are tabs on one figure and must match.
- Use names exactly as in the code and specs. One question per diagram. Brand colours only; status colours only for statuses.

### Charts: suggest them every phase

**At the start of each phase, propose which charts to add to the site** from this catalogue (the 17 types in Figma's [types of flow charts](https://www.figma.com/resource-library/types-of-flow-charts/), plus the UML and data diagrams below). The user picks; the chosen charts are added before the phase closes. The full catalogue with status, and the per-phase suggestions, are in the site's "Diagram guide".

| Chart type | Use it in AWS-MMS for |
|---|---|
| Process flow diagram | One actor's steps and decisions: field visit (J6), CI pipeline, station import |
| Workflow diagram | Staff routines outside the app's flow: hypercare triage, calibration follow-up, release routine |
| Data flow diagram | Event wiring, where secrets and tokens live, notification fan-out, backups |
| Swimlane flowchart | Hand-offs between roles and services: J1 registration, J4 approve and assign, J8 client review (draw.io for true lanes) |
| Decision tree diagram | Rules with many branches: `derive_status`, sync conflicts, client document access |
| System flowchart | Inputs processed by the system: gateway routing, media pipeline, report rendering |
| Document flowchart | Documents that collect signatures: visit report → final → client sign-off; client report form → PDF |
| Product flowchart | Sensor inventory: stock → installed → repair or lab calibration → stock or retired |
| PERT chart | IP phases, dependencies and decision deadlines (Mermaid gantt) |
| Use case flowchart | Roles × actions per service (mirrors the authorization matrix) |
| Event storming flowchart | Commands → domain events → consumers and read models per module |
| Customer journey flowchart | The client's path: invited → first request → follow progress → sign off |
| Production flowchart | Not used (covered by the request swimlane and lifecycle) |
| Logical model flowchart | Summary reports and dashboards: read-model inputs → aggregation → PDF/CSV |
| Code flowchart | Branch-by-branch logic worth a test each: `/login`, `/refresh`, sensor action apply/reverse, sync op apply, finalize retry |
| E-commerce flowchart | Not used (no sales flow) |
| Website flowchart | Pages, shells, route guards and redirects |
| *Beyond Figma:* sequence, state, ER, architecture (C4), gantt | Calls over time; every status field; collections; containers; schedules |

Suggested per phase (adjust to what was built): **P1** J1 swimlane (draw.io), credentials data flow, `/login` and `/refresh` code flowcharts, auth use cases, auth event storming, outbox leader handover sequence, shells and guards website flowchart, local stack architecture. **P2** sensor inventory product flowchart, sensor unit state, document upload and model-document download sequence, station import process flow. **P3** request state (as built), `derive_status` decision tree, J4 swimlane, WebSocket fan-out sequence, request event storming. **P4** visit state, visit-end transaction sequence, sensor action code flowchart, media pipeline system flowchart, media state. **P5** prepare-for-field sequence, offline op state, conflict decision tree, device storage data flow. **P6** visit report document flowchart, finalize saga (as built), client review customer journey, reminders and auto-close state. **P7** summary reports logical model, backup and restore data flow, monitoring system flowchart, production architecture. **P8** hypercare workflow, client onboarding customer journey, go-live gantt.

## Orientation: read this instead of exploring (saves tokens)

**Resume point (2026-10-20, branch `feat/p2-w7-qr-map-labels`, not pushed or committed yet).** W6 and its forms are on `main` (#36, #39). **W7 is built, back end and screens** (the "AWS-MMS W7 screens" mock-up was approved): operations' QR routes (`GET /api/v1/qr/{token}`, 410 for a replaced token, `POST /api/v1/stations/{id}/qr/regenerate`, `qr_revoked`, `qr.regenerated`), `POST /internal/labels`, the **report service** (`services/report`: label sheets with WeasyPrint, `report` and `report-worker` in compose, images, CI and the release health loop), and the frontend: `/scan` (`features/scan/`: own camera loop, `BarcodeDetector` or jsQR in `qr.worker.ts`; **not** `qr-scanner`, finding F16: its worker is a `blob:` URL and the CSP says `worker-src 'self'`), `/s/:token` (open to clients too), `/map` (`features/map/`: Leaflet and markercluster loaded with `import()`; the service worker keeps viewed OSM tiles in `mms-tiles`, emptied at logout), `/admin/stations-tools` (label tool, polls the job), the QR card on the station Overview (`StationQrCard.vue`, `qrCode.ts` lazy), `stores/stationDirectory.ts` (every station in memory for the map, the code field and the label picker) and `PageBody`'s new `bleed` prop. Decisions W7-1 to W7-8 are in the docs site and the TRD 2.9 row; the docs site has the W7 status, pages, tiles row, settings, changelog and two charts (scanned-label flow, label sheet sequence). **Verified locally 2026-10-20:** Vitest 267, Playwright (`e2e/labels.spec.ts`: label replace and 410, client scope, signed-out `next`, typed code, map, label sheet through the report worker, phone viewport; axe light and dark), ESLint, vue-tsc, production build (precache 27 files, 1.8 MB: the extra files are the worker, `qrCode`, `leaflet`, `leaflet.markercluster` and two CSS files), operations 144, report 59, `mms_common` 114, `infra/tests` 46. **Next:** (1) commit, push and open the pull request (nothing of W7 is committed); (2) **before the first deploy with report, add `KAFKA_REPORT_PASSWORD` and `REPORT_SERVICE_SECRET` to the staging host's `infra/.env`** (and set `REPORT_APP_URL` to `https://rnd.yanacreations.com`: a label holds that address; the others, `REPORT_DB_PASSWORD` and `REPORT_S3_*`, are there already), then rerun the failed deploy if it stopped; (3) the iPhone checks (Phase 1 install, F15 for W6) and W7's exit check: a printed label scanned by an iPhone camera app, an Android camera app and the in-app scanner on both (the camera loop, torch and the installed app's permission prompt are only proven on real phones); (4) F1 stays open: before production pick a tile provider that allows offline use (T1).

**Sensors page (W6-12, 2026-10-20, not committed yet):** redesigned from mock-ups. Model photos are documents of type `photo` (scope `model`; first = cover); `SensorModelOut` carries `specs`, `unit_counts`, `photo_count`, `cover_document_id`; `features/sensors/` has `ModelRow`, `ModelGallery`, `ModelSpecs`, `ModelUnits`, `ModelPhoto` (links via `photoLinks.ts`, memory only), `PhotoStager`, `SpecsField`. The mock-ups' offline queue was not built (OFF-10). Verified locally: operations sensor and document tests 36, Vitest 215, Playwright documents, stations and shell journeys 14 (chromium and phone), lint and type-check clean.

**Where things live (operations; media follows the same layers).** Route: `app/api/stations/<x>_routes.py` + `schemas.py`/`doc_schemas.py`; rules with no I/O: `app/domain/stations/`; Mongo and HTTP clients: `app/repo/stations/` (`media_client.py` is operations' view of media); events: schema in `libs/mms_common/mms_common/events/<service>.py` with `@register`, send through `Emitter` in `app/events/publish.py` inside `ctx.tx(...)`; consumers: `app/events/consumer.py` composes `org_consumer` and `media_consumer`; indexes: a new `app/migrations/NNNN_*.py`. Every new route goes in `tests/api/test_authorization_matrix.py` (`TABLE`, path params use the real names such as `{media_id}`); the audit consumer records every event type by default (`AUD1` in `services/platform/app/domain/audit.py`). After an API change: `.venv/Scripts/python infra/scripts/export_openapi.py`, then `npm run api:types` in `frontend/` (CI fails on drift). A **new service** needs: the copier template, a Kafka user in `infra/kafka/users.yml` and its password in every `.env` and in `kafka-init`, an entry in `AUTH_SERVICE_SECRETS`, compose services plus `compose.prod.yml` and `compose.staging.yml` overrides, `images.yml` and `backend.yml` matrices, the `release.yml` health loop, `infra/scripts/export_openapi.py`, and its tests in `infra/tests`. Frontend: pages in `features/<area>/`, API clients in `src/api/*.ts` (types from `src/api/types`, aliases in `models.ts`), device-made IDs from `app/ids.ts` (`newId()`), upload code in `src/offline/` (no Vue imports there).

**Test helpers.** `mms_common.testing.containers` gives `mongo_uri`, `redis_url`, `kafka_bootstrap`, `seaweedfs` (real S3) and `clamd` (real ClamAV, about a minute to start) as session fixtures, skipped without Docker. `ManualClock.advance(minutes=16)` takes keyword arguments. Seed users: `tech1`, `tech2`, `admin`, `viewer`, `client_a1`, `client_b1`, `disabled` (`TestIssuer.token(name)`, `.service_token(name)`). Fakes live in each service's `tests/conftest.py` (`FakeMedia`, `FakeOwners`, `FakeJobs`, `FakeScanner`). Tests that build an app with a lifespan must use the app's own `app.state.mongo`/`app.state.db` for sessions, not a second client.

**Running things on this PC (Windows, Git Bash).** Docker is not on PATH: `export PATH="$PATH:$LOCALAPPDATA/Programs/DockerDesktop/resources/bin"`, and `export MSYS_NO_PATHCONV=1` for `docker run --entrypoint /bin/sh`. Run each service's tests from its own folder (`cd services/media && ../../.venv/Scripts/python -m pytest -q`): every service's package is called `app`, so a script that imports one needs `PYTHONPATH=.` and that folder as the working directory. Rough durations: `mms_common` 30 s, platform 40 s, operations 75 s, auth 2 min, media 2 min (ClamAV adds a minute), `infra/tests` 90 s (the stack must be up: `docker compose -f compose.yml -f compose.dev.yml up -d --build` in `infra/`, then `restart seaweedfs`-style changes need `up -d --force-recreate <svc>`), Vitest 6 s, ESLint 1 min. ESLint here is strict: `npm run lint:fix` first, then fix by hand (one statement per line, `toSorted`, `addEventListener` not `onload`, catch parameter names, class member order); `tsconfig.app.json` targets ES2023 libs. In this tool a Bash heredoc breaks on an apostrophe in its text: write files with the Write tool, and for several edits write a small script to the scratchpad and run it. Editing `docs/index.html` or `TRD.md` by script is cheaper than reading them: find the anchor with `grep -n`, then replace (docs-site ids: `#services` route table, `#media`, `#decisions`, `#config`, `#status`, `#changelog`; TRD sections §3.2 operations, §3.3 media, §9 jobs, §10 storage, R6 risks). Do not read either file in full.

**Verified 2026-10-19 (W6, local):** media 116 (88%), operations 136 (95%), auth 143, platform 53, `mms_common` 114, Vitest 180, Playwright 18 on Chromium (`e2e/documents.spec.ts` new: upload, share, client download, configuration versions, sensors, calibration due; axe light and dark) and 1 phone journey, `infra/tests` 45 (new: a 10 MiB PDF through Nginx and the files host into the audit chain). Ruff, mypy, ESLint, vue-tsc and the production build are clean. CI has not run on this branch. The Playwright `chromium` project now skips `@phone` tests (they run in the `phone` project).

## Planning documents

Read these before writing a new document or any code. Requirement IDs (AUTH-1, REQ-2, VIS-7, …) belong to the PRD. Service, container and route names belong to the TRD. Journey IDs J1–J10 and page routes belong to the AFD.

| File | Document | Version | Live copy (Claude Doc) |
|---|---|---|---|
| [docs/PRD.md](docs/PRD.md) | Product Requirements | 1.3 | — |
| [docs/TRD.md](docs/TRD.md) | Technical Requirements | 2.7 | — |
| [docs/AFD.md](docs/AFD.md) | App Flow (journeys J1–J10, routes, menus, edge states) | 1.5 | [link](https://claude.ai/code/artifact/51ce0c78-20c6-4218-b22b-4f69ee6024d1) (1.0, stale) |
| [docs/DBD.md](docs/DBD.md) | Design Brief (colour, type, shells, components) | 1.6 | [link](https://claude.ai/code/artifact/b14d2c1e-0106-470a-bd5a-ffc28c4eea37) (1.1, stale) |
| [docs/BSD.md](docs/BSD.md) | Background Schema (data location, schemas, access, retention) | 1.5 | [link](https://claude.ai/code/artifact/bfd6c029-c1d7-4fc0-a6fe-b75502654c02) (1.0, stale) |
| [docs/IP.md](docs/IP.md) | Implementation Plan (phases 0–8, 25 weeks) | 1.1 draft | [link](https://claude.ai/code/artifact/de63972b-b743-4ad1-b5fa-85325dc22312) (1.0, stale) |
| [docs/TP.md](docs/TP.md) | Test Plan (levels, rule-enforcement tests, seed users, CI stages, tests by phase) | 1.2 draft | [link](https://claude.ai/code/artifact/d6d1344c-a8be-466d-931c-2b8c8f5ec225) (1.0, stale) |

- The App Flow file is `docs/AFD.md`. Some older notes call it "APD"; it is the same document.
- [docs/drafts/](docs/drafts/) holds the earlier drafts (Claude, DeepSeek, GPT) and the original `Specification.txt`. The final documents supersede them. Don't edit them, and don't treat them as a source of truth.
- **The local files are the source of truth.** Since 2026-10-16 the Claude Doc live copies are stale: each carries a note pointing to the local file. Update only `docs/*.md` unless the user asks for the live copies to be brought back in step.
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
  - A single MongoDB 8 replica set (`rs0`) with **one database and one DB user per service** (`platform` has two).
  - Files go to SeaweedFS (S3 API) through presigned direct uploads.
  - Kafka 4.x (KRaft) carries domain events between services.
  - Redis 7.4 holds jobs (arq), cache, leader leases, the login throttle and WebSocket pub/sub.
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
- Staff and clients use the **app shell** (DBD "The shells"): rail · interactive pane · view, as square tiles on `ground`. A page fills the view with `PageBody` (title, subtitle, `#actions`, `back` for phones) and puts its list or controls in the pane with `<PaneContent>`; a record it opens goes in the URL and is reported with `usePaneSelection()`. No bordered cards inside tiles. Rail tooltips are CSS (`RailTip`): Vuetify's `VTooltip` leaves empty `role="tooltip"` nodes that fail axe. The field shell (phone: stepper Before → Work → After → Review, bottom nav, sync badge) is unchanged. Public pages, including `/unlock`, use the split panel.
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

- Demo stations (after auth's seed): `docker compose -f compose.yml -f compose.dev.yml exec operations python -m app.cli seed` (five made-up stations for organizations A and B, with sensors). A station export: copy it in (`docker compose cp stations.xlsx operations:/tmp/`), then `exec operations python -m app.cli import-stations /tmp/stations.xlsx` (a dry run; add `--commit`). Never commit a real export: the repo is public. The existing system's exports (W5-8): `exec auth python -m app.cli import-orgs /tmp/org.json`, then `exec operations python -m app.cli import-stations /tmp/site.json` (each a dry run; add `--commit`). Its `entities` documents hold MQTT usernames and passwords (`web`, `device`): ask for the export without them (it may come with them anyway: keep only `id`, `name`, `organization` and `code` before copying it anywhere), never put them in the repo, a fixture or a log, and delete the files from the containers afterwards (`exec -u root auth rm -f /tmp/org.json`: `docker compose cp` leaves them owned by root, so the service user can't).
- Seed users (TP): `admin@example.org`, `tech1@example.org`, `client.a1@example.org`, `viewer@example.org` and the rest of `mms_common.testing.seed.SEED_USERS`, all with `AUTH_SEED_PASSWORD`. On staging and production, create the first admin with `python -m app.cli create-admin --email … --name …` (password from `AUTH_ADMIN_PASSWORD` or a prompt); `seed` refuses production.

- App: `https://mms.localhost` (accept the self-signed certificate once). Files host: `https://files.mms.localhost`. Mailpit: `http://127.0.0.1:8025`.
- Published on 127.0.0.1 only, for debugging: MongoDB on `MONGO_DEV_PORT` (default **27018**, because a locally installed MongoDB often holds 27017; connect with `directConnection=true`), Redis 6379, SeaweedFS S3 8333.
- To check the gateway config alone: `docker compose -f compose.yml -f compose.dev.yml exec nginx nginx -t`.

Not yet available. Add these as they are built (IP Phase 1):

- hot reload in the local stack (seed users exist through `python -m app.cli seed` in auth; stations and requests come with their services)
- rebuild a read model (`infra/scripts/backfill.py --consumer <service>`)

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
