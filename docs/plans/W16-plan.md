# Phase 6 · W16 plan: report drafts, the read model and the visit report PDF

Proposed 2026-10-23, while W15 (the field test) waits on a staging deploy and the phones. Questions are in section 8; nothing is built from this plan until they are answered. Slices 1 to 3 have no screens and can start first; slice 4 needs approved boards.

Delivers RPT-1 (a draft when a visit ends and syncs), RPT-3 (preview the draft as a PDF), RPT-9 (station time zone on reports), RPT-10 (branding and `VR-` numbering), the read-model backfill of TRD §8.6 for the report service, and the notification "Draft report ready" (PRD Appendix B). Journey J7 starts here (the technician reads the draft); it finishes in W17.

**Not in W16** (so it is clear where it goes): editing the narrative and choosing photos (RPT-2), signatures (RPT-4, RPT-5), finalize, the visit lock, reopen and verify (RPT-6, RPT-11), the finalize reminders (RPT-7), client review (W18), client reports (CRP, W18), the close-out report (RPT-8, W18), summary reports and the dashboard (Phase 7). The `sensor_events` read model is Phase 7 too: nothing in W16 reads it.

## 1. Where things stand (checked 2026-10-23)

- **report service:** the skeleton and the label sheet only (W7). Jinja + WeasyPrint render path, `report_jobs` + the Redis queue (`mms_common.jobs`), `report-worker`, S3 bucket `mms-reports`, `GET /reports/jobs/{id}`. **No consumer, no Kafka consume rights** (`infra/kafka/users.yml`: report produces only), no `reports` collection, no events of its own (`mms.report.events` exists and is empty).
- **operations:** `visit.ended` and `visit.element_added|updated|deleted` events carry facts and ids, never the notes (rule 1: the report must ask). The visit board is built (`visit_elements`), Config elements make configuration versions at `end`, `/internal/snapshot/{stations|sensor_units|calibrations|requests|visits}` exist (not elements), `/internal/labels` shows the pattern for a report-service read. `site_visits` has `locked` and `report_status` fields already.
- **media:** processes images and video to a `view.webp` and a `thumb.webp` beside the original; `media.processed` carries width, height and duration; `/internal/media/{id}/url` gives a link but only for the `operations` service.
- **Phones:** nothing changes on the phone except wording: after a visit syncs, a draft report follows (see §6).
- **Product questions:** Q1 (branding and numbering), Q2 (attestation wording) and Q3 (jurisdictions) are due "by the start of W16" (IP). Q2 and Q3 have defaults in the PRD and W17 is where they bite; Q1 is needed by slice 3.

## 2. Order of work

Four slices, each its own branch and pull request, stacked where they must be.

| Slice | Branch | What | Size |
|---|---|---|---|
| 1 | `feat/p6-w16-read-model` | Kafka rights for `report`, the consumer group, the read model (`request_facts`, `visit_facts`, `station_facts`, `calibration_facts`) with `aggregate_version` guards, the backfill command and a run on staging | M |
| 2 | `feat/p6-w16-draft` | The `reports` collection, operations' `GET /internal/visits/{id}/report-facts`, media's rendition read, the `visit.ended` consumer, refresh on board and media events, the render job, `report.drafted`, `GET /reports`, `GET /reports/{id}`, `POST /reports/{id}/preview`, `GET /reports/{id}/download`, platform's "Draft report ready" | L |
| 3 | `feat/p6-w16-template` | `visit.html.j2` and `print.css` from PRD Appendix A (as the board), images and video QR, the DRAFT watermark, time zones, `template_version`, the visual regression baseline | L |
| 4 | `feat/p6-w16-screens` | The Report section on the visit page: status, number, Preview, the "draft ready" link; the sync wording; boards for W17 approved this week | S |

Slice 1 and slice 3 do not depend on each other. Slice 2 needs slice 1's consumer plumbing; slice 3 fills in the template that slice 2's job renders (slice 2 ships with a plain placeholder template so the pipeline is testable end to end first).

## 3. Decisions (proposed W16-1 to W16-12)

1. **The draft is a record first, a PDF second.** On `visit.ended` the consumer inserts `reports` `{type: visit, subject_ref: visit:{id}, version: 1, status: draft}` in one Mongo transaction with its `processed_events` row (rule 2; idempotent by `(subject_ref, version)`, so a redelivered event adds nothing). The record exists within seconds; the PDF follows.
2. **Facts come from one internal read.** `GET /internal/visits/{id}/report-facts` (operations; service `report` only) returns, in one document: the visit (ref, request ref and title, organization name, dates, outcome, follow-up notes, staff with the lead marked and names, each station's owner, arrive and depart), each station's details (name, code, type, country, coordinates, elevation, time zone, parameters), every live board element with its content (title, description, items and checks, priority, shared, linked request ref) and its media entries (id, kind, caption, capture time, section), the configuration versions made (number, file names, note) and the follow-up calibrations due at those stations. `content.facts` is that document, frozen at the time of the draft and **refreshed** while the report is a draft; the report never reads operations' database (rule 1).
3. **The narrative starts from the board.** `content.narrative` is pre-filled from the visit's follow-up notes and the Notes and Recommendations (TRD §11.2 step 1); `media_selection` defaults to the first Before and After image of each Task and up to six images per station (TRD §11.1). Nothing in W16 edits them; W17 does.
4. **A board change refreshes the facts and never the narrative.** `visit.element_added|updated|deleted` for a visit whose report is a draft re-reads the facts, bumps `facts_version`, leaves `narrative` and `media_selection` as they are, and (from W17) clears the signatures. For a report that is not a draft the event is ignored (a finalized report is immutable, rule 11; the visit lock stops edits anyway).
5. **The PDF is rendered when the media is ready, or after five minutes.** TRD §3.4: wait up to five minutes for `media.processed` on the visit's files. The consumer keeps `awaiting_media: [media_id]` on the draft; each `media.processed` or `media.failed` for one of them removes it and, when none is left, queues `render_draft`; a cron `due_drafts` (every minute, a Redis lock per run) queues the render for any draft older than five minutes that still has no PDF. A file that is still processing then prints as a grey box with its caption. This meets the exit criterion (a draft PDF within 10 minutes of sync) with room to spare.
6. **Preview is the same job, on demand.** `POST /reports/{id}/preview` (staff, draft only) queues `render_draft` for the current `content_version` and `facts_version` and answers with a job (the label sheet's pattern); a repeat for the same versions returns the existing PDF. PDFs are stored at `visits/{report_id}/draft-{content_version}-{facts_version}.pdf` in `mms-reports` (keys are never reused, TRD §10.1); the last few drafts are kept and the cron `purge_drafts` removes older draft PDFs after seven days (a final PDF is never purged).
7. **Images reach the worker through media, not the store.** `GET /internal/media/{id}/rendition` (media; services `operations` and `report`) streams the 1024 px display copy (`view.webp`); the worker converts it to JPEG with Pillow for WeasyPrint (TRD §11.1) and caches it for the run. The report service has no rights on media's buckets, and the files host is not reachable from the worker's network by its public name. Videos use the poster frame and a QR to `/visits/{id}/media/{media_id}` (segno).
8. **Numbers and versions.** The report's number is the visit's ref (`VR-2026-0042-02`); the version is shown as "v1" in the header; both are in the filename. Q1 may change the format: the number is built in one function in `domain/numbering.py`.
9. **Branding.** The built-in MARS-MMS mark and the built-in brand colours until Q1 is answered; the template reads its colours from CSS variables set by one stylesheet, so an organization's colours (auth's branding setting) can be fed in later without touching the layout. Status colours are not used for decoration.
10. **Times in the station's zone.** Every time is formatted in the zone of the station it belongs to, with the abbreviation (`14:05 AST`); the summary and header use the zone of the first station (as the visit emails do). A visit across zones shows each station's own times. Signature blocks (W17) will show UTC as well.
11. **`report.drafted` is the only new event** (`mms_common.events.report`: `report_id`, `number`, `version`, `visit_id`, `request_id`, `org_id`, `staff_ids`, `lead_staff_id`; no content). Platform turns it into the in-app notification "Draft report ready" for the attending staff, with the report link. The audit consumer records it by default (AUD1). `report.finalized`, `report.reopened` and the rest come with their slices.
12. **Access in W16.** Staff read drafts (attending staff and admins edit in W17; viewers read). **Clients see nothing**: `GET /reports` returns final reports for a client's organization only, and there are none until W17 (rule 6: drafts are staff-only; a draft asked for by a client is 404, rule 4). The authorization matrix gets every new route.

## 4. Back end

| Where | What |
|---|---|
| `infra/kafka/users.yml`, `kafka-init`, compose | `report` consumes `mms.operations.events mms.media.events` (and `mms.auth.events` if the directory is needed) in group `report`; DLQ topic exists |
| `libs/mms_common/events/report.py` | `report.drafted` (version 1) |
| `services/report` | `migrations/0002_reports` (collections and indexes of TRD §5.4: `reports` on `(subject_ref, version)` unique, `pdf_sha256`, `(type, status)`, `request_id`); `domain/{numbering,draft,facts}.py` (no I/O: the narrative from the board, the default photo selection, who is awaited); `repo/{reports,readmodel,operations,media}.py`; `events/{consumer,visit_consumer,readmodel_consumer}.py`; `jobs/{render_draft,due_drafts,purge_drafts}.py`; `api/report_routes.py`; `cli.py` (`backfill`) |
| `services/operations` | `GET /internal/visits/{id}/report-facts` (decision 2) with a contract test; scoping by service only |
| `services/media` | `GET /internal/media/{id}/rendition`; `/internal/media/{id}/url` also for `report` |
| `services/platform` | `plan()` entry for `report.drafted` (attending staff, in-app) |

New public routes (all staff; matrix rows): `GET /api/v1/reports?subject_ref=&type=`, `GET /api/v1/reports/{id}`, `POST /api/v1/reports/{id}/preview`, `GET /api/v1/reports/{id}/download`. Literal paths (`/labels`, `/jobs/...`) stay before `/{id}`. After the API change: `export_openapi.py`, `npm run api:types`.

**The backfill** is `python -m app.cli backfill` in the report container (the same shape as operations' `backfill-orgs`): it pages operations' `/internal/snapshot/{stations|calibrations|requests|visits}` with a service token, upserts each row with `upsert_if_newer` (so live events and the backfill cannot disagree, TRD §8.6), and prints counts. TRD §8.6 names `infra/scripts/backfill.py --consumer <service>`: it becomes a thin wrapper that runs the service's command in its container; the TRD is corrected in the same change. Run on staging at the end of slice 1 (50 stations, 50 example requests; no real visits yet, so `visit_facts` fills from the field test's visits as they end).

## 5. The template and the baseline (slice 3)

- `app/templates/visit.html.j2` extends `base.html.j2`; sections as PRD Appendix A, adapted to the board: header (mark, "Site Visit Report", number, version, status, dates), summary, per station (details, Tasks with their checks and Before and After photos, Notes, Recommendations with the linked request, Configuration changes with version numbers and file names, work performed), videos, recommendations and follow-up, signatures (an empty "Not yet signed" block in W16), appendix of remaining photos with capture times. Incomplete tasks are highlighted. Footer: page x of y, generated date; the verification hash appears on a final only.
- Fonts: Inter and JetBrains Mono as the label sheet (the report image installs them); no web fonts, no network at render time.
- **Visual regression baseline.** A fixed, made-up visit (`tests/fixtures/visit_facts.json` and three small generated images; no real station, person or client, the repo is public) is rendered inside the report image in CI, each page rasterised with `pypdfium2` at 80 dpi and compared with the committed PNGs under `tests/baselines/` with a small tolerance (default 0.5% of pixels differing, per page). A deliberate template change updates the baselines through `pytest --update-baselines`, in the same commit, and the PR shows the images. The render test skips where Pango is missing (Windows), as the label test does; the baseline is made and checked only in Linux, where the fonts are the image's.
- Plain-text assertions on the PDF as well (`pypdf` text): the number, the zone abbreviation, each station name, "Additional visit required" when it is.

## 6. PWA pre-flight (answers)

1. **Device.** W16 changes no phone code except wording and one section on the visit page. A draft PDF is viewed online only (OFF-10); the phone shows "Needs a connection" for Preview offline. iOS: the PDF opens in the app's own viewer (`PdfViewer`, pdf.js, online only) rather than a new tab, so there is no Safari download or blob-URL quirk to depend on; a Download link is the fallback.
2. **Network.** Every report route is idempotent or read-only; a preview request lost mid-flight is asked again and returns the same PDF (decision 6).
3. **Lifecycle.** None on the phone. On the server, a worker killed mid-render leaves the job `running`; the claim logic of the label job (a conditional update, a stale `running` taken again) is reused.
4. **Data and loss.** The draft appears only after the phone's `visit.end` was applied (W14); a phone that has not synced has no draft yet, and the **Sync** page says so: "Your report is made once the visit has synced." Nothing is deleted on the phone because of a report. The draft's facts come from the server's board, so an element still queued on a phone is not in the draft and a later sync refreshes it (decision 4).
5. **Storage.** Not on the phone. Server: draft PDFs are purged after seven days (decision 6); finals are kept for ever.
6. **Caching.** The service worker still caches no API response and no PDF; the viewer asks for a fresh ten-minute link each time. No new precached file (the budget is 29 of 30; the Report section joins the `app` chunk; pdf.js stays out of the precache, finding F17).
7. **Security.** A draft is staff-only in the repository layer (rule 6); the facts hold no email or phone of any person; the preview link is presigned for ten minutes and made after a scoped read (rule 4: out of scope is 404). CSP unchanged (the viewer's worker is bundled; no `frame-src` is needed because nothing is framed).
8. **Proof.** Python: the consumer (a redelivered `visit.ended` adds nothing; element events refresh facts and keep the narrative), the render job against a fake renderer and against the real WeasyPrint where Pango exists, the cron with `ManualClock`, `report-facts` contract and scoping tests, the matrix, the event contract. The visual baseline in CI. Playwright: a technician ends a visit and finds the draft and previews it (slice 4). Real devices: **the W15 field-test visits produce drafts** if slice 2 is deployed first (question 3): a free check that sync → draft works from a phone.

## 7. Tests and exit checks

- **Exit (IP):** a draft PDF is ready within 10 minutes of sync. Measured on staging with a visit ended from a phone (or by API) and written down.
- **Backfill:** a run against staging twice gives the same counts; a row that a live event already made is not overwritten by an older snapshot.
- **Draft:** the consumer is idempotent; two quick `visit.ended` deliveries make one draft; an ended visit with no elements still produces a draft ("No work recorded"); a failed media file is listed, not fatal.
- **Template:** the baseline images; text assertions; a station in another time zone; a long station list paginates; 30 photos go six per station and the rest in the appendix; a video shows a QR.
- **Access:** viewer reads, technician not attending 404, client 404 for a draft (matrix).
- **Docs site:** status and badges, the report routes, the `reports` and read-model schemas, `report.drafted`, settings (`REPORT_DRAFT_WAIT_S`, `REPORT_DRAFT_PURGE_DAYS`, the Kafka keys), decisions W16-1 to W16-12, a changelog entry, and the P6 charts still on the list: the **draft report sequence** (visit.ended → draft → render), the **report state** (draft, finalizing, final, superseded; the first transition built), the **read-model rebuild** data flow, and a **document flowchart** of the visit report (sections and who writes them). Documents: TRD §3.4 and §8.6 (as built; the backfill wrapper), PRD Appendix A (as the board), BSD (report collections), TP (consumer and baseline tests).

## 8. Questions for you

1. **Q1: branding and numbering.** Do you have the logo and colours the reports should carry, and is `VR-YYYY-NNNN-NN` plus a version the right number? Default: the MARS-MMS mark and colours, the visit's ref as the number, "v1" as the version.
2. **Draft timing (decision 5).** Render the draft PDF by itself when the visit's media is ready (or after five minutes), or only when someone asks for a preview? Default: **by itself**: the exit criterion says a draft PDF is ready within 10 minutes.
3. **Deploy slice 2 before the field day?** Default: **yes**, it costs nothing and the field visits then produce drafts, which tests sync → draft from a real phone. The risk is small (it only adds a consumer and a collection); the alternative is to keep the field day on the 0.5.0 build only. The field-test visits are on real stations: their drafts stay staff-only, like their notes.
4. **Photos in the body.** Up to six images per station, Before and After pairs first (TRD §11.1), the rest in the appendix. Default: as written. Alternative: put every photo in the appendix and none in the body until the technician chooses (W17).
5. **Visual regression.** Raster baselines in CI with a 0.5% tolerance, plus text assertions. Alternative: text and structure assertions only (less brittle, shows nothing about the look). Default: both.
6. **Boards for W17.** Draw the editor, signature pad and finalize screens ("AWS-MMS W17 screens", phone and desktop, light and dark) during W16 so W17 can start building straight away, or wait until W17 begins? Default: **draw them in W16**, after slice 4's boards are approved.
7. **Retention of draft PDFs.** Seven days for older draft versions, finals for ever. Default: as written.
