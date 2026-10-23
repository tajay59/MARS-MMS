# Implementation Plan
## AWS-MMS — Automatic Weather Station Maintenance Management System

| | |
|---|---|
| **Version** | 1.2 (draft) |
| **Date** | 2026-10-22 |
| **Status** | Draft for review |
| **Changes in 1.2** | Phase 4: the visit board replaces work records, sensor reconciliation and checklist templates (decisions W11-16 to W11-35, 2026-10-22; plan in `docs/plans/visit-board-plan.md`). W12 becomes the board on a phone and the client's view; Q5 is closed |
| **Changes in 1.1** | Follows TRD 2.0: five services (operations replaces station, maintenance and visit; platform replaces notification and audit; no integration stub), Nginx instead of Kong, SeaweedFS instead of MinIO. Phase 2 grows to 3 weeks, so go-live moves to the end of **week 25**. Label PDFs come from the report service, whose skeleton moves to Phase 2. New work: offline PIN session, station owners, request status derivation, sensor-action correction, finalize saga and read-model backfill. The definition of done adds the design review |
| **Builds on** | [PRD.md](PRD.md) v1.1, [TRD.md](TRD.md) v2.0, [AFD.md](AFD.md) v1.1 (App Flow), [DBD.md](DBD.md) v1.2 (Design Brief), [BSD.md](BSD.md) v1.1 (Background Schema), [TP.md](TP.md) v1.1 (Test Plan) |
| **Replaces** | PRD §8 Release plan and TRD §20 Implementation phases |
| **Live copy** | [Claude Doc](https://claude.ai/code/artifact/de63972b-b743-4ad1-b5fa-85325dc22312) (1.0; superseded by this file) |

AWS-MMS goes live in about 25 weeks: a 1-week readiness phase, 19 weeks of build in the seven PRD phases, a 2-week buffer, and a 3-week pilot and go-live. A release goes to staging at the end of every build phase so staff can use each module before clients see anything.

---

## Purpose and scope

This plan sets what gets built, in what order, and how we know each phase is done. It covers the v1 scope in PRD §3 only. Routine maintenance, integrations and SLAs (PRD §10) stay out.

Each phase lists its goal, deliverables, weekly milestones, the PRD requirements and App Flow journeys (J1–J10) it delivers, what it depends on, the staging release, and exit criteria. Requirement IDs (AUTH-1, VIS-7, …) are the PRD's. Service and container names are the TRD's: `auth`, `operations`, `media`, `report`, `platform`.

## Approach and planning assumptions

One developer builds AWS-MMS, with Claude Code writing most of the code. That brings the build down from the PRD's 21 weeks to 19, but no further. The slow parts are infrastructure debugging, testing on real devices, and waiting on people.

| Assumption | Detail |
|---|---|
| Team | One full-time developer working with Claude Code. An admin from the organization acts as product owner: about 2 hours per phase to try the staging release and answer questions. |
| Calendar | Relative weeks W1–W25, 5 working days each. No holidays are counted; add them when a start date is set. |
| Scope | PRD §3 v1. Every **M** requirement is in. **S** requirements are in their phase but can move to after launch if the phase runs late. RPT-11 (**C**) is built only if the buffer is unused. |
| Environments | Local Compose stack from W2. Staging on the second host from the end of Phase 1. Production built in Phase 7. |
| Inputs | The organization makes the decisions listed under Phase 0 by the dates in *Decision deadlines*. A late decision moves the phase that needs it, not the whole plan. |

### Where Claude Code saves time

| Work | Saving | Why |
|---|---|---|
| Service scaffolding, CRUD endpoints, Pydantic models, state-machine tests | Large | Repetitive, well specified in the TRD, and the copier template keeps every service alike |
| Vue screens and Vuetify components | Medium | The Design Brief fixes tokens, shells and components; each new screen still gets an HTML mock-up for approval and a review on real screens |
| PDF templates (WeasyPrint) and email templates | Medium | Templates are quick to write; print layout needs several visual passes |
| Infrastructure: Kafka, Nginx gateway, outbox relay, SeaweedFS, TLS, backups | Small | Time goes on debugging the running stack, not on writing config |
| Offline mode on real iOS and Android devices | None | Device behaviour (storage eviction, camera, background upload) has to be tested by hand |
| UAT, pilot, training, waiting on decisions | None | People's time |

### Working rhythm

- **CLAUDE.md first.** It already holds the service layout, the non-negotiable rules ("never access another service's database", "all state changes go through the state machine and the outbox") and the definition of done. It keeps generated code inside the architecture, and is updated as commands and code arrive.
- **Mock-up before build.** Each new screen gets a static HTML mock-up built from DBD tokens, published as a private artifact for the product owner's approval, then built in Vue (CLAUDE.md, "Workflow for each screen").
- **Weekly checkpoint.** Every Friday, compare progress against that week's milestone. A slip of more than 3 days is taken from the buffer and recorded in the plan.
- **Phase demo.** Each build phase ends with a staging release and a 30-minute demo to the product owner. Feedback goes into the next phase or the backlog, not back into the closed one.
- **Real data early.** The station import (STN-8) runs against staging in Phase 2, so staff test every later phase on their own stations.

### Definition of done

A feature is done when:

- [ ] Unit and API tests pass, including org scoping and 404 for out-of-scope records (TRD §17)
- [ ] New routes are in the authorization matrix, and new tests carry the requirement IDs they cover (TP)
- [ ] Ruff, mypy, ESLint and vue-tsc are clean
- [ ] OpenAPI is regenerated; event schemas in `mms_common.events` and the audit mapping are updated
- [ ] Screens work in light and dark themes and pass an axe check (WCAG 2.2 AA)
- [ ] New or changed screens have passed a `web-design-guidelines` review
- [ ] The developer docs site (`docs/index.html`) describes what was built, with the phase's chosen charts and a changelog entry (CLAUDE.md, "Developer documentation site")
- [ ] CI is green and the build is deployed to staging

## Timeline at a glance

Nine phases and a buffer run back to back over 25 weeks, followed by 2 weeks of hypercare.

```
Go-live at the end of week 25, with a staging release after every build phase
(◆ = staging release, ★ = go-live, ░ = buffer / hypercare)

Week                              1   3   5   7   9   11  13  15  17  19  21  23  25  27
                                  |...|...|...|...|...|...|...|...|...|...|...|...|...|.
0 · Readiness             W1      ██
1 · Foundations           W2–4      ██████ ◆ 0.1
2 · Stations              W5–7            ██████ ◆ 0.2
3 · Requests              W8–9                  ████ ◆ 0.3
4 · Visits online         W10–12                    ██████ ◆ 0.4
5 · Offline field mode    W13–15                          ██████ ◆ 0.5
6 · Reports, signatures   W16–18                                ██████ ◆ 0.6
7 · Summaries, hardening  W19–20                                      ████ ◆ 0.7
Buffer                    W21–22                                          ░░░░
8 · Pilot and go-live     W23–25                                              ██████ ★ 1.0
Hypercare                 W26–27                                                    ░░░░
```

Each build phase ends with a staging release (0.1 to 0.7) for staff only. Clients first use the system in the Phase 8 pilot.

| Phase | PRD estimate (weeks) | This plan (weeks) | Why |
|---|---|---|---|
| 0 · Readiness | — | 1 | New: decisions and hosts in place before coding |
| 1 · Foundations | 3 | 3 | Fewer services, but infrastructure debugging does not compress |
| 2 · Stations | 3 | 3 | The largest domain, plus the report service skeleton for label sheets |
| 3 · Requests | 3 | 2 | State machine and notifications are fully specified |
| 4 · Visits online | 3 | 3 | Media pipeline, the visit board and testing on phones |
| 5 · Offline field mode | 3 | 3 | Real-device testing |
| 6 · Reports and signatures | 3 | 3 | Several visual passes on the PDF layout |
| 7 · Summaries and hardening | 3 | 2 | UAT moves to Phase 8 |
| Buffer | — | 2 | New: about 10% contingency |
| 8 · Pilot and go-live | in Phase 7 | 3 | New: data import, training, pilot |
| **Total to go-live** | **21** | **25** | 19 build weeks instead of 21, plus the new phases and buffer |

## Phase 0 · Readiness and decisions (W1)

**Goal:** by the end of W1, the servers, domains and repository exist, and every decision that blocks Phase 1 is made. Little code gets written this week. Its job is to stop Phase 1 from waiting on the organization.

**Deliverables**

| Item | Detail | Closes |
|---|---|---|
| Document sign-off | PRD, TRD, App Flow, Design Brief, Background Schema, Test Plan and this plan approved by the product owner | — |
| Blocking decisions | Outbound internet, Git and registry, single-node Mongo/Kafka, domains and TLS, host RAM, disk encryption | T1, T2, T5, T6, T8, B1 |
| Production host | 8 vCPU, 32 GB RAM, 200 GB SSD + 1 TB RAID-1 (TRD §16.2). OS, Docker, LUKS disk encryption, firewall, SSH keys | B1 |
| Second host | Staging stack and backup target, same OS and Docker setup | — |
| DNS | `mms.` and `files.mms.` records for production and staging | T6 |
| Repository | GitHub repo `tajay59/MARS-MMS`. Done 2026-10-16: `main` pushed, with line-ending rules (`.gitattributes`, `.editorconfig`) and a frontend CI workflow (lint, type-check, build). Milestones P0–P8 created, with the open Phase 0 work as issues #1–#10 in P0, on the project board [AWS-MMS](https://github.com/users/tajay59/projects/2). CI now runs on every pull request, so `check` can be a required status. The repo was made public on 2026-10-16, which made branch protection available on GitHub Free: `main` now needs a pull request with a green, up-to-date `check`, linear history (squash or rebase merges only), resolved conversations, no force pushes or deletions, and admins are included. Secret scanning with push protection and Dependabot alerts are on (#6 closed). GHCR has nothing to set up until Phase 1 publishes images (the publishing workflow grants itself `packages: write`; the default workflow token stays read-only) | T2 |
| SeaweedFS spike | **Passed 2026-10-16** (`infra/spikes/seaweedfs/`, SeaweedFS 4.48): all 15 server-side checks (7 MUST, 2 NICE, 3 INFO) and the browser checks in Chrome 155 (20 MiB in 3 parts, a 50.9 MiB video in 7 parts in 2.0 s, abandon and abort). Versioning and object lock work. A 152.8 MiB phone video uploaded from Android Chrome over Wi-Fi in 20 parts in 47.5 s, read back intact. Firefox 158 passed the same browser checks (20 MiB in 1.0 s, the 50.9 MiB video in 2.5 s, abandon and abort). All checks done; an iPhone run is optional. Results in the spike README | T7 (confirmed), R6 |
| Requests to the organization | Sent with a due date: SMTP relay details (T3), station and sensor export (T4, Q4), branding (Q1, D1, D5), request categories (Q6), signature wording and jurisdictions (Q2, Q3) | Tracked in *Decision deadlines* |

**Weekly milestone**

| Days | Milestone |
|---|---|
| Mon–Tue | Sign-off meeting; blocking decisions made; requests to the organization sent |
| Wed–Thu | Both hosts provisioned; DNS records created |
| Fri | Repository and board set up; SeaweedFS spike done |

**Exit criteria:** both hosts accept SSH and run `docker compose version`; the four domain names resolve; the SeaweedFS spike passes; the documents are marked approved.

## Phase 1 · Foundations (W2–W4)

**Goal:** the platform runs end to end. A client registers, an admin approves them, they log in and reset their password, and every step lands in the audit log.

**Deliverables**

- **Monorepo** laid out as TRD §19, with `mms_common` (auth, events, outbox with leader lease, kafka, consumer, mongo, logging, errors, ids, time, snapshot), the copier service template, and `CLAUDE.md` updated with commands.
- **Compose stack:** Nginx as edge and gateway (routes, rate limits, request IDs, CSP), MongoDB `rs0`, Kafka (KRaft), Redis, SeaweedFS, and Mailpit for local email.
- **auth service:** registration and approval, invitations, login, refresh tokens (EdDSA JWT) with the 30-second rotation grace, password reset, rate limits, breached-password check with throttling that doesn't reveal accounts, disabling users, organizations, profile, AUTH-5 purge cron.
- **platform service, part 1:** the audit module (consumes every topic, hash-chained insert-only collection, restricted Mongo role) and account email from the notification module (approval, rejection, invitation, reset). WebSocket and in-app notifications follow in Phase 3.
- **Frontend:** build on the existing theme foundation in `frontend/` (brand themes in light and dark, cascade layers, global defaults, MDI icons, Google Sans and Roboto Flex, `theme-init.js`): the three shells, public pages (login, register, reset, set password), admin pages for registrations, users and organizations, My profile with the theme setting, and the Web Lock refresh coordination.
- **CI and staging:** GitHub Actions lint, type-check, test and build per changed service, `nginx -t`, plus Trivy; images pushed to GHCR and deployed to staging on `main`.
- **Test harnesses (TP):** the authorization matrix and client leak test in `mms_common`; `import-linter` and the no-direct-produce check in the service template; an injectable clock and seeded UUIDv7s; outbox, leader-lease and consumer tests; audit tamper and role tests; JWT and refresh-race tests; the seed users; Playwright with axe, CSP and screenshot checks. Every later service inherits them from the template.

**Weekly milestones**

| Week | Milestone |
|---|---|
| W2 | Repo, `mms_common` core (mongo, outbox with leader lease, kafka, logging, clock), service template with its lint and test harnesses. Full Compose stack up locally behind Nginx. |
| W3 | auth service complete with tests. platform's audit module builds the chain from auth events. Nginx routes and CI running. **Done 2026-10-17** (branch `feat/p1-w3-auth`): register → approve → log in → refresh → reset runs through Nginx and lands in the audit chain in the stack test. |
| W4 | Frontend shells and auth screens. Account emails. Staging deploy pipeline. Playwright test for J1 and J2. **PWA findings adopted 2026-10-17:** a minimal service worker and manifest now (F5: precache, navigation fallback, update prompt; no tiles, no Background Sync), the manifest served `no-cache` (F10), earlier releases' assets kept 7 days (F9), safe-area padding in the field shell (F13). **Done 2026-10-18** on staging: register → approve → log in → reset by hand into the audit chain, and the update prompt between two real releases (release 0.1). The real-phone test is issue #8. |

**Delivers:** AUTH-1 to AUTH-11, AUTH-13, ORG-1, ORG-4, NOT-3, AUD-1 (account events), AUD-2, AUD-3, AUD-5 (chain only). Journeys J1, J2.

**Depends on:** Phase 0 hosts and repo; T1 (breached-password API reachable or local list); T3 SMTP relay for staging email by the end of W4 (met for now by an interim Gmail account; TRD §22).

**Staging release 0.1:** the product owner registers a test client, approves it, and resets a password. **Done 2026-10-18** (the release shows `Version 0.1.0` on the public pages).

**Exit criteria:** register → approve → log in → reset works on staging, each step appears in the audit collection, and a new service can be created from the template and pass CI, including the authorization matrix and architecture checks, unchanged. **Met 2026-10-18:** on staging the test client's `user.registered`, `user.approved`, `auth.login_succeeded`, `auth.password_reset_requested`, `auth.password_reset` and the login with the new password are in the chain, and `verify()` finds no break over all 36 records; CI's `service template` job generates both variants and passes them unchanged.

## Phase 2 · Stations (W5–W7)

**Goal:** staff can find any station, see its sensors, calibrations, documents and configuration history, open it by scanning its QR label, and print label sheets.

**Deliverables**

- **operations service, stations module:** stations, sensor models, sensor units (with `current_org_id`), installation history and calibration records (with `org_id`), document metadata and the document download endpoint (model documents for clients), configuration versions with checksum diff, QR tokens, the `import_stations.py` script, and the snapshot endpoints.
- **media service, documents path:** presigned multipart uploads (8 MiB parts) to the `files.` host, the owner check, fail-closed visibility driven by `media.visibility_requested`, ClamAV scanning, size limits, and the `abort_stale_uploads` cron. Images and video come in Phase 4.
- **report service skeleton and report-worker:** the render pipeline, `base.html.j2` and `print.css`, and the label sheet PDF (QR-6). Visit reports and summaries come in Phases 6 and 7.
- **Frontend:** station list with filters, the station page and its tabs, the sensor model catalogue, sensor units, calibration records and certificates, document upload with versions, configuration upload and compare, the calibration-due list, the map with clustering, the in-app QR scanner, the `/s/:token` landing page, and label printing.

**Weekly milestones**

| Week | Milestone |
|---|---|
| W5 | Stations, models, units, installations and calibrations, with tests. Real station export imported into staging (**done 2026-10-18**: 8 organizations and 50 stations, no rejected rows; decision W5-9). Station list and page. **Backend built 2026-10-18** (branch `feat/p2-w5-stations`): the operations service's stations module, the import with dry run (API and CLI) and a demo seed; 84 tests, 95% coverage. Station list and page mock-ups approved and **built 2026-10-18** (Overview, Sensors and Calibration tabs; the station form for New and Edit still needs a mock-up). **T4 answered 2026-10-18 (W5-8):** the organization's existing system is a MongoDB; its `entities` and `sites` exports come in with `import-orgs` (auth) and `import-stations` (operations), one station per device. Waiting on the export files themselves. |
| W6 | Document and configuration uploads through the media service, with fail-closed visibility. Model documents for clients. Calibration-due list. **Backend built 2026-10-19** (branch `feat/p2-w6-documents`): the media service (documents path: presigned multipart uploads resumable from the store's part list, owner check, fail-closed visibility, ClamAV scan with a `clamd\|off` switch, stale-upload and reconcile cron), operations' documents, configuration versions with a checksum diff and calibration certificates, a Redis job queue, and the resumable upload engine in `frontend/src/offline/`; 116 media tests, 136 operations tests, and a stack test that uploads through Nginx and the files host. Found on the way: SeaweedFS ran out of volume slots on the second bucket (fixed, TRD R6). **Screens built 2026-10-19** from the approved "AWS-MMS W6 screens" canvas (station Documents and Configurations tabs, the upload and new-version dialogs, the sensor model catalogue, calibration due, the client view, phones), then the leftover forms (sensor models and units, document details; W6-10, W6-11) and the Sensors page redesign (W6-12). Merged in #36 and #39. **Still open:** the iPhone check of uploads from the installed app (F15) and files over 64 MiB (F4). Q7 decided: staff-only by default. |
| W7 | QR tokens and `/s/:token`. Map. Report service skeleton and label sheets. **Back end built 2026-10-20** (branch `feat/p2-w7-qr-map-labels`): QR resolve with revoked tokens (410) and regenerate in operations, `POST /internal/labels`, and the report service skeleton (`report` and `report-worker`, WeasyPrint, label sheets of ten per A4 page, `report_jobs`, downloads from `mms-reports`); 144 operations tests, 59 report tests, and a stack test that draws a sheet through Nginx and the files host. Screens built 2026-10-20 from the approved "AWS-MMS W7 screens" mock-up (scanner and landing states, map, label tool, station QR card); merged in #40 and deployed to staging. **Still open:** the exit check on real phones (a printed label scanned by an iPhone and an Android camera app and the in-app scanner; the sheet to follow is [checks/W7-label-scan-check.md](checks/W7-label-scan-check.md); Android first, iPhone postponed) and the staging copy of the map file (F1 is built, W7-9: a self-hosted Protomaps extract of the Caribbean replaces OSM tiles; the 552 MB file goes to `/opt/mms/tiles` on the host). |

**Delivers:** ORG-2, ORG-3, STN-1 to STN-8, SEN-1 to SEN-3, CAL-1 to CAL-4 (list only; the dashboard widget comes in Phase 7), CAL-6 (flag), DOC-1 to DOC-4, CFG-1 to CFG-3, MED-3, MED-6 (documents), QR-1 to QR-7, MAP-1 to MAP-4.

**Depends on:** Phase 1; the station and sensor export (T4, Q4) by the start of W5; Q7 decided.

**Staging release 0.2:** admins and technicians browse their real stations, print a label sheet, and scan labels at two or three stations.

**Exit criteria:** a station with sensors, calibrations, configuration versions and manuals opens on a phone from its QR label. The real station list imports, with any bad rows reported by row number. A test client sees a model manual only while that model is installed at one of their stations.

## Phase 3 · Requests (W8–W9)

**Goal:** a request moves from Submitted to Assigned, and everyone involved is told in real time.

**Deliverables**

- **operations service, requests module:** the request state machine (explicit transitions and the derivation function, ready for visits in Phase 4), `MR-YYYY-NNNN` references, the queue, assignment and claiming, comments (including internal ones, with attachment visibility following the internal flag), attachments through the media service, edit and cancel rules (admin cancel up to closure), filters, and turnaround timestamps.
- **platform service, part 2:** the notification module complete. WebSocket channel, notification list with catch-up after reconnecting, email for every Appendix B event, per-type email preferences, `entity.updated` for live pages, the weekly calibration digest, and `user_directory` backfilled from auth.
- **Frontend:** the new-request form (from the dashboard, the station page and the QR landing page), the request page with its status timeline and comments, approve and deny, the `/queue` page, the notification bell and list, and the preferences page.

**Weekly milestones**

| Week | Milestone |
|---|---|
| W8 | State machine with a test for every allowed and blocked transition, plus property tests on the derivation function. Request endpoints and screens. J3 works. **Built 2026-10-21** (branch `feat/p3-w8-requests`): the requests module in `operations` (state table with 80 status and action pairs tested, `derive_status` with property tests, create idempotent by a device-made ID, list with filters, read, edit, approve, deny, cancel, `MR-YYYY-NNNN`, `request.*` events and the snapshot) and the screens from the approved "W8 Requests screens" mock-up (list, new and edit form, request page with timeline and History, deny and cancel dialogs; phones). Operations 319 tests, Vitest 308, 9 Playwright journeys. Decisions W8-1 to W8-9: approve and deny came into W8, PDF attachments moved to W9 with comments. |
| W9 | Queue, assignment, claiming and comments. WebSocket and email notifications with preferences. J4 works. |

**Delivers:** REQ-1 to REQ-11, REQ-15, REQ-16 (timestamps), NOT-1 to NOT-5, CAL-5. Journeys J3, J4, and the claim step of J5.

**Depends on:** Phase 2 (stations to report against); Q6 request categories and priorities; T3 SMTP relay live on staging.

**Staging release 0.3:** staff role-play the workflow. Test client accounts submit requests, admins approve and assign, and technicians claim from the queue.

**Exit criteria:** Submitted → Approved → Assigned, Denied and Cancelled all work on staging. In-app notifications arrive within a few seconds and emails within a minute. Every transition is in the audit collection. An internal comment's attachment is never visible to a client.

## Phase 4 · Visits online (W10–W12)

**Goal:** a technician records a whole visit online on each station's board (Notes, Tasks, Recommendations, Config), and a Config element's After files become the station's configuration version.

**Deliverables**

- **operations service, visits module:** scheduling, rescheduling and cancelling (including multi-day and parallel visits), attending staff with a lead and an **owner per station**, start, arrival and departure per station, end rules, "another visit needed", and the request status derived from visits in the same transaction.
- **The visit board:** one per station on a visit, in `visit_elements`: Notes, Tasks (typed items with checkboxes, Before and After media), Recommendations (priority, Create request) and Config (Before and After files of any kind). Each element is saved on its own with `base_version` and a tombstone on delete. *(Replaced on 2026-10-22: checklist templates, the structured work record and sensor reconciliation, built in W10 and W11, are removed; sensor swaps are recorded on the Sensors page.)*
- **media-worker:** images to WebP with thumbnails and EXIF/GPS removed, video compressed with ffmpeg, virus scanning, resumable multipart uploads, `purge_originals` and `reconcile` crons.
- **Frontend:** visit page with station owners and **Change owner**, the board as sticky notes with an element sheet that shows every file in place (photos, video, PDF, text and code), the same board on phones in the field shell. Clients see the shared elements of ended visits.

**Weekly milestones**

| Week | Milestone |
|---|---|
| W10 | Visit lifecycle, scheduling, parallel visits and station owners with tests. Request status derivation wired to visits. Checklist template editor. Scheduling step of J5. |
| W11 | Work records and sensor reconciliation (apply, reverse, re-apply, refuse when changed later). Image and video pipeline in media-worker, tested with the TP media fixtures (iPhone and Android files, GPS EXIF, EICAR). |
| W11 (second half) | The visit board replaces the work record: back end, file viewers, board screens, Config versions and Create request (`docs/plans/visit-board-plan.md`). |
| W12 | The board in the field shell tested on phones. Client view of shared elements. Playwright test of an online visit. |

**Delivers:** VIS-1 to VIS-5, VIS-7 to VIS-11 (VIS-6 dropped), CFG-4 (online), MED-1, MED-2, MED-4, MED-5, MED-7, the "Start visit" action in QR-3.

**Depends on:** Phases 2 and 3.

**Staging release 0.4:** two technicians record a mock visit on their phones at a nearby station, each owning one station, each filling in its board with all four kinds, a Config file and a 2-minute video.

**Exit criteria:** a visit recorded online fills a board for each station, and a Config element's After files become the station's configuration version at the end of the visit. A technician sees only their own stations' Arrive and Depart, and a client sees only the shared elements of an ended visit. A 2-minute video plays in Chrome and iOS Safari after processing. Processed images carry no GPS data. (Changed 2026-10-22: visits no longer change the sensor inventory, decision W11-17.)

## Phase 5 · Offline field mode (W13–W15)

**Goal:** a complete visit, media included, is recorded with no signal and synced later with zero loss. This phase keeps its full PRD length: its last week is hands-on device testing, which Claude Code cannot shorten.

**Deliverables**

- **PWA:** installable app built on the vite-plugin-pwa (`injectManifest`) worker added in Phase 1 (F5), an install prompt, `storage.persist()` (risk R4), and a service worker that caches the app shell and map tiles only.
- **Offline session:** PIN set on first prepare, PBKDF2 verifier, `/unlock` page, five-attempt lockout, profile and bundles cleared on logout, 30-day field session (AUTH-12).
- **Prepare for field:** downloads the request, stations, sensors, calibration status, latest configuration files, the stations' boards and manuals to Dexie as data and blobs (OFF-1).
- **Offline capture:** the outbox of operations with UUIDv7 IDs and idempotency keys, owner-only work operations, and offline QR lookup.
- **Sync:** the `/sync` endpoint, resumable media uploads, the conflict codes (`not_owner`, `stale_version`, `locked`, `visit_cancelled`, `already_ended`), visit restore for admins, and local copies cleared only after the server confirms.
- **Sync status UI:** pending changes, pending files and storage used, the "Needs attention" group with **Export**, "Sync now" and the unprepared-visit warning.

**Weekly milestones**

| Week | Milestone |
|---|---|
| W13 | Service worker and Dexie stores. PIN session and `/unlock`. Prepare-for-field download. Offline station lookup by QR. |
| W14 | Offline outbox, `/sync`, idempotency, resumable uploads and conflict handling. `/sync` property and fault-injection tests. Playwright offline tests (`setOffline`) in Chromium and WebKit. |
| W15 | Field test on a real iPhone and Android phone in a no-signal area. Fixes from the field test. |

**Delivers:** OFF-1 to OFF-11, AUTH-12, QR-5 (offline), CFG-4 (offline). Journeys J5 (prepare) and J6.

**Depends on:** Phase 4; a current iPhone and Android phone for W13–W15; one day of two technicians' time in W15 for the field test.

**Staging release 0.5:** two technicians install the PWA and run the field test.

**Exit criteria:** a full visit is recorded offline on both iOS and Android, including a phone restart mid-visit and PIN unlock, then synced on return with no lost or duplicated records or files. Syncing the same visit twice changes nothing. Work for a station whose owner changed while offline comes back as a conflict and can be exported.

## Phase 6 · Reports and signatures (W16–W18)

**Goal:** every visit ends in a signed, locked PDF report, and the client either signs off the work or it closes on day 30.

**Deliverables**

- **report service and report-worker, complete:** the automatic draft from synced visit data (PRD Appendix A), the narrative and photo editor, PDF preview, signatures (`signature_pad`, typed name, attestation), the finalize saga (lock, render, retry, roll back, resume), reopen for correction, finalize reminders, branding and `VR-` numbering, and times in the station's zone.
- **Read-model backfill:** `backfill.py` builds the report read model from operations and media snapshots, covering everything entered since Phase 2, before the consumers take over.
- **Client review:** the Client Review state, accept with a signature, reject with a reason, reminders on days 7, 21 and 28, the day-30 auto-close cron, and the return to In progress when a report is reopened.
- **Client reports:** PDF upload, or the online form rendered to PDF.
- **Close-out report:** generated when a request closes, and regenerated when a report of a closed request is corrected.
- **Visit lock:** finalizing locks the visit's boards (VIS-12).

**Weekly milestones**

| Week | Milestone |
|---|---|
| W16 | Report drafts from visit events. Backfill run on staging. Visit report PDF template and preview, with its visual regression baseline. |
| W17 | Editor, signatures, finalize saga and reopen. Visit lock. J7 works. |
| W18 | Client review, reminders and auto-close (tested with a clock override). Client reports. Close-out report. J8 and J9 work. |

**Delivers:** RPT-1 to RPT-10, REQ-12 to REQ-14, CRP-1 to CRP-5, VIS-12. Journeys J7, J8, J9.

**Depends on:** Phase 5 (drafts come from synced visits); Q1 branding and numbering, Q2 attestation wording and Q3 jurisdictions, all by the start of W16.

**Staging release 0.6:** technicians sign the reports for their test visits. The product owner, using a client account, accepts one and rejects another. An admin reopens one report while its request is in Client Review.

**Exit criteria:** a draft PDF is ready within 10 minutes of sync; a finalized report locks the visit; a failed render returns the report to draft with the visit unlocked; client acceptance closes the request; reopening a report in Client Review returns the request to In progress; the day-30 auto-close and its close-out report work under a clock override.

## Phase 7 · Summaries and hardening (W19–W20)

**Goal:** management reporting is in place and production is ready to run. User acceptance testing moves to Phase 8, so this phase is 2 weeks instead of the PRD's 3.

**Deliverables**

- **Summary reports:** PDF from report-worker with ApexCharts rendered in headless Chromium, CSV for tabular reports, and the client-run versions (SUM-3).
- **Dashboards:** admin, technician and client dashboards, including the calibration-due and failed-calibration widgets.
- **Audit:** the viewer with search and CSV export, the integrity check, and the staff-only History tab.
- **Production stack:** `compose.prod.yml` on the production host, with Prometheus, Grafana, Loki, Alloy and exporters, and the alerts in TRD §16.5.
- **Backups:** nightly `mongodump`, continuous `weed filer.sync` to the second host with a nightly `rclone check`, and the first restore test.
- **Security review:** the TRD §15 checklist, Trivy and dependency audit, an org-scoping test run as a client of another organization, and a nightly OWASP ZAP baseline scan of staging.
- **Load test:** Locust with 50 concurrent users and 20 simultaneous video uploads, plus a 1-hour soak.
- **Continuous checks (TP):** the restore test becomes a weekly job with the audit chain check; every TRD §16.5 alert is fired once on staging.

**Weekly milestones**

| Week | Milestone |
|---|---|
| W19 | Summary reports and CSV. Dashboards. Audit viewer, History tab and integrity check. J10 works. |
| W20 | Production stack with monitoring and alerts. Backups and a restore test into staging. Security review. Load test. |

**Delivers:** SUM-1 to SUM-6, AUD-4 to AUD-6, CAL-4 (widget), CAL-6 (dashboard), and the NFR-2, NFR-3 and NFR-9 checks. Journey J10.

**Depends on:** Phases 1–6; production host ready since Phase 0.

**Staging release 0.7:** admins and a Viewer run summary reports for real stations and check the dashboards against what they know.

**Exit criteria:** production runs with monitoring and test alerts delivered; a restore into staging passes the audit chain check; no open high or critical security findings; the load test meets NFR-2.

## Buffer (W21–W22)

Two weeks of slack, about 10% of the build, held at the end rather than spread across phases. Weekly slips over 3 days draw it down. If it is unused, Phase 8 starts early, or RPT-11 and deferred **S** requirements are built.

## Phase 8 · Pilot, data import and go-live (W23–W25)

**Goal:** two client organizations and two technicians use AWS-MMS for real work on production, the PRD launch criteria are met, and the remaining clients are invited.

**Deliverables**

- **Production data:** final import of stations, sensor units and calibration history; client organizations and staff accounts created; request categories loaded; final branding applied.
- **Training:** one session each for admins and technicians (including the PIN unlock and station ownership), a one-page quick reference per role, and a short client guide sent with the invitation email.
- **Pilot (UAT):** the pilot clients and technicians run real requests through J1–J10. Defects are triaged daily, and critical and high defects are fixed before go/no-go.
- **Go-live:** go/no-go meeting, invitations to the remaining clients (AUTH-6), and an announcement.

**Weekly milestones**

| Week | Milestone |
|---|---|
| W23 | Production import and setup. Training sessions. Pilot users invited. |
| W24 | Pilot: real requests, visits and sign-offs. Daily triage and fix releases. |
| W25 | Remaining fixes. Go/no-go against the launch criteria. Remaining clients invited. |

**Launch criteria (PRD §8)**

- [ ] Every **M** requirement is done
- [ ] A full visit recorded offline on a real Android and iOS device synced with no loss
- [ ] Restore from backup tested
- [ ] Audit integrity check passes
- [ ] UAT passed with at least two client organizations and two technicians

**Hypercare (W26–W27, after launch):** daily review of alerts, dead-letter topics, sync conflicts and stuck finalizations, with a weekly fix release. After that, work moves to the later-release backlog (PRD §10).

## Critical path and decision deadlines

Every phase is on the critical path. With one developer, phases run one after another and each builds on the one before: requests need stations, visits need requests, offline needs online visits, reports need synced visits. The only parallel work is the organization's, so its inputs are what can delay the plan. Each input below is due at the start of the week that needs it.

| ID | Decision or input | Owner | Needed by | Blocks |
|---|---|---|---|---|
| T1, T2, T5, T6, T8 | Outbound internet, Git and registry, single-node Mongo/Kafka, domains and TLS, host RAM | Organization IT | W1 | Phase 1 |
| T7 | SeaweedFS confirmed by the spike (**confirmed 2026-10-16**; Garage stays the fallback) | Developer | W1 | Phase 1 |
| B1 | Disk encryption on both hosts | Organization IT | W1 | Host build |
| A1–A6, A8 | App Flow defaults (routes, queue page, landings, field layout) | Product owner | W1 sign-off | Frontend from W4 |
| T3 | SMTP relay and sending domain (SPF, DKIM, DMARC) (**interim 2026-10-17:** a Gmail account for staff-only staging, so W4 no longer waits on it; TRD §22) | Organization IT | W4 → before the Phase 8 pilot | Phase 3 notification volume; client email in the pilot |
| T4, Q4 | Station and sensor export; countries and time zones | Product owner | W5 | Phase 2 import |
| Q7 | Default document visibility | Product owner | W5 | Phase 2 · **decided 2026-10-19: staff-only** |
| Q6 | Request categories and priority definitions | Product owner | W8 | Phase 3 |
| Q5 | *Closed 2026-10-22: checklist templates removed (W11-16)* | — | — | — |
| — | Test iPhone and Android phone; one day of two technicians for the field test | Product owner | W13 (devices), W15 (field day) | Phase 5 |
| Q1, D1, D5 | Branding, logo, report numbering, login photo | Product owner | W16 | Phase 6 PDFs |
| Q2, Q3 | Signature attestation wording; jurisdictions accept a simple e-signature (R5) | Product owner, legal | W16 | Phase 6 |
| — | Two pilot client organizations and two technicians named | Product owner | W21 | Phase 8 |

B2, B3 and B4 were closed in BSD 1.1, and B5 and B6 were decided on 2026-10-16.

If an input is late, the developer moves on to work that does not need it, such as tests, screens on seed data, or the next phase's service skeleton. That is cheaper than waiting, but each switch costs time, so a late input is recorded at the weekly checkpoint.

## Checkpoints, quality gates and schedule risks

The riskiest technical assumptions are each tested in the first days of the phase that relies on them, not at its end.

### Early checkpoints

| Week | Checkpoint | Risk it retires |
|---|---|---|
| W1 | SeaweedFS spike: presigned multipart upload from a browser through the `files.` host | The S3 store (R6) before anything depends on it |
| W2 | One event goes through the outbox (leader lease) and Kafka and lands in the audit chain; killing the leader hands over within 10 s | The event backbone (ADR-3, ADR-13) works before four more services rely on it |
| W5 | First import of the real station export | Bad source data (T4) found while there is time to clean it |
| W7 | A printed label is scanned by an iPhone and an Android camera | QR flow (QR-2) on real devices |
| W11 | A 2-minute phone video is processed on the staging host | Media-worker time and memory (R7, R8) |
| W13 | 50 photos and 3 videos stored offline on an iPhone, then the phone is restarted and the PIN unlocks them | iOS storage eviction (R4) and the offline session, two weeks before the field test |
| W16 | Q3 answered in writing; backfill builds the report read model from staging data | E-signature acceptance (R5) before signing is built; read models (TRD §8.6) |
| W20 | Full restore into staging with an audit chain check | Backups (NFR-9) before real data exists |

### Phase gate

A phase closes only when:

1. Its exit criteria pass on staging.
2. Every feature in it meets the definition of done.
3. Its journeys are added to the Playwright smoke suite run on each deploy.
4. Coverage is at least 90% for `domain/` packages and 70% overall (TRD §17).
5. The tests the Test Plan assigns to the phase exist and pass, and the nightly jobs are green.
6. The product owner has seen the demo and logged feedback.
7. The developer docs site is updated for the phase, including the diagrams chosen from its suggestions.

### Schedule risks

| Risk | Early signal | Response |
|---|---|---|
| Infrastructure in Phase 1 takes longer than planned | Compose stack not running by the end of W2 | Use buffer. Keep the outbox and Kafka; defer kafka-ui. |
| SeaweedFS lacks an S3 feature the app needs | The W1 spike fails a check | Switch to Garage (the app uses only the S3 API); rely on app-level immutability (TRD §10.1) |
| Generated code drifts from the architecture | Review finds cross-service database access, or state changes outside the state machine and outbox | `CLAUDE.md` rules, contract tests, and a human review of every diff before merge |
| Station data is poor | More than 10% of rows fail the W5 import | Import the valid rows; the product owner fixes the rest by W9; work continues on seed data |
| iOS limits offline media | The W13 check loses data | Upload as soon as there is signal, require install to home screen, and lower offline video length if needed |
| E-signatures not accepted somewhere | Q3 is not a clear yes by W16 | Ship the simple signature where accepted; scope a certificate (PAdES) signature at finalize as a separate estimate |
| The developer is unavailable | Any absence over 2 days | Draw on the buffer; move the go-live date rather than cut **M** scope |
| Staging demos add scope | New requests after a demo | New items go to the backlog; the product owner trades them against **S** items |

## Open questions

| # | Question | Assumption until decided |
|---|---|---|
| P1 | What is the start date, and which holidays or leave fall in the 25 weeks? | Relative weeks; dates added once W1 is fixed |
| P2 | Who is the product owner, and can they give about 2 hours per phase plus the Phase 0 and Phase 8 meetings, and approve screen mock-ups as they come? | An admin from the organization, named in Phase 0 |
| P3 | Does the pilot run on production, so pilot data is kept? | Yes; pilot organizations keep their records after go-live |
| P4 | Are all remaining client organizations invited on go-live day, or in waves? | All at once in W25; there are about 200 users |
| P5 | Should notification email move to Phase 1 as planned here? | **Decided:** yes. Account email comes with platform in Phase 1; TRD §20 and PRD §8 point to this plan |
