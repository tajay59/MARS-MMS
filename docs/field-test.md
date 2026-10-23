# Field test runbook (Phase 5, W15)

For the people running the field test: the admin at a desk, and the technicians in the field. Plan and reasons: [plans/W15-plan.md](plans/W15-plan.md). The test passes on **counts**, not on how it felt: what the phone says it recorded must be what the server holds, once, after the sync, and the same after a second sync.

**This repo is public.** Fill the result sheet in a private note or message, not in this file. Station names, people and phone details stay out of git.

## 0. What is being tested

Release **0.5.0** on staging (`https://rnd.yanacreations.com`), on **Android** phones (there is no iPhone: Phase 5 is not formally closed until an iPhone run, see plan decision 6). "No signal" is **airplane mode**.

The visits are on **real stations** whose organizations have no client users on staging, so nobody outside the team is emailed. What stays on a real station afterwards: the visit, its notes, photos and recommendations (staff only, nothing shared), and the `[Field test]` request, which is cancelled at the end. **Do not put an After file on a Config element**: it would become a permanent configuration version.

## 1. Admin setup (a week before, with signal)

1. Check the build: the public pages show `Version 0.5.0`.
2. Check the people: each technician has a staff account on staging and has logged in once. (An admin can also attend a visit, so the admin account can stand in for a second technician.)
3. Make **two requests**, each covering **two** of the four stations (a visit belongs to one request, and a request can cover several stations): as an admin, **New request**, title `[Field test] <first station code> and <second station code>`, category inspection, no attachments. Approve each, then **Assign** it to one technician. The admin account can stand in as the second technician.
4. The technician (or you) **Schedules** the visit from each request, with both stations, for the field day. Add the admin as an attendee of each visit: S6 needs someone else to hand a station to.
5. Print the four stations' labels from **Admin › Station tools** and fix them where the technicians will scan them (any surface; the scan does not need the real station).
6. Write down the request and visit references (`MR-…`, `VR-…`).

## 2. Each technician, the day before (with signal)

1. Open `https://rnd.yanacreations.com` in Chrome on the phone. Install the app (the Install card on the dashboard, or the browser menu).
2. Open it **from the home screen**, log in, set the offline PIN (My profile › Offline PIN).
3. Open the visit › **Prepare for field**. Wait for *Ready offline*.
4. Open **Me › Sync › This phone**. Check: installed, works with no signal *Yes*, data kept by the browser, prepared visits `1`. Tap **Copy report** and send it to the admin (result sheet row S1).
5. Put the phone in airplane mode, close the app, open it again, unlock with the PIN. If any step fails, stop and send the report.

## 3. The field day

Work through the scenarios in order on each phone. After each one, write **pass / fail** and the numbers in the result sheet. A technician says out loud what they recorded (counts of notes, tasks, photos, videos) before syncing, so the admin can compare.

| # | Do | Pass when |
|---|---|---|
| S1 | Install and prepare (section 2). Note `persisted` and the storage numbers from **Copy report** | Ready offline; report sent |
| S2 | Airplane mode on. **Scan** a printed label with the in-app scanner | The prepared station opens; its configuration file opens |
| S3 | Start the visit. **Arrive** at both stations. At one: a Note, a Task with a Before photo, a Recommendation, a Config element with a **Before** file only, 10 photos, one 1 to 2 minute video. **Depart** | Everything shows *On phone / Not saved yet*; the count on **Sync** matches what was said |
| S4 | Switch the phone off and on. Open the app from the home screen. Unlock with the PIN | All of S3's work is still there; the PIN worked with no signal |
| S5 | Airplane mode off. Tap **Sync now**. While it uploads, lock the screen for 30 seconds, then unlock | The upload carries on; no file appears twice |
| S6 | Before S7, with the phone still offline: the admin **Change owner** on the second station to another person. The technician records a note on that station | After sync, that station's work is under **Needs attention** (not yours any more); **Export** works and the file opens; the server's station is unchanged |
| S7 | **End visit** (offline), then airplane mode off | The visit is ended once on the server; the phone holds nothing for it |
| S8 | Open **Sync** and tap **Sync now** again. Then log out, log in and sync again | Nothing changes: the same counts on the server |
| S9 | (Optional) the admin deploys 0.5.1 while the phone holds unsynced work | The update prompt appears and is not applied during a capture or sync; the old work still syncs |
| S10 | The technician logs out; a second person logs in on that phone | Nothing of the first person shows; their waiting work is there when they log back in |

Order notes: S6 needs the admin to act *while the technician is offline* (between S3 and S7), so agree the moment by message. S10 comes last.

## 4. After each scenario set: the server's side

The admin runs, on the staging host:

```sh
ssh kw-server "docker exec mms-operations-1 python -m app.cli field-test-report"
```

(`--visit <id>` for one visit, `--prefix "[Field test]"` is the default.) It prints for each visit: state, each station's arrive and depart, elements by kind, deleted ones, files on boards, sync operations by type, the devices that sent them, and **Check:** anything odd. Exit code 1 means it found something. Compare against what the technician said they recorded and the phone's report.

Pass conditions in numbers (the phone's counts are in **Copy report** and on **Sync**):

- elements and files on the server = what was recorded (minus anything deleted on purpose);
- each file once (`Check` is empty);
- after S8, the report is **identical** to the one after S7;
- S6: the second station's elements are unchanged, and the phone's report shows `1 conflicts`.

## 5. Result sheet (copy into a private note)

| Scenario | Phone | Pass / fail | Numbers (waiting, applied, report text) | Notes |
|---|---|---|---|---|
| S1 | | | persisted; used / quota | |
| S2 | | | | |
| S3 | | | notes / tasks / recs / photos / videos | |
| S4 | | | | |
| S5 | | | files before / after | |
| S6 | | | | |
| S7 | | | server counts | |
| S8 | | | server counts (same?) | |
| S9 | | | | |
| S10 | | | | |

For a failure: scenario, phone, what happened, the **Copy report** text from before and after, and whether anything was **lost or duplicated** (that is the first thing fixed).

## 6. Afterwards

1. Cancel the four `[Field test]` requests (Requests › the request › Cancel, reason "Field test"). Nobody is notified: no client users exist for these organizations.
2. Each technician: **Sync** shows nothing waiting; log out.
3. Write the measured numbers into `.claude/skills/pwa/references/findings.md` (F3 storage, F12 background upload, F14 install time) and the docs site changelog.

## 7. Kill switch test (once, on staging, before the field day)

What it does: a build that replaces the service worker with one that unregisters itself and clears the caches, and an app that does not register it again. The phone's recorded work (Dexie `outbox`, `blobs`, prepared visits) is **not touched**. It reloads open pages once. Last resort for a broken worker that a fix-forward release cannot reach.

1. On a phone with the app installed and some waiting work (a note recorded offline), open **Me › Sync › This phone › Copy report**: keep it (`Waiting: N changes`).
2. On this PC: `cd frontend && npm run build:kill` (output `dist-kill/`).
3. Copy it in and replace the served files:
   ```sh
   tar -C frontend/dist-kill -cf - . | ssh kw-server "docker exec -i mms-nginx-1 tar -C /usr/share/nginx/html -xf -"
   ```
4. On the phone, open the app (online). Within a minute it reloads once. Then **Copy report**: `Service worker in control: no`, `Caches: none`, and **`Waiting` is unchanged**. Chrome › Site settings or the report shows no worker.
5. Restore: on the host, `cd /opt/mms/infra && docker compose -f compose.yml -f compose.prod.yml -f compose.staging.yml up -d --force-recreate nginx` (the image still holds the normal build). The phone registers the normal worker on its next open; **Copy report** shows `Service worker in control: yes` after the second open.
6. Write the result in the sheet.

Production runbook (Phase 7): the same build, shipped as a release with `npm run build:kill` in place of `build-only`, and the steps above to verify.
