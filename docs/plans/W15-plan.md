# Phase 5 · W15 plan: the field test on real phones

Proposed 2026-10-23, after W14 (#79 to #83 merged to `main`; the release run for #83 was still going when this was written). Questions are in section 8; three were answered 2026-10-23 (no iPhone, real stations, airplane mode) and this plan is updated for them.

W15 is the last week of Phase 5 and it is mostly **people and phones**, not code. Its job is to prove the IP exit criterion on both platforms: *a full visit is recorded offline on both iOS and Android, including a phone restart mid-visit and PIN unlock, then synced on return with no lost or duplicated records or files. Syncing the same visit twice changes nothing. Work for a station whose owner changed while offline comes back as a conflict and can be exported.* Claude Code cannot run the field test; it prepares everything the day depends on, writes down what happens, and fixes what breaks.

Delivers: the Phase 5 exit criteria (OFF-1 to OFF-11, AUTH-12, QR-5 offline, CFG-4 offline, journeys J5 and J6 on real hardware), **staging release 0.5**, the kill switch tested once on staging (pwa skill: "before closing" Phase 5), and the findings the day produces (F2, F3, F6, F12, F15 closed or reopened with evidence).

**Not in W15:** Background Sync (still question 3 of W14: no), reports (Phase 6), editing a visit's plan offline (OFF-10), the pilot's second field test (Phase 8).

## 1. Where things stand (checked 2026-10-23)

- **Built, Chromium-proven:** the PIN session and `/unlock`, Prepare for field, offline station lookup, the install card, the storage check, the outbox and runner, `POST /api/v1/sync`, the local-first board, `/sync` with Needs attention and Export, the three dialog warnings. Playwright J6 (`e2e/offlineVisit.spec.ts`), `e2e/syncConflict.spec.ts` and the Dexie/runner fault tests pass in Chromium. WebKit covers only the primitives (F6).
- **Never run on a real phone:** everything above except the Phase 1 shell and update prompt (Android, 2026-10-18). The W13 Android check (install, prepare, airplane mode, restart, unlock, scan, storage check with 50 photos and 3 videos) is **still open**, and so are all iPhone checks (Phase 1, W6 F15, W7 scan, W13). The user postponed the iPhone checks by choice (2026-10-20); the W13 plan said they must be done "at the latest W15, because the field test depends on it". They are now on the critical path for the exit criterion.
- **Not built:** the kill switch (`selfDestroying` build), a sync log for bug reports, the version bump to 0.5, any field-test data or runbook. The package version is still `0.1.0`.
- **Open findings that the day settles:** F2 (iPhone in a Safari tab: install steps), F3 (browser may clear data: `persist()` result on iOS), F6 (Playwright cannot prove iOS), F12 (JavaScript stops in the background: does an upload resume after the screen locks), F15 (CORS preflight and 8 MiB XHR PUTs from the installed iPhone app), F14 (first install time on the iPhone).

## 2. Order of work

Four steps. Steps 1 and 2 are code on the usual branch and pull-request flow; step 3 is the human part; step 4 is whatever step 3 breaks.

| Step | Branch | What | Who |
|---|---|---|---|
| 1 | `feat/p5-w15-field-support` | **Built:** the kill switch, the sync log and "Copy report", release 0.5.0, `field-test-report`, the runbook and result sheet; docs site | Claude |
| 2 | (staging) | Deploy 0.5; test the kill switch on staging; the Android rehearsal (W13 check, then J6 alone, with the developer) | You, Claude on call |
| 3 | (field) | The field day: both phones, two technicians, a no-signal area, scenarios S1 to S9 (section 5) | Technicians and you |
| 4 | `fix/p5-w15-*` | Fixes, one pull request each, retest of the scenario that failed; findings updated; close Phase 5 | Claude |

Do the Android rehearsal and the iPhone install a few days **before** the field day: a bug that shows up with two technicians waiting costs the day.

## 3. Decisions (proposed W15-1 to W15-8)

1. **The field test runs on staging, on real stations** (answered 2026-10-23: no test organization). Four real stations from the staging import carry two visits, set up **in the app by an admin** (two requests titled `[Field test] …`, each covering two stations, assigned and scheduled: J4 and J5 on real screens). *Changed during step 1:* the plan first had a `seed-field-test` command; it was dropped because writing requests and visits to the database by hand would skip the domain state machine and the outbox (rule 2), and the real path is also part of what is being tested. **What stays on a real station afterwards, and the safeguards:**
   - *Configuration versions* are permanent (immutable, TRD): scenario S3 therefore **does not put an After file on the Config element** on a real station (Before only, or a Config element with no file). The Config-to-version path stays proven by Chromium J6 and by the Phase 4 staging check.
   - *Notes, photos, recommendations* stay staff-only: nothing is shared, so a client sees none of it (rule 6: files start `visibility = staff`; clients see only shared elements of ended visits, and `end` shares only what was marked shared).
   - *The request* is visible to the station's client organization and its status moves (Submitted, Assigned, In progress…) and a cancel tells the client. **Safeguard: pick stations whose organization has no client users on staging.** Checked on 2026-10-23 (a read-only query of auth): staging has three accounts (one admin, one technician, one client), and the one client belongs to a separate "CIMH" organization that owns no station; **all eight imported organizations have no client user**, so no one outside the team can be notified by any of the 50 stations.
   - The labels are printed from the label tool for these stations, so the QR scan is part of the test.
2. **Release 0.5 is the build under test.** `frontend/package.json` goes to `0.5.0` in the step 1 pull request (the version prompt is how the app tells a phone it changed; no commit SHA, per the existing gotcha). Both phones install **that** build before the day and are not updated during it, except on purpose (scenario S9).
3. **The kill switch is a second build, not a flag.** `npm run build:kill` (`vite build --mode kill --outDir dist-kill`) sets `selfDestroying: true`; the output is `sw.js` at the same path, and `usePwa` does nothing in that mode. *Found while building it:* copying only the new `sw.js` would loop, because the deployed app registers the worker again on every start and the self-destroying worker reloads the page when it unregisters; the whole `dist-kill` is shipped, whose app never registers. CI builds it once and checks the worker unregisters and holds no Workbox code (not deployed). Ship path for the staging test: copy `dist-kill` over the served files in the Nginx container; restore by recreating that container (`docs/field-test.md` §7). Tested once on staging in step 2: after it, the app still opens online, `navigator.serviceWorker.controller` is null, and **Dexie `outbox` and `blobs` still hold their rows** (the test counts them before and after). Then the normal build is redeployed and the worker returns.
4. **A sync log for the day.** `offline/syncLog.ts` keeps the last 100 runner events (time, trigger, outcome, counts, error code, never content or tokens) in `meta`, per user, and `/sync` › This phone gets **Copy report**: version, platform, display mode, worker state, `persisted()`, `estimate()`, queue counts, PIN state, and the log, as text the technician pastes into a message. This is the "no Mac" debugging path (ios-safari.md §4) and the evidence for the result sheet.
5. **Scenarios are written before the day**, each with a pass condition that is a **count on the server and the phone** (records and files), not a feeling: `docs/field-test.md` (runbook) and a result sheet (a table in the same file, filled in by hand and copied into the docs site changelog). The server side of each count comes from a read-only command, `python -m app.cli field-test-report`, run on the staging host after sync: elements by kind, files on boards, sync operations and devices per visit, with a file attached twice, an element with no author and an unanswered operation listed under *Check*. (Media's own file records and the audit chain are other services' databases: they are looked at through media's status route and the audit screen, not this report.)
6. **Pass means both platforms, and there is no iPhone** (answered 2026-10-23). So W15 runs **Android only**, with both technicians on Android phones if two are available, and the result is recorded as "Android passed; iOS not tested". Phase 5's exit criterion is **not met** until an iPhone run happens: it stays an open item on the IP (a named blocker to close Phase 5 formally, due before the Phase 8 pilot and before any iPhone technician uses the app), alongside the deferred Phase 1, W6 (F15), W7 and W13 iPhone checks. Phase 6 can start. Because WebKit under Playwright (F6) covers only the primitives, the iOS-specific risks (HEIC/HEVC capture, quota and eviction, JavaScript suspended in the background, F15's CORS and XHR PUTs) stay **unproven**; the docs site and the pwa skill's findings say so plainly.
7. **Fixes are found-on-the-day only.** No feature work in W15. A failure becomes an issue with the scenario, the phone, the report text and, if it loses or duplicates data, the priority above everything else (PRD §8: zero lost or duplicated).
8. **Findings are closed with evidence.** F2, F3, F12, F14, F15 each get the measured result (numbers from Copy report) written into `findings.md` and the TRD where a number or limit changed (for example the iOS `estimate()` quota, the first-install time, the largest video that uploaded).

## 4. Code and docs in step 1

| Piece | Where |
|---|---|
| Kill switch build | `frontend/vite.config.mts` (a `selfDestroying` mode), `package.json` script `build:kill`, `release.yml`/`frontend.yml` job that builds it once, runbook section in the docs site (Infrastructure › Releases) |
| Sync log | `frontend/src/offline/syncLog.ts` (no Vue), called by `runSync` and the upload path; Vitest (bounded to 100, per user, no content, survives logout like `outbox`) |
| Copy report | `features/field/DiagnosticsCard.vue` and `offline/report.ts` (builds the text; `navigator.clipboard` with a select-all fallback for iOS in a non-secure gesture) |
| Version | `frontend/package.json` to 0.5.0; the public pages show `Version 0.5.0` (decision W4-17) |
| Field-test data | none in code: requests and visits are made in the app by an admin (decision 1); the technicians are real staff accounts on staging |
| Server report | `services/operations/app/jobs/field_report.py` and `python -m app.cli field-test-report` (read-only; runs in the `operations` container; replaces the planned `infra/scripts/field_test_report.py`, because it must read operations' own database and the CLI already has the connection) |
| Runbook | `docs/field-test.md` (before, scenarios, after, result sheet) |
| Docs site | Status: Phase 5 field test; decisions W15-1 to W15-8; changelog; charts (below) |

No new precache file is expected (the budget is 29 of 30): the log and report join the `app` chunk. If the kill-switch build changes the precache list it is not the deployed build, so the `offline.spec.ts` limit does not apply to it.

## 5. The field day: scenarios

Two technicians (T1 and T2) on **Android phones** (no iPhone: decision 6), each with their own staff account and PIN. If only one Android phone is available, one technician runs it and the second account is used only for S6 and S10. Each phone installs release 0.5 from `https://rnd.yanacreations.com` the day before and prepares one visit with signal. **Offline is airplane mode** (answered 2026-10-23), so a connection that drops mid-request is covered only by the Vitest and Playwright fault tests, not by the day. An admin (you) is at a desk with signal.

Each visit has two stations; each technician owns one of the two stations on the *other* technician's visit too, so the owner-change case can be run on a different phone from the main one.

| # | Scenario | Pass condition |
|---|---|---|
| S1 | **Install and prepare** with signal: install, log in, set PIN, Prepare the visit, see Ready offline. Record `persisted()`, `estimate()` and the install time | Ready offline; numbers in the result sheet |
| S2 | **Go to the site, lose signal** (airplane mode or a real dead area). Scan the station label with the in-app scanner | The prepared station opens; its configuration file opens |
| S3 | **A full visit with no signal:** Start, Arrive, a Note, a Task with Before and After photos, a Recommendation, a Config element (Before file only; no After file on a real station, decision 1), 10 photos, one 1- to 2-minute video, Depart | Everything shown "Not saved yet / On phone"; the waiting count matches |
| S4 | **Restart mid-visit:** switch the phone off and on, open the app from the Home Screen, unlock with the PIN | All S3 work still there; nothing lost; the PIN unlock worked with no signal |
| S5 | **Lock the screen during a sync/upload** (once signal is back, start Sync now, lock the phone for 30 s, unlock) | Upload resumes; no duplicate file (F12, F15) |
| S6 | **Owner change while offline:** the admin gives T's second station to someone else while the phone is still offline; T records work for it | After sync: that station's work is a conflict (`not_owner`), the rest of the visit synced; Export works and the file opens; the server's station is unchanged |
| S7 | **End the visit and sync on return:** End visit offline, signal returns | The visit is ended once on the server; the phone holds no bundle, files or blobs for it (OFF-8); `field_test_report.py` shows the counts equal the phone's count before sync |
| S8 | **Sync twice:** open `/sync`, Sync now again; then log out and in and sync again | Nothing changes: same counts, no new events, all answers `duplicate` or no ops |
| S9 | **An update during a visit (optional):** deploy 0.5.1 while the phone has unsynced work | The update prompt appears, is not applied during a capture or sync, and queued ops of version 0.5.0 sync after the update (F8) |
| S10 | **Shared phone:** T logs out; the other person logs in on the same phone | Nothing of the first is shown; the first person's queued work is still there when they log back in (not synced by the second) |

The storage load (50 photos and 3 videos) is run in step 2 by one person on each phone with the storage check, not on the field day.

## 6. PWA pre-flight (answers)

1. **Device.** The day is the iOS proof: installed app from the Home Screen, camera and photo library capture (HEIC/HEVC), no Background Sync, storage that may be cleared. Android Chrome the same flow. Desktop is not part of it.
2. **Network.** Real dead area versus airplane mode: a real area drops connections mid-request, airplane mode does not; S5 and S7 are run once each way if the site allows.
3. **Lifecycle.** A waiting worker must not apply during a visit (S9); the kill switch must leave Dexie alone (decision 3); queued ops of an older version must still sync (F8).
4. **Data and loss.** The pass conditions are counts. `field_test_report.py` compares the server with what the phone's report says it held, per visit; anything on the phone that is not on the server after "all synced" is a P0 bug.
5. **Storage.** iOS quota, `persist()` result, and how much the 50-photo, 3-video load takes are recorded and written back to the TRD.
6. **Caching.** Nothing changes; confirm in the installed app (Cache Storage inspector via the report) that no `/api/` URL is cached. The kill switch removes only the worker and its caches.
7. **Security and shared devices.** S10 covers the shared phone; the report text contains no token, PIN, user content or full device ID (first and last four characters, as in This phone).
8. **Proof.** The result sheet and the server counts. Playwright cannot stand in for the iPhone (F6); the Chromium J6 stays as the regression for what the field day proves.

## 7. Tests and exit checks

- **Vitest:** the sync log (bounds, per user, no content, kept across logout); the report text (no secrets).
- **Build:** the kill-switch build compiles in CI; its `sw.js` contains the unregister code and no Workbox code (a string check in `frontend.yml`).
- **Python:** `field-test-report` finds visits by request title, counts the board, changes nothing, and flags a file attached twice and an unanswered operation (`tests/api/test_field_report.py`).
- **Staging (step 2):** kill switch tested with counts before and after; Android rehearsal (S1 to S4, S7, S8 alone); the storage check with 50 photos and 3 videos on each phone.
- **Field day (step 3):** S1 to S10 on both phones; every row of the result sheet filled in.
- **Exit:** the IP Phase 5 criteria as in the opening paragraph, on both platforms; no open data-loss or duplicate bug; findings updated; release 0.5 stays on staging as the baseline for Phase 6.

## 8. Questions

**Answered 2026-10-23:** (1) no iPhone: Android only, Phase 5 not formally closed (decision 6); (2) real stations (decision 1); (4) airplane mode for the no-signal part (section 5); (5) the technicians' own phones, no reset between runs (S10 uses a technician's phone with a second account, logging out between); (6) yes, the day runs without other sites deploying, and the media worker's memory is checked in step 2 with a 2-minute video.

**Answered (second round):** 2b use the default (stations of an organization with no client users); 3 the technician account is the one the user named (`ui@gmail.com`; staging has `iu@gmail.com`, a technician, active, so this is taken to be a typo).

**Still open:**

- **The four stations.** Every imported organization qualifies. Proposed (the two smallest organizations, so the least history is mixed in; any can be swapped): visit one `ALFAROMEO` and `FOXTROT` (JMS, Jamaica), visit two `BELMONTESTATE` and `GRENVILLE` (GMS, Grenada). Needed for the admin setup in the runbook.
- **The second technician and the day.** Staging has one technician and one admin. Default: the admin account attends as the second person; or invite a second technician from Users. The day is not set.

## 9. Developer docs site

Status and badges (Phase 5: field test), decisions W15-1 to W15-8, the field-test runbook link, the kill-switch runbook in Infrastructure, a changelog entry with the result sheet, and the P5 charts still on the list if W14's four did not cover them: the **prepare-for-field sequence** and the **device storage data flow** (W13 and W14 charts exist; check the diagram guide before adding), plus a **process flow** of the field-day scenarios. Documents: IP (W15 row marked done with the date), TP (field-test level filled in with the results), TRD §7 and §14 (measured limits), AFD (any wording the test changes), the pwa skill's findings (F2, F3, F6, F12, F14, F15) and phase map.
