# W23 plan: production setup, training and pilot invitations (Phase 8, week 1)

Date: 2026-11-13. W23 is the first week of Phase 8 (IP.md, "Phase 8 · Pilot, data import and go-live", W23 to W25). The IP's milestone for this week is: **production import and setup, training sessions, pilot users invited.** Release 0.8.0 (W22, two-step sign-in for admins) is on staging and its API check passed on 2026-11-12.

## The headline: W23 waits on a host

**There is no production host yet.** W20 defined the production stack (`infra/compose.production.yml`, limits totalling 18.9 GB, `production.yml` with approval and rollback by tag). It has never run, because the host, the backup host, the backup key holder, the alert recipients and the `production` environment's reviewers in GitHub are all still with people (W20 and W21 plans). Neither "Production import and setup" nor inviting pilot users on production (P3: the pilot runs on production) can happen until the host exists.

So this plan splits each slice into **needs the host** and **can be done now**. The developer work that needs nobody fills W23. Everything that needs the host is ready to run in under a day once the host is handed over.

## Answers so far

| Question | Answer |
|---|---|
| Does the pilot run on production? (P3) | Default **yes**: pilot organizations keep their records after go-live. |
| Remaining clients invited all at once? (P4) | Default **all at once in W25** (about 200 users). |
| Pilot organizations and technicians named (IP, due W21) | **Not answered yet.** Question 2 below. |

## Questions for the product owner and IT (defaults in bold)

1. **Production host and backup host.** When are they handed over (8 vCPU, 32 GB, disk encryption B1; a backup host with its own disk)? Who holds the backup key, who gets alerts, and who are the `production` environment's reviewers? Default: **the go-live date moves one day for each day after W23 Wednesday that the host arrives.** W24's pilot cannot start without it.
2. **Pilot organizations and technicians.** Which two client organizations, which contacts there (one client admin each is enough to start), and which two technicians? Default: none. This blocks the invitations and the device checks.
3. **Email for clients (T3).** Pilot clients get real email. The Gmail interim sender is for staff-only staging. Is the SMTP relay with SPF, DKIM and DMARC on the sending domain ready **before the first invitation**? Default: **no client is invited until a test email to an outside mailbox passes SPF and DKIM** (Gmail's "Show original").
4. **Calibration history.** `import-stations` takes the last calibration date and the intervals, not a history. Does the existing system hold more than the last date? Default: **last date only**. Older certificates can be added as documents by staff later.
5. **Request categories and priorities (Q6).** They are fixed in code (REQ-1: Fault, Communications, Power, Calibration, Relocation, Inspection, Other; Low to Urgent). Default: **keep them**, so "categories loaded" is nothing to do. A change is a small code change and a release, not data.
6. **Staging's Mongo feature compatibility version.** A fresh production mongod 9.0.8 starts at FCV 9.0; staging is held at 8.0 on purpose (W21). Backups are logical dumps (`mongodump --oplog`), which normally restore into a server on a lower FCV, but **this has not been tried**, and "restore from backup tested" is a launch criterion. Default: **the first production backup is restored into staging as it is; if that fails on the FCV, staging's FCV is raised to 9.0** (after a staging backup and a restore drill pass at 8.0, W21's conditions, and with the product owner's go-ahead). `readiness.sh --on-host` prints the FCV of the host it runs on.
7. **Charts for Phase 8** (CLAUDE.md asks for a proposal at each phase start). Proposed: **hypercare workflow** (triage, fix release, rollback), **client onboarding customer journey** (invited, first sign-in, first request, sign-off), **go-live gantt** (W23 to W27 with the inputs above as milestones). Default: all three.
8. **The pilot devices.** Default: **the pilot technicians' own phones, with at least one iPhone and one Android phone**. If neither technician has an iPhone, the organization lends one for W23 and W24. The launch criterion needs both.

## Goal

By the end of W23 (or the day after the host arrives, if later):

- production runs release 0.8.x, with the first admin enrolled in two-step sign-in, real organizations, stations and sensors imported from a fresh export, and backups running;
- the device checks that have been put off since W6 are done on the pilot technicians' own phones, iPhone included;
- the quick references and the client guide exist, and the training sessions have been held;
- the pilot users are invited, and a triage routine is ready for W24.

## PWA pre-flight

| Question | Answer |
|---|---|
| Device | The pilot runs on the technicians' **own** phones. The iPhone checks were postponed by choice (Phase 1 install, F15, W7 label scan, W13 unlock, W14 sync, W17/W18 signatures, W22 code autofill) and the launch criterion needs an offline visit on a real iPhone. W23 is the last week those checks can move to: they run **before** the training session, because training is installing the app and setting a PIN on those same phones. |
| Network | No app change. Production gets the same Nginx, CSP and `no-cache` headers as staging (`infra/tests/test_production_config.py`). |
| Lifecycle | Production starts from release 0.8.x. Phones installed from staging are a different origin and keep their own storage: a technician who used staging must **sync everything there first**, then install the production app. Training says so. Fix releases in W24 use the update prompt (F19 fixed), never a silent reload; the version comes from `frontend/package.json`, never a commit SHA. |
| Data loss | Nothing queued on staging moves to production. The device check proves an offline visit syncs with no loss on both platforms, by counts (`field-test-report`). |
| Storage | Diagnostics on each pilot phone: OS and browser version, installed, `persisted()`, free quota (`/sync` › This phone › Copy report). Noted in a private sheet, not in the repo. |
| Caching, CSP | No change. |
| Security, shared devices | Training covers: a phone passcode is required, the offline PIN, sign out on a shared phone. Admins enrol in two-step sign-in in their first 7 days. `AUTH_TOTP_KEY` and every other secret are new on production, never copied from staging. |
| Proof | Production: `@smoke` after the deploy, `verify-audit`, a first backup and its restore into a scratch stack. Devices: the W15 runbook (`docs/field-test.md`) on both platforms with counts. |

## Decisions (W23-1 to W23-7, proposed)

- **W23-1 Production is set up from scratch, not copied from staging.** A fresh `mongoexport` of `entities` and `sites` from the existing system (data has moved since 2026-10-18), imported with `import-orgs` then `import-stations` (dry run, then `--commit`). No `seed`, `seed-requests` or test users on production (each already refuses production). The files are deleted from the host and the containers afterwards, as on staging (W5-9).
- **W23-2 A production runbook in the docs site**, under Infrastructure › Production, mirroring Staging: host preparation, the full `.env` list (every key in `.env.example`, including `AUTH_TOTP_KEY`, `MEDIA_SCAN_MODE=clamd`, `REPORT_APP_URL`), DNS and TLS for the app and files hosts, the GitHub `production` environment, the first deploy with `production.yml`, `create-admin`, the first admin's two-step enrolment, branding, the import, the first backup and restore, and the checks. A step that needs a person names them.
- **W23-3 A readiness check script**, `infra/scripts/readiness.sh URL`, that can run against staging now and production later: version on the public pages, `@smoke`, security headers and CSP, `/health` of every service through the gateway's checks, no `/docs` in production, the audit chain verified, the age of the last backup. It prints pass or fail per line and nothing private (the repo is public).
- **W23-4 One device checklist for everything that was put off.** `docs/device-check.md` gathers the open real-phone items from W6 to W22 into one run per phone (install, offline shell, PIN unlock, prepare, offline visit with photo and video, sync counts, label scan with the camera app and in the app, signature, the update prompt, the code autofill for an admin). It runs on staging (release 0.8) in W23, before the phones are moved to production at training.
- **W23-5 Training material in the repo, in plain words.** `docs/guides/`: a one-page quick reference for admins, one for technicians (install on iPhone and Android, PIN, station ownership, keep the app open while syncing, what "Needs attention" means), and a short client guide. The client guide is a page the app serves (`/help/client`, public, not precached: it is read with a connection), and the invitation email links to it, because account emails are templates in platform and a link keeps them short. Microcopy follows DBD's "Voice and microcopy" (`writing-guidelines`).
- **W23-6 Pilot triage routine.** A GitHub issue form for pilot defects (what happened, role, phone and version, the request or visit reference, no client names: the repo is public), labels `pilot`, `severity:critical|high|medium|low`, milestone P8, a daily triage at a fixed time, and the fix-release routine (bump the version, merge, staging, `@smoke`, then `production.yml` with approval; rollback by tag through the rollback guard). Critical and high defects are fixed before go/no-go (IP).
- **W23-7 Invitations go out from production only, in a set order.** Pilot staff first (they check their own sign-in and two-step), then the pilot clients' admins, after question 3's email test passes. The pilot client organizations are created by `import-orgs`; the invitation (AUTH-6) links the person to the organization.

## Slices

1. **Can be done now: the runbook and readiness check** (`docs/w23-production-runbook`). W23-2 in the docs site, `infra/scripts/readiness.sh` with a test in `infra/tests`, run against staging, the three Phase 8 charts if chosen.
2. **Can be done now: the device checklist** (W23-4). Written now, run on the pilot phones as soon as question 2 names the technicians. Results in a private sheet; only pass or fail and the OS versions go in `docs/checks/`.
3. **Can be done now: training material and the client guide** (W23-5). The guides, the `/help/client` page (a mock-up first, CLAUDE.md UI workflow), the link in the invitation email. Training sessions are booked once question 2 is answered.
4. **Can be done now: the triage routine** (W23-6). Issue form, labels, the routine in the docs site and in CLAUDE.md.
5. **Needs the host: production up** (W23-1, W23-7). Follow the runbook: deploy, admin, two-step, branding, import, backup and restore, readiness check, then invitations. Record the result in `docs/checks/` and the IP.

## Status (2026-11-13)

Plan written; questions 1 to 8 open. Slices 1 to 4 can start at once on their defaults.

**Slice 1 is built** on `feat/p8-w23-runbook` (2026-11-13): the docs site's Infrastructure › Production, day one (fourteen steps, each with a person; charts: from an empty host to the first invitation, and W23 to go-live), `infra/scripts/readiness.sh` and `infra/tests/test_readiness.py` (33 tests, no stack needed). The outside mode ran against staging: 34 passed, 0 failed (release 0.8.0). The host mode is tested with a made-up host only.

Where the build differs from the text above:

- **The readiness check has two modes.** From outside (curl, GET only) and `--on-host` (the `.env`, the containers, the audit chain, the backups). The backup age and the audit chain cannot be seen from outside, so they are in the host mode.
- **The load run comes before the first admin**, on the empty host, and the data is wiped after it (W20-11): it is step 3 of the runbook, not a W24 item.
- **Labels are printed again from production** (step 8): a label holds the site's address and a token the import makes anew.
- **Of question 7's three charts, the go-live gantt is in** (with the day-one flow, which was not on the list). The hypercare workflow goes in with the triage routine (slice 4) and the client onboarding journey with the client guide (slice 3), where their content is decided.
