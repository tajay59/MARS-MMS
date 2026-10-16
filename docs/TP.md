# Test Plan
## AWS-MMS — Automatic Weather Station Maintenance Management System

| | |
|---|---|
| **Version** | 1.1 (draft) |
| **Date** | 2026-10-16 |
| **Status** | Draft for review |
| **Changes in 1.1** | Follows TRD 2.0 and IP 1.1: five services, Nginx gateway, SeaweedFS, weeks shifted to a W25 go-live. Offline merge tests replaced by station-owner and conflict-code tests. New tests for request status derivation, sensor-action reversal, the finalize saga, fail-closed file visibility, the offline PIN session, refresh-token races, the outbox leader lease, read-model backfill, service-worker cache clearing, the CSP tile host and multipart clean-up |
| **Builds on** | [PRD.md](PRD.md) 1.1, [TRD.md](TRD.md) 2.0 (§7, §15, §17, §18), [AFD.md](AFD.md) 1.1 (J1–J10), [DBD.md](DBD.md) 1.2, [BSD.md](BSD.md) 1.1, [IP.md](IP.md) 1.1 draft |
| **Replaces** | TRD §17 Testing strategy, which is now a summary that points here |
| **Open-question prefix** | V |
| **Live copy** | [Claude Doc](https://claude.ai/code/artifact/d6d1344c-a8be-466d-931c-2b8c8f5ec225) (1.0; superseded by this file) |

AWS-MMS is tested so that the rules generated code is most likely to break are checked by machine on every pull request. Those rules are org scoping, viewers never mutating, the outbox, and offline sync with zero loss. The levels in TRD §17 stay. This plan adds the tests that enforce the architecture rules and the tests for the riskiest areas. It also builds each test in the phase that first needs it, so testing doesn't pile up at the end of the 25 weeks.

---

## Purpose and scope

This plan sets what is tested, with which tools, when each test runs, and which phase builds it. It covers the v1 scope in PRD §3: all five services, the workers, the Nginx edge and gateway, the PWA in its three shells, PDFs, emails, backups and the production stack.

Compared with TRD §17, it adds:

- tests that enforce the 12 rules in `CLAUDE.md`, the ones most at risk because most code is generated
- fault and property tests for the event backbone and offline sync
- an injectable clock for every time-based rule
- visual regression for PDFs and the three shells
- automated security and restore checks that run continuously, not only in W20
- a shared set of seed users and fixtures, so the E2E tests, the authorization matrix and staging demos use the same data

**Out of scope:** penetration testing by a third party (an open question, V3), the later integration service, and routine maintenance features.

## Test levels

Nine levels run, from per-PR unit tests to a hands-on field test, and the cheap ones run most often.

| Level | Tooling | Scope | Runs |
|---|---|---|---|
| Unit | pytest, Hypothesis | `domain/`: request status derivation, visit end and owner rules, sensor reconciliation, report lifecycle and finalize saga, signature invalidation, audit hash chain, permissions | Every PR |
| API | pytest + httpx `AsyncClient` + testcontainers (Mongo, Redis, Kafka) | Each endpoint, org scoping, 404 for out-of-scope records, role checks, the authorization matrix | Every PR, changed services |
| Contract | pytest | Consumer fixtures against `mms_common.events`; every AUD-1 action maps to an event; snapshot endpoint shapes | Every PR; all services when `mms_common` changes |
| Integration | pytest against the Compose stack | Event flows end to end, outbox leader failover and consumer faults, backfill, migrations, clock-driven jobs | On `main` and nightly |
| Frontend unit | Vitest + Vue Test Utils + MSW (mocks typed from OpenAPI) | Stores, Dexie outbox, sync worker, PIN session, refresh lock, signature component, theme switch | Every PR |
| End-to-end | Playwright against the Compose stack | Journeys J1–J10 including offline (`context.setOffline(true)`), axe, CSP violations | Smoke on every deploy; full suite nightly |
| Visual regression | Playwright `toHaveScreenshot`; PDF pages rendered to PNG | The three shells in light and dark; visit, close-out, label and summary PDFs | Nightly; reviewed when a baseline changes |
| Field test | Real iPhone and Android phone | A full visit with no signal, a restart and PIN unlock mid-visit, sync on return, sign next day | W15, Phase 8 pilot, any release touching `frontend/src/offline/` or `sw/` |
| Load and soak | Locust | 50 concurrent users, 20 simultaneous video uploads, 1-hour soak | W20, before go-live |

Coverage targets stay at 90% for `domain/` and 70% overall. Mutation testing (`mutmut`) runs weekly on the request state machine, the status derivation, the sensor reconciliation and the report lifecycle, to check that their tests catch changed rules.

## Rule-enforcement tests

Each of the 12 non-negotiable rules in `CLAUDE.md` has a test that fails the build when the rule is broken. Code review alone doesn't catch these breaks reliably when most code is generated.

| Test | Rules | How it works | Level |
|---|---|---|---|
| Authorization matrix | 3, 4, 5 | One parametrized test per service reads its OpenAPI and calls every route as each seed user. Expected: anonymous → 401; viewer on a mutating route → 403; client of another organization → 404 on every resource route; a technician editing a station they don't own → 403; a route missing from the expected-roles table (taken from the PRD §2.3 permission matrix) fails the test. New routes can't skip it. | API |
| Client leak test | 6, D4 | Every response returned to a client token is checked against a deny list: staff `email` and `phone`, internal comments, draft reports, staff-only documents, config versions. Staff appear only as `{id, name}`. | API |
| Domain imports | 7 | `import-linter` contract: `app.domain` may not import `fastapi`, `pymongo`, `aiokafka` or `app.repo`. | Every PR (lint) |
| No direct produce | 2 | A Ruff custom rule or grep check: Kafka producer calls only inside `mms_common.outbox`. A state change without an outbox row in the same transaction fails an API test that inspects the outbox collection. | Lint + API |
| Database isolation | 1 | With each service's own Mongo credentials (six databases, platform holding two users), reading any other database is refused. | Integration |
| Repo-layer scoping | 3 | A unit test asserts that every public `repo/` read for a client merges `org_id` (or `owner_org_id` / `current_org_id`), using a fake collection that records the filter. | Unit |
| Injection | 12 | Every filter and search endpoint gets bodies and query strings containing `{"$ne": null}`, `{"$where": "1"}`, `{"$gt": ""}` and dotted keys. Expected: a validation error, never a widened result. | API |
| Audit insert-only and chain | 10 | The audit Mongo role has no `update` or `remove` on `audit_events`, yet migrations can create indexes. Editing one stored record directly makes the integrity check report that record. | Integration |
| Finalized reports immutable | 11 | Any write to a finalized version is rejected (409, V1); reopening creates version n+1 and invalidates the earlier signatures. | Unit + API |
| UTC storage | 8 | A Hypothesis test round-trips times through each service's models: stored values are UTC; display helpers use the station's IANA zone. | Unit |
| Client-generated IDs and `op_id` | 9 | Replaying any create with the same UUIDv7 or `op_id` returns the first result and creates nothing new. | API |

## Risk-area tests

Ten areas get dedicated tests beyond the TRD's levels, ordered by the cost of a failure in production.

### Offline sync and the field session (NFR-4, OFF-1 to OFF-11, AUTH-12)

- **Properties (Hypothesis, unit and API):** applying any `/sync` batch twice gives the same state as once; a failed op stops later ops for that visit only; every conflict leaves the device copy in place.
- **Owner rules:** a non-owner's `work.save`, `station.arrive` and `station.depart` return `conflict: not_owner`; any attending staff's `media.attach` applies; an owner change while offline produces `not_owner` for the old owner's queued work, with nothing overwritten on the server.
- **Conflict codes:** each row in TRD §7.4 has a test: `stale_version`, `locked`, `visit_cancelled` (then admin restore and re-sync applies the ops), station removed while offline (applied and re-added), `already_ended`, and a duplicate start.
- **Fault injection:** the connection drops mid-part in a multipart upload, then resumes from `parts_done[]`; drops between media upload and `/sync`; the access token expires during sync; storage quota is exceeded; the tab is killed during a Dexie write (Vitest with `fake-indexeddb`, then Playwright).
- **PIN session (Vitest + Playwright):** setting a PIN stores only a PBKDF2 verifier; a correct PIN unlocks the cached profile after a reload with the network off; five wrong PINs disable unlock but keep queued data; logout removes the profile and bundles but keeps queued ops for the same user; another user logging in on the device can't see or sync them.
- **Playwright offline:** with the real service worker, `setOffline(true)` through a whole J6 visit, reload while offline and unlock with the PIN, go online, check every record and file on the server. Run in Chromium and WebKit; WebKit only approximates iOS Safari.
- **Real devices:** the field test exit criterion from IP Phase 5, plus the W13 iOS check (50 photos and 3 videos survive a phone restart and PIN unlock).

### Request status and visits (ADR-17, PRD §5.1)

- **Derivation properties (Hypothesis):** for any set of visits (planned, started, ended, cancelled) and report statuses, `derive_status` matches the five rules in PRD §5.1. It is idempotent, and the order in which visits change doesn't affect the result.
- **Examples:** two parallel visits where one ends needing another visit while the other is still planned (Scheduled, never stuck); a report reopened during Client Review (In progress, reminders cleared, auto-close stopped); a report reopened after Closed (stays Closed, close-out regenerated); a rejection followed by a report-only correction (Assigned → In progress → Client Review); admin cancel from Client Review cancels planned visits and keeps a started visit's work.
- **Events out of order:** `report.finalized` delivered before, after or twice around a `visit.ended` always gives the same final status.

### Sensor inventory corrections (SEN-3, SEN-4, TRD §3.2.3)

- Applying the same sensor actions twice changes nothing.
- Changing a serial after the visit ends reverses the old installation and calibration and applies the new one, all in one transaction, with `sensor.application_reversed` audited.
- Removing an action reverses it; reopening a report and correcting the work record does the same.
- Reversal is refused with `409 sensor_changed_later` when a later visit or manual change touched the same unit or station parameter.
- Unknown serials are created once per action and flagged.

### Event backbone (ADR-3, ADR-13, TRD §8)

- Kafka stopped: state changes still succeed, outbox rows wait, and they publish in order when Kafka returns. The "oldest unpublished outbox row" alert fires after 5 minutes.
- **Leader lease:** two workers and two containers of one service run, and only the lease holder publishes. Killing the leader hands over within 10 s, with no duplicates out of order and no gaps.
- The same event delivered twice: each consumer applies it once (`processed_events` in the handler's transaction; a crash between write and commit is simulated).
- Out-of-order events: read models keep the newest `aggregate_version`.
- A malformed event goes to `mms.dlq.<service>` and the DLQ alert fires.
- **Backfill:** `backfill.py` builds each read model from snapshots to match one built from live events, including while events keep arriving. The report service deployed weeks after the data was entered gets a complete read model.
- Two instances of one service start together: the `_migrations` lock lets only one run migrations.

### Reports and PDFs (RPT-1 to RPT-10)

- **Finalize saga:** render fails three times → report back to Draft, visit unlocked, signatures kept, `report.finalize_failed` emitted; a worker killed mid-saga leaves `finalizing`, and the cron resumes it to Final; facts changed between lock and render → back to Draft with signatures cleared.
- **Signatures:** a facts refresh from a corrected work record clears signatures, as an edited narrative does.
- **Visual regression:** each PDF template (visit report, close-out, client report form, label sheet, summary with ApexCharts) is rendered from fixed fixtures and compared page by page with approved PNG baselines.
- A draft is generated within 10 minutes of sync and a summary within 2 minutes (NFR-2), measured in the integration stack.
- Report times show in the station's time zone.
- **Verify (RPT-11):** the public endpoint returns only number, version, status and date, and is rate-limited at 10/min per IP.

### Time-based rules

Every service reads time from an injectable clock in `mms_common.time`, overridden in tests. Integration tests cover:

- client-review reminders on days 7, 21 and 28
- auto-close and its close-out report on day 30, and the restart of the 30 days after a report reopen
- finalize reminders and the stuck-finalize resume
- the AUTH-5 purge
- deleting original media after 30 days (NFR-8) and aborting multipart uploads after 48 hours
- the 30-day field session (AUTH-12)
- the weekly calibration digest

Display tests cover stations in several IANA zones across a DST change.

### Media pipeline and visibility (MED-1 to MED-7, NFR-7, ADR-19)

- A fixture set of real files: iPhone HEIC photos and HEVC `.mov` video, Android JPEG and MP4, a photo with GPS EXIF, the EICAR test file, a PDF renamed `.jpg`, and a file over the size limit. Tests check that:
  - processed images carry no GPS or personal EXIF
  - EICAR is rejected
  - the magic-byte mismatch is rejected
  - a 2-minute video plays in Chrome and iOS Safari after processing
- **Fail-closed visibility:** a new upload is invisible to the client until its owner emits `media.visibility_requested`. An attachment on an internal comment is never visible to a client, even when listed by `owner_ref`. Making a comment internal hides its attachments again. An older `visibility_version` never overrides a newer one.
- **Model documents:** a client gets a model manual through `/documents/{id}/download` only while that model is installed at one of their stations, and gets 404 from media directly.
- **Multipart:** 8 MiB parts complete on SeaweedFS; the browser reads `ETag` through CORS; `abort_stale_uploads` removes abandoned uploads.

### Frontend quality

- Every route in J1–J10, plus `/unlock`, runs an `@axe-core/playwright` check in light and dark (WCAG 2.2 AA, NFR-11).
- Playwright fails the test on any console CSP violation, so a stray inline script or font from a CDN is caught. Map tiles from `tile.openstreetmap.org` load in the page and through the service worker.
- Screenshots of the client, staff and field shells in both themes at 390, 768 and 1280 px.
- Browser projects: Chromium, Firefox and WebKit, with Pixel 7 and iPhone 15 emulation (NFR-5).
- Viewers see no action buttons: a Playwright test per page checks that buttons are absent, not disabled.
- **Shared device:** after logout and a login as a different user, no API response or bundle of the first user is served (service worker caches no API responses).
- **Refresh race:** two tabs and the service worker refresh at the same moment; the user stays logged in and the refresh family isn't revoked. A real reuse after the 30-second grace still revokes it.
- OpenAPI drift: CI regenerates the `openapi-typescript` types and fails on `git diff --exit-code`.

### Security (NFR-6, TRD §15)

- JWT tests at each service, because Nginx doesn't verify tokens: wrong key, `alg: none`, `alg` confusion, expired token, refresh token used as an access token, a token for a disabled user.
- `/internal/*` and `/.well-known/*` return 404 through Nginx and require a service token (or the internal network) inside.
- Login throttling: the same message and similar timing for registered and unregistered emails after 5 failures (AUTH-10).
- Security headers, HSTS, CSP, rate limits (including the office allowlist) checked on staging after each deploy.
- OWASP ZAP baseline scan of staging nightly; `pip-audit`, `npm audit` and Trivy on every PR; the ASVS L2 review in W20.

### Operations (NFR-3, NFR-9)

- A weekly job restores the latest production backup into staging and runs the audit integrity check. The first run is the W20 restore test; after that it runs continuously.
- `rclone check` confirms the SeaweedFS replica matches the primary.
- `import_stations.py` against a bad-rows fixture reports each error with its row number (STN-8).
- Every alert in TRD §16.5 is fired once on staging and its email checked.

## Test data and environments

One seed set serves every level, so a failure on staging can be reproduced locally with the same users and records.

### Seed users (`infra/scripts/seed.py`)

| User | Role | Purpose |
|---|---|---|
| Client A1, Client A2 | Client, organization A | Own-organization access; two clients on one request |
| Client B1 | Client, organization B | Out-of-scope checks: must get 404 on everything of A's |
| Admin | Admin | Approvals, assignment, owner changes, restores, audit log |
| Tech 1, Tech 2 | Technician | Claiming; two technicians on one visit owning different stations (OFF-11) |
| Tech-Admin | Technician + Admin | A staff user with several roles |
| Viewer | Viewer | Read-only: 403 on every mutating route, no audit log |
| Disabled user | Client, disabled | Tokens refused |
| Pending registration | none yet | J1 approval and rejection |

Seed records cover:

- at least two stations per organization, in different IANA time zones
- a sensor model installed at an organization A station only, with a client-visible manual
- sensor units with calibrations due and overdue
- one request in each status, including one with two parallel visits

### Factories and determinism

- Each service has `tests/factories.py` built on `polyfactory` from its Pydantic models.
- Tests use a fixed clock and a seeded UUIDv7 generator, so IDs, timestamps and `MR-`/`VR-` numbers are stable in snapshots and PDFs.
- No test depends on another test's data; API tests use a fresh database per test module.

### Environments

| Environment | Used for | Data |
|---|---|---|
| testcontainers | Unit and API tests in CI | Factories |
| Local Compose (`compose.dev.yml`) | Integration and E2E during development; Mailpit captures email | Seed set |
| CI Compose | Integration and E2E on `main` and nightly | Seed set |
| Staging | Smoke tests per deploy, ZAP, restore drills, demos, field test | Real station import (from W5) + seed users |
| Production | Smoke tests after deploy, pilot | Real data |

## CI pipeline and gates

The cheap checks run on every pull request; the slow ones run on `main`, nightly and weekly, so a PR gets an answer in minutes. This extends TRD §18.

```
Every change passes PR checks and staging smoke before production

┌──────────────────────────────────────────────────────────────────────────────┐
│ Every pull request                                                           │
│ Changed services: Ruff, mypy, import-linter, no-direct-produce check,        │
│   unit, API and contract tests                                               │
│ Frontend: ESLint, vue-tsc, Vitest, build, OpenAPI type drift check           │
│ Gateway: nginx -t                                                            │
│ pip-audit, npm audit, Trivy; coverage 90% for domain/ and 70% overall        │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │ all green + human review of the diff → merge
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Merge to main                                                                │
│ Images built and tagged with the commit SHA; integration tests on CI Compose │
│ Deploy to staging; Playwright smoke for every journey delivered so far       │
│ Security headers, CSP, rate limits and /internal checks on staging           │
└───────────────────┬──────────────────────────────────────┬───────────────────┘
                    │ scheduled, on staging                │ manual approval
                    ▼                                      ▼
┌──────────────────────────────────────┐ ┌─────────────────────────────────────┐
│ Nightly and weekly                   │ │ Production deploy                   │
│ Full E2E: Chromium, Firefox, WebKit  │ │ Same images as staging              │
│ Visual regression of shells and PDFs │ │ Smoke tests; rollback = previous tag│
│ OWASP ZAP baseline scan              │ │ Go-live: 7 green nights in a row    │
│ Weekly: restore drill, mutation tests│ │ and the PRD §8 launch criteria      │
└──────────────────────────────────────┘ └─────────────────────────────────────┘
```

A nightly failure blocks the next production deploy but not merges. A failing nightly job is fixed before new feature work starts that day.

## Tests by phase

Each test is built in the first phase that needs it, and the harnesses come in Phase 1 so every later service inherits them from the copier template. The phase gate in the IP stays: exit criteria on staging, definition of done, journeys added to the smoke suite, coverage met, demo seen.

| Phase | Weeks | Tests built | Gate evidence |
|---|---|---|---|
| 0 · Readiness | W1 | Test plan approved; test phones ordered; SeaweedFS spike checks (multipart, CORS `ETag`, abort, versioning, lock) | Spike passes |
| 1 · Foundations | W2–W4 | Authorization matrix and client leak harness in `mms_common`; `import-linter` and no-direct-produce lint in the template; injectable clock and seeded UUIDv7; outbox leader-lease, consumer and duplicate tests; audit tamper and role tests; database isolation test; JWT, login-throttle and refresh-race tests; Nginx routing, 404 for `/internal/` and CSP checks; seed set; Playwright with axe, CSP and screenshot fixtures; J1, J2 | W2 checkpoint passes in CI; a new service from the template passes every harness unchanged |
| 2 · Stations | W5–W7 | Station import bad-rows fixture; document media fixtures (EICAR, magic bytes, size); fail-closed visibility and model-document tests; multipart abort; label-sheet PDF baseline; QR scan on real phones | Real import report; W7 label scan |
| 3 · Requests | W8–W9 | Request state machine and derivation property tests; internal-comment attachment visibility; Mailpit email assertions; WebSocket catch-up after reconnect; `user_directory` backfill; J3, J4 | Every allowed and blocked transition tested |
| 4 · Visits online | W10–W12 | Parallel-visit and owner tests; sensor reconciliation and reversal; image and video fixtures, EXIF and playback checks; visit end rules; online J5 | W11 video timing on staging; a corrected serial fixes the history |
| 5 · Offline | W13–W15 | `/sync` properties, conflict codes and fault injection; PIN session; Dexie tests; shared-device cache test; Playwright offline in Chromium and WebKit; J6; field test | W13 iOS restart-and-unlock check; W15 field test with zero loss |
| 6 · Reports | W16–W18 | Report PDF baselines; finalize saga faults; immutability and signature invalidation; report reopen in Client Review and after Closed; report read-model backfill; reminders and auto-close under the clock; J7–J9 | Auto-close and close-out under clock override; backfill matches live build |
| 7 · Hardening | W19–W20 | Summary PDF and CSV baselines; NFR-2 timings; ZAP nightly; Locust load and soak; weekly restore job; alert firing; J10 | No open high or critical findings; load test meets NFR-2; restore passes the chain check |
| 8 · Pilot | W23–W25 | Pilot defects become regression tests; second field test on pilot technicians' phones | Launch criteria (PRD §8) |

## Requirement traceability

Every NFR has at least one automated check, and every journey has a Playwright test. Functional requirements are traced in the tests themselves: each test carries a `@pytest.mark.req("REQ-3")` marker or a Playwright tag `@REQ-3`, and a CI report lists every **M** requirement without a test.

| NFR | Checked by |
|---|---|
| NFR-1 Scale | Locust with 5× seed volume |
| NFR-2 Performance | Locust p95 < 1 s; draft PDF ≤ 10 min and summary ≤ 2 min in the integration stack |
| NFR-3 Availability | Alert firing on staging; smoke tests after each deploy |
| NFR-4 Offline | Sync properties, conflict codes and faults, PIN session, Playwright offline, field test |
| NFR-5 Devices | Playwright browser projects and device emulation; real phones |
| NFR-6 Security | Authorization matrix, client leak test, fail-closed visibility, JWT tests, ZAP, dependency scans |
| NFR-7 Privacy | EXIF and GPS check on processed images; client leak test |
| NFR-8 Retention | Original-media deletion under the clock; audit insert-only test |
| NFR-9 Backup | Weekly restore job with chain check; replica check |
| NFR-10 Hosting | Integration and E2E run on the same Compose files as production |
| NFR-11 Accessibility | axe per route in both themes |
| NFR-12 Maintainability | Template harnesses; coverage gates |
| NFR-13 Architecture | Import lint, no-direct-produce lint, database isolation, contract tests |
| NFR-14 Time | UTC round-trip property test; DST display tests |
| NFR-15 Extensibility | Contract tests on every event schema version and snapshot endpoint |

| Journey | Playwright test | Smoke suite from |
|---|---|---|
| J1, J2 | `auth.spec.ts` | Phase 1 |
| J3, J4 | `requests.spec.ts` | Phase 3 |
| J5 | `visit-prepare.spec.ts` | Phase 4 (claim, schedule, owners); prepare step and PIN added in Phase 5 |
| J6 | `visit-offline.spec.ts` | Phase 5 |
| J7, J8, J9 | `reports.spec.ts` | Phase 6 |
| J10 | `summaries.spec.ts` | Phase 7 |

## Defects and release criteria

A release goes out only when every gate passes; a defect found in staging or the pilot gets a regression test before it is closed.

| Severity | Meaning | Release rule |
|---|---|---|
| Critical | Data loss, a cross-organization leak, a broken audit chain, a sync that loses or duplicates records | Blocks every release; fixed the same day |
| High | A journey can't be completed, a viewer can mutate, a wrong report is finalized, a request stuck in a wrong status | Blocks the release |
| Medium | A workaround exists | Fixed in the next phase or fix release |
| Low | Cosmetic, copy | Backlog |

**Staging release (end of each build phase):** the IP phase gate, plus no open critical or high defects and no failing nightly job.

**Production go-live:** the PRD §8 launch criteria, plus a clean ZAP baseline, the last weekly restore passed, and 7 nights in a row of a green full E2E suite on staging.

## Open questions

| # | Question | Assumption until decided |
|---|---|---|
| V1 | Which HTTP status codes and error body do the services return (validation error, conflict, locked)? The TRD doesn't define them, and the tests need a fixed contract. | RFC 9457 problem details: 422 validation, 409 conflict (including writes to a finalized report and `sensor_changed_later`); sync conflicts use the reason codes in TRD §7.4 |
| V2 | Do CI runners have enough memory to run the full Compose stack nightly (about 18.5 GB in production)? | A slimmed CI profile without monitoring and with ClamAV signatures pre-loaded; otherwise run nightly on the staging host |
| V3 | Is an external penetration test wanted before go-live or after the pilot? | Not in v1; the internal ASVS L2 review and ZAP cover launch |
| V4 | Which phones are used for the field test, and does the organization own them? | One current iPhone and one mid-range Android bought in Phase 0 (IP: devices by W13) |
| V5 | Can an anonymized copy of production be used on staging for restore drills after go-live? | Yes for restore drills; staging access limited to staff |
