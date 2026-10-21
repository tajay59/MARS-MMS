# Phase 4 · W11 plan: work records, sensor reconciliation, photos and video

Proposed 2026-10-21, waiting for your answers (section 7) and the mock-up boards (section 4). Nothing is built.

Delivers VIS-7 (the work record), VIS-8 (the copy of the template a visit used), SEN-4 and SEN-5 (swaps update the inventory, unknown serials are created and flagged), CAL-1 (field checks), CFG-4 (online), VIS-5 and VIS-10 (media per station and phase), MED-1, MED-2, MED-4, MED-5 and MED-7 (the image and video pipeline), and the browser side of F4 (hashing a 200 MB video). Depends on W10 (merged). The IP exit check for the week: **a 2-minute phone video is processed on the staging host** (risks R7 and R8).

**Not in W11** (so it is clear where it goes): the field-shell screens where a technician fills in the work record on a phone, the VIS-6 end rule (a Before and an After image per station, or an override), the client's view of visit media and the lightbox (all W12); the lock and unlock of work records by the visit report (Phase 6; W11 builds the `locked` field and refuses writes when it is set); `/sync`, the field bundle and offline capture (Phase 5).

## 1. Order of work

Four slices, each its own branch and pull request, stacked where they must be. Slices 1 and 3 do not depend on each other, so they can go in parallel.

| Slice | Branch | What | Size |
|---|---|---|---|
| 1 | `feat/p4-w11-work-records` | `operations`: the work record on a station (save with `base_version`, the template copied at start, ad-hoc checklist items, validation of every part), `visit.work_updated`, `locked` refusal, the visit page shows the record read only. | M |
| 2 | `feat/p4-w11-sensor-actions` | `operations`: apply, reverse and re-apply sensor actions through `sensor_applications`, `sensor_changed_later`, unknown serials flagged `needs_review`, field calibrations, configuration versions created at end, the `needs_review` flag on the Sensors page. Stacked on 1. | L |
| 3 | `feat/p4-w11-media-pipeline` | `media`: `process_image` and `process_video` in `media-worker` (Pillow, pillow-heif, ffmpeg), thumbnails, EXIF and GPS removed, capture time, `purge_originals`, the TP media fixtures, the image gains ffmpeg. | L |
| 4 | `feat/p4-w11-visit-media` | `operations` and front end: link media to a station and phase, `/internal/attachable` for visit media, delete until locked, the browser's resize and incremental SHA-256 (F4), an "Add photo or video" strip on each station of the visit page, the staging exit check. Needs 3. | M |

## 2. Decisions to approve (proposed W11-1 to W11-12)

1. **A work record is a document inside the station on the visit** (`site_visits.stations[].work`, TRD §5.2 `WorkRecord`). It is saved whole, not by parts: `PUT /api/v1/visits/{id}/stations/{sid}/work` takes the record and `base_version`. A save from an older version answers 409 `work_changed` with the current record (ADR-18 means no merge: only one person writes it, so a conflict can only be the same person on two devices, or an admin). The server stamps `version`, `updated_by`, `updated_at`; the client sends `device_id` for the audit trail.
2. **Who and when.** The station's owner or an admin saves; nobody else (404 for a client, 403 for other staff, 403 for viewers). Allowed while the visit is `started`, and after `ended` until it is locked (TRD §3.2.1); a planned or cancelled visit answers 409 `visit_not_started` / `visit_cancelled`. A locked visit answers 409 `locked`. The same codes `/sync` will report in Phase 5, from the same function (as W10-8).
3. **The template is copied when the visit starts** (VIS-8). Starting resolves each station's template (its type plus an add-on for each installed sensor model, the W10 `resolve`) and stores the items and the version numbers in `work.checklist_template`; a template edited afterwards changes nothing already started. A visit started before this slice has no copy: the first save copies it then. The checklist rows are the owner's answers: `{item_id, label, result: ok|fixed|issue|na, note, ad_hoc}`. Ad-hoc items (VIS-8) have a client UUIDv7 `item_id` and `ad_hoc: true`; template items cannot be removed.
4. **Every part of the record is typed and bounded** (rule 12): at most 60 checklist rows, 20 sensor actions, 20 configuration versions, 30 parts, 30 issues, notes up to 4000 characters. `parts_used`, `issues_found`, `sensor_actions` and `config_versions` entries carry device-made IDs (rule 9), so a retried save never doubles them.
5. **Sensor actions are applied by a pure function** (`domain/visits/reconcile.py`, no I/O): it takes the actions before and after a save, the `sensor_applications` already written, and the facts it needs (the unit, its installation, later changes), and returns the list of steps to write. The route runs the steps in the same transaction as the work save and the events (rule 2). On `end` and on every later save: a **new** action is applied; an **unchanged** one (same `action_hash`) is skipped; a **changed** one is reversed exactly and applied again; a **removed** one is reversed (TRD §3.2.3).
6. **What each action does** (proposed; question 2):

   | Action | Effect | Reversal |
   |---|---|---|
   | `install` | A unit in stock (by `new_serial`) is installed at the station for `parameter`; opens an installation with `source_action_id` | Close the installation, unit back to its status before |
   | `remove` | The installed unit (`old_serial`) leaves the station; closes the installation; the unit goes where `removal_reason` says (`faulty` to repair, `calibration` or `other` to stock, `retired` to retired) | Reopen the installation, unit back to installed |
   | `replace` | `remove` of the old serial and `install` of the new one for the same parameter, as one action | Both reversed |
   | `calibrate` | A calibration for the installed unit (method, reference instrument, readings, result) with `source_action_id`; sets the due date and, for a failed result, the `calibration_failed` flag (CAL-6) | Remove that calibration and restore the unit's due date and flag from before |
   | `clean`, `repair` | A note on the station's history; no inventory change | Nothing to undo |

7. **Reversal is refused when something moved on.** If a later visit or a manual inventory change has touched the same unit, or the same parameter at the station, since the action was applied, the save answers 409 `sensor_changed_later` naming the action and the later change, and **nothing in the save is written** (the record and the inventory move together). The correction is made on the later visit or by an admin. A change of `action_hash` is detected by hashing the action's fields that matter, not its note.
8. **Unknown serials are created once** (SEN-5): a `new_serial` that matches no unit makes a unit in stock of the action's `sensor_model_id` (required in that case), keyed by the action ID, `needs_review: true`, and installs it. The Sensors page shows a "Needs review" chip, and an admin clears it by completing the unit (manufacturer details, calibration interval). A serial that exists with another model answers 422 `serial_model_mismatch`.
9. **Configuration versions** (CFG-4): at `end` each `config_versions[]` entry becomes a version of the station (W6 `config-versions`) with its device-made ID and the files already uploaded; created versions never change (CFG-2). A correction adds a new version. Files that are not `ready` yet make `end` answer 409 `config_files_not_ready` listing them (media may still be scanning).
10. **Media on a visit** (VIS-5, VIS-10). `POST /api/v1/visits/{id}/stations/{sid}/media` links a media ID to a phase (`before`, `during`, `after`) with a caption and `captured_at`; any attending staff member or an admin may (ADR-18). The owner reference is `visit:{id}:station:{sid}:{phase}`, and `GET /internal/attachable` answers for it with the visit's organization. At most 50 items per visit, else 409 `too_many_media`. Delete (`DELETE /api/v1/media/{id}`) works for the uploader until the visit is locked.
11. **The pipeline** (TRD §10): images through Pillow and pillow-heif: EXIF orientation applied, capture time read, **all EXIF and GPS removed**, longest side 2048 px, WebP q80, and a 400 px WebP thumbnail. Video through ffmpeg: H.264/AAC MP4 at most 1280 px wide, CRF 28, `+faststart`, a poster frame at 1 s as the thumbnail, the duration. The worker runs **one video at a time** with a thread limit, so a 2-minute video cannot starve the shared host (R7, R8). A file ffmpeg or Pillow cannot read becomes `failed` with a reason the uploader sees; a processed file never replaces its original until `ready`. The original is kept 30 days after `ready`, then `purge_originals` deletes it (the cron the TRD already names).
12. **The browser prepares what it sends** (TRD §7.5, F4): images are resized to 2560 px and JPEG 0.85 before upload, `captured_at` is read before resizing, videos go as recorded. SHA-256 is computed **incrementally in a module worker** (`@noble/hashes` over 8 MiB `Blob.slice()` chunks), so a 200 MB video never sits in memory and the CSP (`script-src 'self'; worker-src 'self'`, no Wasm) is untouched. This lifts the upload engine's 64 MiB limit. The engine itself (`src/offline/upload.ts`) stays free of Vue and gets no Dexie code until Phase 5.

## 3. Back end

### operations

| Method | Path | Roles | Notes |
|---|---|---|---|
| PUT | `/api/v1/visits/{id}/stations/{sid}/work` | station owner, admin | The record whole, with `base_version`; applies sensor actions when the visit is `ended` (and on `end`); 409 `work_changed`, `sensor_changed_later`, `locked`, `visit_not_started` |
| POST | `/api/v1/visits/{id}/stations/{sid}/media` | attending staff, admin | `{media_id, phase, caption?, captured_at?}`; sets the media's visibility (see question 1) in the same transaction |
| POST | `/api/v1/visits/{id}/start` | (as W10) | now also copies the templates (decision 3) |
| POST | `/api/v1/visits/{id}/end` | (as W10) | now also applies the sensor actions and creates the configuration versions, in the same transaction as the status change; `overrides[]` still waits for W12 |
| GET | `/api/v1/visits/{id}` | any in scope | gains `stations[].work` (staff) and `stations[].media[]` (staff; clients in W12); a client never gets `work` |
| GET | `/internal/attachable` | service (media) | gains the `visit:` owner references |

Events (schemas in `mms_common.events.operations`, audit mapping unchanged: every event type is recorded):

- `visit.work_updated` (new, keyed by `request_id`): the visit facts, `station_id`, `version`, `sensor_actions[]` and `config_versions[]` as ids and kinds only (never notes, readings or serials beyond what `sensor.*` events already carry).
- `visit.ended` gains the `sensor_actions` and `config_versions` it already declared (W10 left them empty).
- The sensor and calibration events the inventory already emits (`sensor.installed`, `sensor.removed`, `calibration.recorded`, and so on) are emitted by the reconciliation with `action_id` set, so the audit chain shows which visit action caused each change.

Collections and indexes (migration `NNNN_work_records`): `sensor_applications` (`_id` = action ID, `visit_id`, `station_id`, `action_hash`, `effects`) with `visit_id`; `sensor_units.needs_review` (partial index); `site_visits` gains nothing new beyond the embedded `work`.

Layers, as before: `app/domain/visits/{work,reconcile}.py` (no I/O), `app/repo/visits/{work,applications}.py`, `app/api/visits/work_routes.py`, `app/events/publish.py` gains the emitters.

### media (slice 3)

`process_image` and `process_video` join `process_media` as worker tasks queued after the checks pass (a file is `ready` only when every step passed, as W6). `GET /api/v1/media/{id}` returns the view, thumbnail and (while kept) original URLs; `media.processed` gains `width`, `height`, `duration_s`, `captured_at`, `thumbnail_key`. The Docker image installs `ffmpeg` and the Python imaging libraries; the CI job for media installs ffmpeg on the runner. Fixtures are made at test time with Pillow and ffmpeg (nothing real, nothing large in the repository, since the repository is public): an upright JPEG, a rotated one, one with GPS and camera EXIF, a HEIC, a PNG, a 10-second H.264 clip, a clip with a rotation flag, a truncated file, an image renamed `.mp4`, and the EICAR string through the scanner.

### platform

No change in W11. The work-record events are audit-only; visit media does not notify anyone.

## 4. Front end

Mock-up boards to draw and approve before slice 4 (added to the "AWS-MMS W11 screens" canvas; light and dark where it matters). W11 builds no screen for filling in a work record: that is the field shell of W12, so the record is exercised by the API tests and read on the visit page.

1. The visit page's station row, started: the Times, **Add photo or video**, a strip of thumbnails by phase (Before, During, After) with captions, and an upload's progress and failure ("Try again", "Remove").
2. The same on a phone (the stations as cards): the strip scrolls sideways, Add photo or video is a full-width button, camera or library.
3. A station's work record, read only, on the visit page: condition, checklist results with notes, sensor actions as sentences ("Replaced AT sensor V-23001 with V-23044"), parts, issues, data downloaded, departure.
4. The Sensors page: a "Needs review" chip on a unit made from the field, and the complete-the-unit dialog.
5. A failed save of the work record (`sensor_changed_later`) as the API will answer it, drawn as the message a person would read, for W12 to reuse.

New files:

- `src/offline/hash.ts` (incremental, already the entry point from W6) gains the worker, `src/offline/hash.worker.ts`, and `src/offline/image.ts` (resize, EXIF capture time); no Vue imports there.
- `features/visits/`: `StationMedia.vue`, `MediaStrip.vue`, `MediaThumb.vue` (links ask for a ten-minute URL on click and keep nothing, as `SavedFile` does), `AddMediaButton.vue`, `WorkRecordView.vue`, and `work.ts` (sentences for actions, labels).
- `src/api/operations.ts` gets `visitsApi.saveWork`, `visitsApi.addMedia`; `src/api/media.ts` already has the upload calls.

## 5. PWA pre-flight (answers)

1. **Device.** Video capture is `<input type="file" accept="video/*">` and `capture` where it helps: the same on iOS Safari and Android Chrome, no new browser feature. iOS suspends background JavaScript (F12): a part that fails while the page is hidden is retried by the engine when the page returns; Phase 5 adds the "Keep AWS-MMS open" text on `/sync`.
2. **Network.** Every write here is idempotent: the work save by `base_version` plus device-made IDs in the record, the media link by `media_id`, the sensor actions by action ID. A response lost after the server applied a save is retried with the same `base_version` and answers `work_changed` with the record that holds exactly what was sent, which the client treats as success (the record equals what it sent).
3. **Lifecycle.** An update waiting while an upload runs is already handled by the update prompt rules (never reload mid-upload). The hash worker is a hashed asset in the precache; its absence offline is a cached miss, not a failure of the shell.
4. **Data and loss.** W11 is online only (OFF-10). The browser keeps the `File` handle in memory during an upload; a reload loses it and the person picks the file again, which joins the open upload (F15). Nothing is deleted locally because nothing is stored locally; Phase 5 stores the blob in Dexie and deletes it only after the server confirms (OFF-8).
5. **Storage.** No IndexedDB use. Memory is bounded: 8 MiB slices, one slice hashed at a time.
6. **Caching.** The service worker still caches no API response and no media. Processed media is fetched through ten-minute presigned URLs asked for on use.
7. **Security and shared devices.** `files.` host URLs expire in ten minutes and are never stored (TRD §7.6). The GPS EXIF of a photo is removed on the server for what is shown, and the original (which keeps it) is staff-only and purged after 30 days. `connect-src` already covers the files host (W6).
8. **Proof.** Vitest for the hash against known vectors and a 200 MB stream with bounded memory, for the resize and the EXIF capture time; media tests with real SeaweedFS, ffmpeg and Pillow; Playwright online (upload a photo and a short video, see them processed); the staging exit check; the iPhone and Android camera check joins the postponed phone checks.

## 6. Tests and the exit checks

- **Domain:** `reconcile` for every action and every pair (new, unchanged, changed, removed), reversal exactness (inventory equal to before), `sensor_changed_later` for each kind of later touch (a later visit's action, a manual install, a manual status edit, a calibration), unknown serial created once and not twice on a retry, `serial_model_mismatch`, `parameter_taken`, the work record's bounds and its IDs.
- **API** with real Mongo and Redis: matrix entries for every new route, viewers 403, clients 404 and never see `work`, other staff 403 on someone else's station, `base_version` conflict, locked, planned and cancelled visits, the save and the inventory in one transaction (a refused reversal writes nothing), `visit.work_updated` and the `sensor.*` events in the same transaction (outbox) and the audit chain.
- **Exit check 1 (sensor correction).** A technician records a swap at a station, ends the visit; the inventory shows the new unit installed and the old one in repair; the technician corrects the new serial and saves again; the history shows one swap with the corrected serial, the first unit is back in stock or repair as it was, and the audit chain has every step. A correction after a later visit changed the same unit is refused with `sensor_changed_later` and nothing moves.
- **Exit check 2 (media).** A 2-minute phone video and several photos (iPhone and Android files, one with GPS) uploaded from a phone to staging: photos come back as WebP with no GPS, the video plays in Chrome, Firefox and Safari, the thumbnails show, capture time is in the station's zone, an EICAR file is refused, and the processing time of the video and the worker's peak memory are written down (R7, R8).
- **Playwright:** an online journey: a technician starts a visit, uploads a photo and a short video to a station, sees them process, and reads the record; the unit created from an unknown serial shows "Needs review"; axe in light and dark on every new screen.
- Review: `web-design-guidelines` on each new screen, `writing-guidelines` on the sentences for actions, errors and the chip.

## 7. Questions for you

1. **When do clients see a visit's photos and video?** The PRD (VIS-11) says clients see "their media" but not when. Proposed: staff only while the visit is under way, and **client-visible from the moment the visit ends**, with a staff member able to hide one item. The alternative is to wait for the finalized visit report (Phase 6), which keeps a rough photo from a client until staff have chosen. (The TRD's rule is that the owning service shares a file in the same transaction that attaches it; this moves that step to `end`.)
2. **Where does a removed unit go?** Proposed by reason: `faulty` goes to In repair, `retired` to Retired, `calibration` and `other` to In stock. Is that the list you use, or is there another reason (lost, stolen, sent to a depot)?
3. **Which sensor actions ship first?** All six are in the TRD (`replace`, `calibrate`, `clean`, `repair`, `remove`, `install`). Proposed: all six, with `clean` and `repair` as notes only (no inventory change). Is a repair meant to move the unit to In repair and back, or just to be a note?
4. **Video quality and time.** The TRD's recipe is 1280 px, CRF 28, one video at a time. On the shared staging host a 2-minute video may take several minutes to process. Is "ready within about ten minutes" acceptable while we measure, or do you need it faster (lower quality, 720 px)?
5. **The photo limits.** TRD and PRD say 25 MB per image and 200 MB per video, about 50 items per visit. The browser resizes photos to 2560 px first, so photos are about 1 to 3 MB. Is 50 per visit the cap you want, or should a station have its own limit?
6. **Needs-review units.** The proposal is a chip on the Sensors page and an admin completing the unit. Should an admin also be told (an in-app notice) when the field creates one? It would be a new notification type; the proposal is no, because the chip and a filter are enough at the start.

## 8. Developer docs site (updated at the end of each slice)

Decisions W11-1 to W11-12, routes, events, collections, the visits and media sections, the changelog and the status badges. Charts for this week (Phase 4's suggested set, the ones that belong to W11):

1. Code flowchart: `reconcile`, branch by branch (new, unchanged, changed, removed; the refusal).
2. State: a sensor unit (in stock, installed, in repair, retired, needs review) and what moves it.
3. Sequence: ending a visit in one transaction (visit status, request status, sensor actions, configuration versions, outbox, then platform and report).
4. System flowchart: the media pipeline (upload, checks, image and video paths, thumbnails, purge).
5. State: a media file (pending to ready or failed, original kept and purged).
