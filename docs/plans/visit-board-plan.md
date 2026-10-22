# Phase 4 · Visit board plan: Notes, Tasks, Recommendations and Config replace the work record

Proposed 2026-10-22. **Questions answered 2026-10-22** (section 9). W11 slice 4 is merged (#65). Slice 0 (#66) and slice 1 (#68) are merged. **Slices 2 and 3 are built** on `feat/p4-board-screens` (#69), from the approved Stitch screens and the mock-up for the rest (decision 36). **Slice 4 is built** on `feat/p4-board-config-requests` (decisions 37, 38). Still open: the staging exit checks. The mock-up boards (section 5) must be drawn and approved before slices 2 and 3.

A visit is now **filling in a board for each station on it**. The board holds sticky notes of four kinds: **Note**, **Task**, **Recommendation** and **Config**. They capture everything that happened during the visit. This replaces the structured work record (W11 slices 1 and 2), the media phases Before, During and After (W11 slice 4) and the checklist templates (W10 slice 2). The visit's lifecycle (schedule, start, arrive, depart, end, cancel, restore), the request status derived from visits, the media pipeline (W11 slice 3), the browser's hashing and upload queue, and VIS-9 (another visit needed) are unchanged.

**What this changes for the rest of the plan:** W12's field-shell stepper (Before → Work → After → Review) is replaced by the same board on a phone, so W12 becomes "the board on a phone, and the client's view". Phase 5's sync ops for a visit's work become per-element ops (TRD §7.2). Phase 6's visit report is built from the board's elements.

## 1. Order of work

First, as agreed: **merge `feat/p4-w11-visit-media` (W11 slice 4) as it is** once CI is green. Its media linking, upload queue, thumbnails, hashing and processing are what the board reuses. Then come five slices, each on its own branch.

| Slice | Branch | What | Size |
|---|---|---|---|
| 0 | `docs/visit-board` | Planning documents and the docs site's decisions (section 7). No code. | S |
| 1 | `feat/p4-board-backend` | `operations`: remove the work record, reconciliation, `sensor_applications`, checklist templates and phases; the `visit_elements` module (domain, repo, routes, events, media owners, `/internal/attachable`); the migration that clears staging's test data; the matrix; OpenAPI. Front end: remove what called the removed routes (`WorkRecordView`, the checklist editor, the Needs review chip and filter, the phase strip) so CI stays green; the visit page shows "Board coming" in their place. | L |
| 2 | `feat/p4-board-viewers` | The file viewers inside a modal: image, video, PDF (pdf.js), text and code, and the fallback. Check the files host's CORS for `GET`. Needs the mock-up. Can run beside slice 3. | M |
| 3 | `feat/p4-board-screens` | The board, the sticky notes, the element modal for each kind, the Add menu, the filter chips, the phone layout, the client's read-only board, the End visit warning. Needs 1 and the mock-up. | L |
| 4 | `feat/p4-board-config-requests` | Config's After files become configuration versions at `end` and on later saves; "Create request" from a Recommendation; the staging exit checks. Needs 3. | M |

## 2. Decisions (W11-16 to W11-35)

These supersede W11-1 to W11-9, W11-15 (the screens for the work record and the phase strip) and the checklist-template decisions W10-11 and W10-12. W11-10 to W11-14 (media linking, the pipeline, browser preparation, visibility at end, incremental hashing) still apply, with the owner reference changed by decision 27.

16. **The board replaces the whole work record** (answered). Removed: `domain/visits/{work,reconcile}.py`, `api/visits/{work_schemas,work_routes,sensor_apply}.py`, `stations[].work`, the `sensor_applications` collection, `PUT .../work`, the media `phase` field, the checklist templates (`domain`/`repo`/`api` for checklists, `seed-checklists`, `/admin/checklists`, the `checklist_templates` collection), and `visit.work_updated` (its schema stays registered so old audit records still parse; it is no longer emitted). PRD VIS-5, VIS-7 and VIS-8 are rewritten, and VIS-6 is dropped (decision 34).
17. **Visits no longer change the sensor inventory** (a consequence of decision 16). SEN-4 (a swap updates the inventory) and SEN-5 (unknown serials created from the field) are now done on the Sensors page with install and remove (W5-1). A calibration in the field (CAL-1) is recorded on the station's Calibration tab. The Needs review chip, its filter and "Mark as reviewed" are removed, because nothing creates such units any more. The `needs_review` field is dropped by the migration.
18. **One board per station on a visit** (answered). Elements live in a new collection, `visit_elements`, not inside `site_visits`. Each element is versioned on its own, so a conflict covers one element only, and the visit document stays small.
19. **Four kinds, each with a fixed colour** (answered) and always an icon and a label, so colour is never the only cue (WCAG 1.4.1). Note is yellow, Task green, Recommendation red and Config purple. The tints are new tokens, `sticky-note`, `sticky-task`, `sticky-recommendation` and `sticky-config`, in `brand.ts`, with light and dark values. They are not status colours and are not taken from the Material theme, and text on them reaches at least 4.5:1. DBD gets a "Sticky note" component.
20. **What an element holds.**

    | Field | Kinds | Rule |
    |---|---|---|
    | `id` | all | UUIDv7 made on the device (rule 9); creating is idempotent by it |
    | `visit_id`, `request_id`, `station_id`, `org_id` | all | `org_id` is the station's `owner_org_id`, for the client scope in `repo/` (rule 3) |
    | `kind` | all | `note`, `task`, `recommendation`, `config` |
    | `title` | all | required, up to 80 characters (answered: a short title and a description) |
    | `description` | all | up to 4000 characters, optional |
    | `items[]` | task | `{id, text, done, done_by, done_at}`, up to 50, text up to 200 characters, `id` made on the device |
    | `priority` | recommendation | `low`, `medium` (default), `high` |
    | `request_ref` | recommendation | `{id, number}` of the request made from it (decision 23) |
    | `media` | all | sections: `main` for note and recommendation; `before` and `after` for task and config. Each entry is `{media_id, kind, filename, caption, captured_at, added_by}` |
    | `shared` | all | decision 28 |
    | `config_version_ids[]` | config | the station versions made from it (decision 24) |
    | `completed_at` | task | set by the server, decision 21 |
    | `created_by`, `created_at`, `version`, `updated_by`, `updated_at`, `device_id`, `deleted_at` | all | server fields; `deleted_at` is a tombstone (decision 26) |

21. **A task is complete when it has at least one item and every item is checked.** The server sets `completed_at` when that becomes true and clears it when an item is unchecked or added. A task with no items is incomplete and shows "Add an item". Completion is derived from the items and never set directly.
22. **Who** (answered). Any attending staff member or an admin can create an element. The element's author, the station's owner or an admin can edit, delete, tick items, add or remove media and change sharing (answered: ticking and media follow the editing rule). Other attending staff and viewers see the board read only, and viewers never mutate (rule 5). Clients see shared elements of an ended visit only. Out of scope is 404 (rule 4). Author names go to clients as `{id, name}` (D4).
23. **Recommendation → request** (answered: a priority and "Create request"). It is online only, because request creation is not offline work (OFF-10). As built, see 38: the sheet asks for the kind of work and makes the request through the recommendation's own route; a linked recommendation shows "Request MR-…" instead of the button.
24. **Config → configuration versions** (answered: yes, at visit end). At `end`, each Config element with After files becomes a new configuration version of the station (W6 `config-versions`). The version's device-made ID is derived from the element's ID and its `version`, its note is the title, and its files are the After files. Files that are not `ready` make `end` answer 409 `config_files_not_ready` with the list, as W11-9 did. After `end`, changed After files are saved as the next version from the sheet (see 37), because versions never change (CFG-2). Deleting the element leaves its versions. Before files are kept on the visit only, as the record of what was there.
25. **When** (answered). The board can be edited from `started` until the visit is locked by its report (Phase 6). On a planned visit the answer is 409 `not_started`, on a cancelled one `visit_cancelled`, and on a locked one `locked`. These are the same codes `/sync` will report, from the same function (as W10-8).
26. **Saves.** Create is `POST` with the device-made `id`. Repeating it with the same content answers 200 with the element; the same `id` with different content answers 409 `duplicate_id`. An update sends the whole element (title, description, items, priority, shared) with `base_version`; a stale one answers 409 `element_changed` with the current element, and a retry whose content equals the current element is treated as success (as W11-1). Delete sends `base_version` and leaves a tombstone, so an element deleted on one device is never brought back by a late save from another: that save answers 409 `element_deleted`. **Media is linked separately from the version** (`POST|PATCH|DELETE .../media`, idempotent by `media_id`), so a photo arriving after a long upload never conflicts with a text edit.
27. **Media owner reference:** `visit:{visit_id}:station:{station_id}:element:{element_id}:{section}`, and `GET /internal/attachable` answers for it with the station's organization. Config's sections take what the `config` kind already accepts (any extension except executables, scripts, HTML and SVG; 50 MB), as well as photos and video. The other kinds take photos and video. W11-10's per-file limits stay, and there is no cap on items.
28. **Sharing** (answered: a toggle on each element). The defaults are Recommendation and Task shared, Note and Config staff only. Nothing reaches a client before the visit ends. At `end`, media of shared elements is shared (`media.visibility_requested`, `org`), in the same transaction, as W11-13 does today. Changing `shared` after the end, or deleting a shared element, emits the matching visibility change. W11-13's hide action stays for a single item inside a shared element.
29. **The modal shows every file in place** (answered: PDF and text inline, others download). Nothing opens a new tab.
    - **Images:** the processed WebP, with arrows and swipe between the items of a section.
    - **Video:** `<video controls playsinline preload="metadata">` from a ten-minute link. `media-src` already allows the files host.
    - **PDF:** pdf.js (`pdfjs-dist`), loaded with `import()` and kept out of the `app` chunk (W7 gotcha). Its worker is a bundled module file, because `worker-src 'self'` rules out `blob:` workers (F16).
    - **Text and code** (`.py`, `.ttx`, `.txt`, `.csv`, `.json`, `.xml`, `.ini`, `.cr*`, `.log`, and anything that is valid UTF-8 without NUL bytes): fetched through the ten-minute link and shown in a `<pre>` in JetBrains Mono with line numbers, never as HTML. Files up to 1 MB are shown; larger ones get a Download button.
    - **Anything else:** name, size, type icon and Download.
30. **The precache budget (F14 gotcha: fewer than 30 files).** pdf.js adds a chunk and a worker. It goes in `globIgnores` like `materialGenerate`, so until Phase 5 a PDF needs a connection to view and offline shows "Download when you're back online". Phase 5 decides whether the field bundle precaches it. This is raised as finding F17 in the `pwa` skill.
31. **The board on screen** (answered: an ordered grid with filters). It is a responsive grid of sticky notes, newest first, with filter chips that show a count each (All, Notes, Tasks, Recommendations, Config). A sticky note shows its kind's icon and label, the title, two lines of description, then by kind: a task's progress (3 of 5) and a check when complete; a recommendation's priority; Config's file count. It also shows a media count with the first thumbnail, a "Shared" mark and the author. Clicking a note opens its modal, a dialog at 640 px and wider (`ModalSheet`) and a full-screen sheet on phones. There is no dragging.
32. **On a phone the board replaces the field stepper** (answered). One column, a floating Add button (Note, Task, Recommendation, Config), arrive, depart and end in the bottom bar. DBD and AFD lose the Before → Work → After → Review stepper.
33. **Ending with incomplete tasks** (answered: allowed, with a warning). The End visit dialog lists the incomplete tasks and asks to confirm. The check is only in the dialog: the server never refuses `end` for it, because an `end` synced from a phone cannot answer a question. The tasks stay editable until the report locks.
34. **VIS-6 is dropped** (answered). Before and After now belong to Tasks and Config, so nothing is required per station at `end`. The override reason goes too.
35. **Events and notifications.** The events are `visit.element_added`, `visit.element_updated` and `visit.element_deleted`, keyed by `request_id`. They carry facts only: `visit_id`, `station_id`, `element_id`, `kind`, `shared`, `completed` (task), `priority` (recommendation), `aggregate_version`. They never carry the title, description or item text, as comment events don't (W9). `visit.media_changed` gains `element_id` and `section`. There are no new emails or notifications (answered): clients see shared recommendations on the visit page and in the visit report (Phase 6). The audit consumer records the new types by default (AUD-1).

36. **Sticky notes are white cards with a coloured top edge** (answered 2026-10-22, after the Stitch screens). The kind's accent is on the card's 4 px top edge, its icon and its label; the pale tint is kept for the open sheet's header band and the Add menu's swatch. The title is the card's button, stretched over the whole card, so the card's name is the title (WCAG 2.5.3).

37. **Versions after the end are saved by hand, and board versions may repeat a file** (W11-37, 2026-10-22). A file added after the end is still being checked when it reaches the element, so it cannot join a version at that moment: after the end, the Config sheet shows "Save as a new configuration version" when the After files differ from the last version made from it (`POST .../elements/{id}/config-version`; pressing it again makes nothing more). A version holds the After files that are not photos or video. Versions made from the board are marked `from_board` and may repeat an unchanged file; the W6 rule that a file belongs to one version now covers hand-made versions only (migration `0012`).
38. **A recommendation makes its request through its own route** (W11-38, 2026-10-22). Technicians cannot create requests (clients and admins do), so `POST .../elements/{id}/request` (`id` made on the device, a category; title and description from the recommendation) is open to whoever can edit the recommendation: a technician's request starts Submitted for an admin to approve, an admin's Approved, for the station's organization and that station, with the recommendation's priority (low, normal, high). The request carries `source: {visit_id, element_id}`; the element gets `request_ref` in the same transaction. One recommendation makes one request (409 `already_requested`).

## 3. Back end (slice 1, plus slice 4's two features)

- **`operations` `domain/visits/elements.py`** (no I/O): `check_can_create`, `check_can_edit` (decisions 22 and 25, the sync codes), `validate` (bounds, kinds, sections per kind, item IDs unique), `apply_update` (the version, `completed_at`), `is_complete`, `sharing_changes(before, after)`, and `config_versions_due(element)` for decision 24.
- **`repo/visits/elements.py`**: client-scoped queries (rule 3: `org_id` plus `shared` plus an ended visit), with tombstones excluded from lists. Indexes go in a new migration: `(visit_id, station_id, created_at)` and `(org_id)`.
- **`api/visits/element_routes.py`**, with the literal paths declared before `{element_id}`:
  - `GET /api/v1/visits/{id}/stations/{sid}/elements`
  - `POST /api/v1/visits/{id}/stations/{sid}/elements`
  - `GET|PUT|DELETE /api/v1/visits/{id}/stations/{sid}/elements/{element_id}` (PUT and DELETE take `base_version`)
  - `POST|PATCH|DELETE /api/v1/visits/{id}/stations/{sid}/elements/{element_id}/media[/{media_id}]` (replaces the W11 slice 4 visit media routes)
  - `GET /api/v1/visits/{id}` gains `stations[].board`: counts by kind, incomplete tasks and the latest thumbnail, for the visit list and the End dialog.
- **`lifecycle.end`** shares media of shared elements and creates Config versions (slice 4), in the one transaction with the status change and the request's derived status.
- **`requests`**: `POST /requests` accepts `source` (decision 23), checked against an element the caller can edit.
- **Migration `NNNN_visit_board.py`** (forward only): unset `stations[].work`, drop `sensor_applications` and `checklist_templates`, unset `needs_review` on sensor units, and for every media link with a phase owner emit `media.deletion_requested` through the outbox. **Staging's test visits are cleared, not migrated** (answered). No production data exists.
- **media**: no change to kinds or the pipeline. The `GET /api/v1/media/{id}` answer gains `size` and `content_type` if the viewer needs them (check in slice 2).
- **Authorization matrix**: every new route. Viewers 403, clients 404 before the end and on unshared elements, other attending staff 403 on edits.

## 4. Front end

New in `features/visits/board/`:

- `VisitBoard.vue` (grid, filter chips, the Add menu or floating button)
- `StickyNote.vue`
- `ElementDialog.vue` (on `ModalSheet`), with a body for each kind: `NoteBody.vue`, `TaskBody.vue` (`TaskItems.vue`), `RecommendationBody.vue` and `ConfigBody.vue`
- `MediaSection.vue`, which reuses `MediaThumb`, `PendingThumb`, `AddMediaDialog`, `CaptionDialog` and `mediaLinks.ts`, with one `useVisitMedia` queue per section key
- `board.ts`: the rules of decisions 21, 22 and 31, with no Vue, tested in Vitest

New in `features/visits/viewers/`: `FileViewer.vue`, which picks one of `ImageViewer`, `VideoPlayer`, `PdfViewer` (with `pdf.ts` loading pdf.js through `import()`), `TextViewer` or `FileFallback`.

Removed: `WorkRecordView.vue`, `work.ts`, `StationMedia.vue`'s phase strip, `NeedsReviewChip`, `ReviewRow`, the checklist admin pages and the `/admin/checklists` route and menu entry. `visitsApi` gets `listElements`, `createElement`, `saveElement`, `deleteElement` and the element media calls.

## 5. Mock-up boards to approve (new canvas "AWS-MMS Visit board", light and dark)

1. The board on a desktop: station header, filter chips with counts, all four kinds of sticky note in their states (task 3 of 5 and complete, high-priority recommendation, Config with files, shared and staff-only), and the Add menu.
2. Note and Recommendation modal: title, description, media section with uploads in progress, share toggle, priority, Create request and "Request MMS-…".
3. Task modal: items with checkboxes, add an item, Before and After sections, the complete state.
4. Config modal: Before and After with files by type (icons, sizes, ready or processing) and photos.
5. The viewer inside the modal: image, video, a PDF, a Python file, and a file with no preview.
6. Phone: the board in one column with the floating Add button and bottom bar; the modal as a full-screen sheet.
7. End visit dialog with incomplete tasks.
8. The client's board: shared elements only, read only.
9. Edge states: empty board, loading, a save that failed with `element_changed`, a deleted element, "This needs a connection" (Create request, PDF offline).

## 6. PWA pre-flight (answers)

1. **Device.** The modal is a full-screen sheet on phones, and on iOS the video uses `playsinline` so it does not jump to full screen. pdf.js draws PDFs the same way on every browser (iOS shows only a PDF's first page in a frame, to confirm on a real iPhone with the postponed checks). Camera and file pickers are the existing `<input type="file">`.
2. **Network.** Every write is idempotent: create by `id`, update by `base_version`, media by `media_id`, the request from a recommendation by the request's `id`. A lost response is retried and lands as success (decision 26). Create request and the PDF viewer say "This needs a connection" when offline.
3. **Lifecycle.** The update prompt never reloads while a modal holds unsaved edits or an upload runs (existing rule). Phase 5's op payloads carry a version so ops queued before an update still sync.
4. **Data and loss.** This stays online only until Phase 5 (OFF-10). Unsaved modal text is kept in memory until saved, as comments are (W9). Per-element records with tombstones mean a phone can never resurrect a deleted element or overwrite another's edit (ADR-18 kept: one editor set per element, no merge).
5. **Storage.** No IndexedDB until Phase 5. The text viewer reads at most 1 MB.
6. **Caching.** No API response or file is cached by the service worker. pdf.js is excluded from the precache (decision 30, finding F17).
7. **Security and shared devices.** Text files are shown as text, never as HTML. HTML and SVG uploads stay blocked, and downloads keep `Content-Disposition: attachment` and `nosniff`. Ten-minute links are never stored. Clients get author `{id, name}` only. pdf.js runs with `isEvalSupported: false` under `script-src 'self'`.
8. **Proof.** Vitest for `board.ts` and the viewer choice; domain and API tests (below); Playwright for the board online on desktop and phone with axe in light and dark; a real phone check on staging.

## 7. Documents to update in slice 0

- **PRD:** rewrite VIS-5, VIS-7 and VIS-8 as the board, drop VIS-6, mark SEN-4, SEN-5 and CAL-1 as Sensors page only, CFG-4 through Config.
- **TRD:** §3.2.1 visits, remove §3.2.3 reconciliation, §5 `visit_elements` schema, §7 sync ops (`element.create`, `element.update`, `element.delete`, `element.media_add`, `element.media_remove` replace `work.save`) and conflicts (`element_changed`, `element_deleted`), and the §8 events table.
- **AFD:** J6 field visit and the field shell.
- **DBD:** the Sticky note component and its tints, the board layout, and the removal of the stepper.
- **BSD:** `visit_elements`; removal of `sensor_applications`, `checklist_templates` and `needs_review`.
- **TP:** the tests below.
- **IP:** W12 becomes the board on a phone and the client view.
- **Docs site:** the visits section, routes, events, collections, decisions W11-16 to W11-35, changelog and status.
- **CLAUDE.md:** orientation and the W11 notes.

## 8. Tests and exit checks

- **Domain:** permissions per role and status, bounds, sections per kind, completion and its clearing, `duplicate_id`, `element_changed` with an equal-content retry, tombstones and `element_deleted`, `sharing_changes`, Config versions due before and after `end`.
- **API** (real Mongo and Redis): the matrix; client scope (unshared, before end, other organization: 404); events and the visit's status in one transaction; Config versions created once on a retried `end`; the request from a recommendation linked once; media visibility at end and on a toggle after end.
- **Playwright:** a technician starts a visit and adds one of each kind (a photo on a note, a task with Before and After photos ticked to complete, a recommendation turned into a request, a Config with a `.py` file viewed in the modal and a PDF); ends the visit with the warning; the client sees the shared ones only; a phone run; axe light and dark.
- **Staging exit checks:** one visit with all four kinds from an Android phone; a 2-minute video played in the modal (the W11 media exit check, still open); the Config version shows on the station's Configurations tab; the client view. The W11 sensor-swap exit check is dropped (decision 17).
- **Review:** `web-design-guidelines` on every screen, and `writing-guidelines` on labels, empty states and errors.

## 9. Questions (answered 2026-10-22)

1. How much is replaced: everything, plus a fourth kind, Config, with Before and After files.
2. Dashboard scope: one board per station on a visit.
3. Editing: attending staff add; the author, the station owner or an admin edits.
4. Clients: a toggle per element (Recommendations and Tasks shared by default).
5. Config's After files become the station's configuration versions at `end`.
6. Files: PDF and text inline, others download.
7. Layout: an ordered grid with filter chips.
8. Task items: typed only. The checklist templates go.
9. Colour: fixed per kind; Config is purple.
10. Recommendation: a priority and "Create request".
11. When: from start until the report locks.
12. W11 work: merge slice 4, then replace on top; staging test data is cleared.
13. Title: a short title and a description.
14. Ending with incomplete tasks: allowed, with a warning.
15. Phone: the board replaces the stepper.
16. VIS-6: dropped.
17. Ticking and media: same people as editing.
18. Client notification: none; shown on the visit page and in the report.

**Charts proposed for this work** (pick, drop or add):

1. ER: `visit_elements` with `site_visits`, media and configuration versions.
2. Decision tree: who can see and edit an element (role, attendance, author or owner, visit status, shared).
3. State: a task (no items, incomplete, complete) and what moves it.
4. Sequence: ending a visit (status, request status, shared media, Config versions, outbox).
5. System flowchart: how the modal picks a viewer for a file.
