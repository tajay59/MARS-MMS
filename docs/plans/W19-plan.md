# Phase 7 · W19 plan: summary reports and CSV, dashboards, the audit viewer and History tab (J10)

Proposed 2026-10-28, while the W18 pull requests (#100 to #106) are being merged. Questions are in section 8; slices 1 to 3 have no screens and can start first. Slices 4 and 5 need approved boards.

Delivers SUM-1 to SUM-6 (eleven summary reports as PDF and CSV, the client-run versions, the three role dashboards), CAL-4 (the Calibration due report and widget), CAL-6 (failed calibrations on the admin dashboard), AUD-4 to AUD-6 (search and CSV export, the integrity check, the staff-only History tab) and the NFR-2 check for summaries (ready within 2 minutes). Journey J10 works end to end.

**Not in W19** (it is W20): the production stack with monitoring and alerts, backups and the restore test, the security review, the load test. W19 only leaves them what they need: the integrity check writes a result and a metric that W20 alerts on. Also not here: RPT-11 and integrations (later), a certificate (PAdES) signature, any offline work for these pages (OFF-10).

## 1. Where things stand (checked 2026-10-28)

- **platform, audit:** `domain/audit.py` (`to_record`, `chain`, `first_break`) and `repo/audit.py` (`append`, `verify`) exist and the chain is verified by tests and on staging. **There is no read API**: no search, export, history or verify route (`app/api/` holds only `notifications.py` and `ws.py`). Migration `audit/0001_audit.py` has the unique `seq` index and indexes on `(resource…)`, `(actor.user_id, at)`, `(action, at)` and `(org_id, at)`; paging by `seq` newest first needs `(…, seq)` variants, added in slice 1.
- **report, read model:** four collections are built and backfilled from operations' snapshots (W16): `station_facts`, `request_facts`, `visit_facts`, `calibration_facts`. Missing for the summaries: `sensor_events` (TRD §5.4, waits for Phase 7), what is installed now at each station, configuration versions, and who a request is assigned to. There is no `GET /dashboard` and no `POST /reports/summary`. `report_jobs` exists and the label sheet uses it; `GET /reports/jobs/{id}` is the requester-only status and link route.
- **report, image:** WeasyPrint with Pango; **no headless Chromium yet** (TRD §11.1 and R9 say it arrives in this phase).
- **frontend:** `DashboardPage.vue` is a first page (greeting, `MyVisits`, a next-step card). `/reports` and `/admin/audit` are `later(…, 7)` placeholders; the Reports rail item and the Audit log admin item already exist. **ApexCharts is not installed** (`vue3-apexcharts` is not in `package.json`) and `frontend/src/charts/` does not exist, so slice 4 adds the dependency and `charts/presets.ts` (and the report image's chart page is built from the same preset). **The precache is at 29 of 30 files (F14).**

## 2. Order of work

Five slices, each its own branch and pull request.

| Slice | Branch | What | Size |
|---|---|---|---|
| 1 | `feat/p7-w19-audit-api` | Platform: `GET /audit/events`, `export.csv`, `GET /audit/resources/{type}/{id}`, `POST /audit/verify` and `GET /audit/checks/{id}`, the nightly check, the indexes, the staff view of a record | M |
| 2 | `feat/p7-w19-read-model` | Report: the missing read-model collections and consumers, backfill from snapshots, `GET /dashboard?view=`, the 60 s cache | L |
| 3 | `feat/p7-w19-summaries` | Report: `POST /reports/summary`, the eleven types, CSV, Chromium charts in the image and the worker, templates, visual baselines | L |
| 4 | `feat/p7-w19-dashboards` | Frontend: the three dashboards, the Calibration due widget, lazy ApexCharts | M |
| 5 | `feat/p7-w19-reports-audit` | Frontend: `/reports`, `/admin/audit`, the History tab on station, request and visit pages; Playwright J10 | L |

Slices 1, 2 and 3 are independent of each other except that 3 uses the collections of 2. Slices 4 and 5 need boards approved first and need 2 or 3 and 1. Slices 1 and 2 touch files W18 also changed (platform's consumer list, report's consumer wiring): build them on `main` after the W18 merges.

## 3. Decisions (proposed W19-1 to W19-12)

1. **Audit reads are in platform and admin-only, except History.** `GET /api/v1/audit/events?actor=&action=&resource_type=&resource_id=&org_id=&from=&to=&cursor=&limit=` (limit at most 100, newest first by `seq`, cursor is the `seq`). One record is returned whole (actor with IP, user agent and device, before and after, correlation id) to admins only.
2. **History shows less.** `GET /api/v1/audit/resources/{type}/{id}` (type is `station`, `request` or `visit`) is for staff including the Viewer, and returns time, actor name and role, action in words and the **names** of the fields that changed. IP, user agent, device, correlation id and the before and after values are not sent (they can hold personal data and staff-only text). A client is refused as on every staff route. A request's History also lists its visits', comments' and reports' records through `metadata.request_id`; `domain/audit.py` does not mention `request_id` today, so slice 1 checks what an event's record keeps in `metadata` and adds `request_id` to `to_record` if it is missing (older records without it simply do not appear under the request). [Question 2.]
3. **CSV is safe to open in a spreadsheet.** Every text cell that starts with `=`, `+`, `-`, `@`, tab or carriage return gets a leading apostrophe, in the audit export and in the summary CSVs (one function in `mms_common`). Files are UTF-8 with a BOM for Excel, dates are ISO 8601 UTC, and the export is streamed with a cap of 50,000 rows. [Question 7.]
4. **The integrity check is a job and also a habit.** `POST /api/v1/audit/verify` (admin) queues a check that reads the chain in pages and answers with `audit_checks/{id}` `{status, checked, first_break_seq, started_at, finished_at, by}`; the page polls. A nightly run (Redis-locked, like the digest) records the same, and sets the gauge `audit_chain_ok` that W20 alerts on. A break is shown as the sequence number of the first bad record and nothing else (no record content).
5. **Looking at the audit trail is itself recorded.** An export and a check each append a record (`audit.exported`, `audit.verified`: who, filters, rows, result) in the platform's own transaction. The chain stays insert-only (rule 10). [Question 8.]
6. **The read model learns what the summaries need and nothing is asked of another service when a report runs** (TRD §11.1). Added to `report`: `sensor_events` (from `sensor.installed` and `sensor.removed`, TRD §5.4), `unit_facts` (the unit, model, serial, parameter, station, installed since, next calibration due), `config_facts` (station, version, date, visit, file count) and `assigned_ids` on `request_facts`. Each keeps its `aggregate_version`, is filled by events and rebuilt by `python -m app.cli backfill` from operations' snapshots. Whether configuration versions have a snapshot today is checked at the start of slice 2 and, if not, one is added to operations (`/internal/snapshot/config_versions`).
7. **Dashboards are figures from the read model, computed on request and cached 60 seconds in Redis** per role and organization. `GET /api/v1/dashboard?view=admin|technician|client` defaults to the caller's own view; a client asking for another view is refused, a Viewer gets the admin view. A client's figures are filtered by the token's organization in the repository, never from a parameter (rule 3). Two figures are not the read model's and stay out of that route: **registrations pending** (auth; the admin page uses auth's existing count) and **visits waiting to sync** (this phone's own IndexedDB, never the server).
8. **Summary reports are jobs, not numbered documents.** `POST /api/v1/reports/summary` `{type, format: pdf|csv, from, to, org_id?, country?, station_ids?, due_in_days?}` answers 202 with a `report_jobs` record (type `summary`); the worker stores `summaries/{job_id}.pdf|csv` in `mms-reports`; `GET /api/v1/reports/jobs/{id}` (requester only) gives a ten-minute link; `GET /api/v1/reports/jobs?type=summary` lists the requester's jobs of the last 30 days for the page. A summary has no report number, no version and no signature, and `verify` does not find it; every page carries "Generated <time> by <name>, <filters>" in the footer. A repeat request with the same parameters inside a minute returns the same job. [Question 5.]
9. **A client's three types are forced on the server.** Clients may ask for Station history, Station asset and Client activity (SUM-3). The organization comes from the token, the station list is checked to belong to it (a station of another organization is 404), and the other eight types are refused. Staff and the Viewer may run all eleven (Technician workload included for every staff role: [Question 3]). The Viewer never creates anything else (rule 5): running a report is a read, so it is the one POST a Viewer may make; the authorization matrix says so explicitly.
10. **Period boundaries are in one zone.** `from` and `to` are dates; a month starts at 00:00 in `REPORT_SUMMARY_TIME_ZONE` (default `America/Jamaica`, as the weekly digest), stored times are UTC (rule 8), and times inside a table are printed in the station's zone when the row is about one station and in this zone otherwise, with the zone named in the header. [Question 4.]
11. **Charts are ApexCharts in one headless Chromium** (TRD §11.1, DBD D3): the worker starts one browser, loads a standalone chart page built from `charts/presets.ts`, renders each chart in the light palette, exports SVG and embeds it. A chart that fails or takes over 30 s is left out with a note and its table still prints. The cost (image size, worker memory against the 1.5 GB budget) is measured in slice 3 and written down. [Question 6.]
12. **Access matrix.** New rows: the five audit routes (admin; History staff and Viewer; a client is refused), `POST /reports/summary` (staff, Viewer, client with the limits above), `GET /reports/jobs` and `/jobs/{id}` (requester only; another user gets 404), `GET /dashboard` (each view by role). The two new consumers' routes are internal. The audit records of the new events are in PRD AUD-1's list.

## 4. Back end

| Where | What |
|---|---|
| platform | `api/audit.py`, `domain/audit_view.py` (the staff view of a record, the words for an action, the changed field names; pure), `repo/audit.py` (`search`, `history`, `stream`; new indexes `(resource.type, resource.id, seq)`, `(actor.user_id, seq)`, `(action, seq)`, `(org_id, seq)` in an `audit/0002` migration), `jobs/audit_check.py` (the job and the nightly run), `audit_checks` collection and a migration, `audit.exported` and `audit.verified` as records the module appends itself |
| report | `domain/dashboard.py` (figures per view; pure functions over rows), `repo/dashboard.py` (aggregates, org-scoped), `domain/summary/{station_history,station_asset,config_history,client_activity,turnaround,workload,reliability,calibration_due,network_status,monthly}.py` (one module per type: parameters in, `Table` and chart specs out; `monthly` serves both Monthly and Annual), `domain/csv.py` (the safe cell, shared via `mms_common.csv`), `repo/summary.py`, `jobs/summary.py`, `charts/` (the standalone page, built from the frontend preset), `templates/summary_*.html.j2` and `print.css` additions, migrations for the new collections and indexes |
| operations | Only if slice 2 finds a gap: a snapshot for configuration versions and the `assigned_ids` on the request snapshot and events |
| mms_common | `csv.py` (safe cells, BOM), event schemas only if a new field is added |
| infra | Chromium in the report image (Playwright for Python, one pinned version), `REPORT_SUMMARY_TIME_ZONE`, a Nginx `limit_req` zone for `/audit/events/export.csv` and `/reports/summary` |

## 5. The summary reports (slice 3)

| Type | Who | Says | Main table (CSV) | Chart |
|---|---|---|---|---|
| Station history | staff, client (own) | What happened at each station in the period | one row per event: date, kind (visit, request, calibration, config, client report), reference, who, outcome | events per month |
| Station asset | staff, client (own) | What is installed now | station, parameter, model, serial, installed since, last calibration, next due | none |
| Configuration history | staff | Config versions per station | station, version, date, visit, files | versions per station |
| Client activity | staff, client (own) | Requests, visits and reports for an organization | one row per request: reference, category, status, dates, visits, rejections | requests by status |
| Request turnaround | staff | How long each step takes | one row per closed request: submitted to approved, assigned, first visit, review, closed | median and 90th percentile by category |
| Technician workload | staff | Assigned requests, visits, time on site, reports signed | one row per technician | visits per technician |
| Sensor reliability | staff | Installs, removals, failed calibrations and time installed per model | one row per model | failures per model |
| Calibration due | staff | Units overdue or due within N days (default 30) | station, unit, due date, days over | overdue and due counts by country |
| Network status | staff | Stations by status and country, last visit, open requests | one row per station | stations by status |
| Monthly and Annual maintenance summary | staff | Counts per month (or per year) | one row per month | requests, visits and closed per month |

Plain-text assertions in the tests: the title, the period and zone, the footer, no staff-only text, and for a client report **no** figure from another organization. Visual baselines are drawn in the `mms-report-visual` image as in W17 and W18.

## 6. PWA pre-flight (answers)

1. **Device.** Everything is online. The dashboards open on phones (staff in the field shell and clients), so tiles stack to one column and charts are lazy; a chart must also be readable without hover (touch). Downloads on iPhone open the PDF in the app's sheet (W16) or the browser's viewer; CSV goes through the share sheet or the downloads folder. **Real devices:** an iPhone and an Android phone open each dashboard and download a CSV (joins the postponed iPhone checks).
2. **Network.** A dashboard or report request that fails shows "Needs a connection" with a retry, never stale numbers; a job in progress is polled again when the app comes back (the requester's job list is server-side). Offline, the dashboard page still opens from the precached shell (AFD §5.2), shows the phone's own sync count from IndexedDB and `MyVisits` as it does today, and the server figures say they need a connection.
3. **Lifecycle.** A waiting service worker never applies while a report is being generated; the page registers busy for the few seconds of the request only, since the job runs on the server. Ten-minute links are asked again when opened.
4. **Data and loss.** Nothing is stored on the device and no outbox op is added. On the server a job that dies is picked up again (the `report_jobs` claim is conditional, as the label sheet); a summary is a pure function of the read model and its parameters, so a repeat draws the same file. The nightly check never writes to the chain except its own record.
5. **Storage.** No new local storage. Generated files are small (tables and a few SVG charts); the 30-day clean-up removes the file and the job record together.
6. **Caching.** No API answer and no PDF is cached by the service worker (TRD §7.6). **ApexCharts is large and new to the app:** it is imported with `import()` inside one `ChartCard` component, that component's module is excluded from the `app` group in `vite.config.mts` and added to `globIgnores`, exactly as Leaflet and `qrCode.ts` are, so the precache stays at 29 of 30 files (F14). A test asserts the count. Dashboard and report figures are held in memory only.
7. **Security.** Org scoping in the repository for every dashboard and summary query, 404 outside scope, the client types and organization forced from the token (decision 9), CSV formula injection closed (decision 3), no personal data in History for non-admins (decision 2), exports rate-limited and recorded in the chain. The report image gains a browser: it runs with no network, loads only the local chart page, and its output is SVG that is escaped before it is embedded.
8. **Proof.** Python: each summary type as a table over made-up read-model rows (empty period, one row, many, two organizations), the client limits for every type and a station of another organization, the dashboard figures per view with a client leak check (`find_leaks`), the cache keyed by role and organization, CSV cells that start with each dangerous character, the chain check over a clean chain, a changed record, a deleted record and a reordered pair, the nightly run under `ManualClock`, History without admin-only fields. Playwright J10 (generate, download PDF and CSV, search the audit log, open a record, export, run the check, the History tab on a station and a request), axe in light and dark, the precache count. The 2-minute target is measured with a year of generated rows on staging and written down.

## 7. Tests and exit checks

- **Exit (IP):** a Viewer and an admin run every summary report for real stations on staging and check the figures against what they know; each is ready within 2 minutes; the dashboards agree with the lists they summarize (a test compares each tile with the matching list query); the audit log can be searched and exported, the integrity check passes on staging's chain and fails on a deliberately altered copy in a test; the History tab works for staff and the Viewer and is absent for clients.
- **Staging release 0.7 (IP):** admins and a Viewer run summaries and check the dashboards; the W20 items (production stack, alerts, backups, restore test, security review, load test) close the release.
- **Docs site:** status and badges, the new routes, schemas (`audit_checks`, the four read-model collections, `report_jobs` of type `summary`), the new records and events, settings (`REPORT_SUMMARY_TIME_ZONE`, retention), decisions W19-1 to W19-12, a changelog entry, the phase's charts. Documents: TRD §3.4, §3.5, §5.4, §5.6, §11.1; PRD (nothing, unless a question changes it); AFD J10 and the dashboards as built; BSD (`audit_checks`, the read model, summary files); TP (the J10 and CSV tests).

## 8. Questions for you

1. **How many summary types first.** Default: all eleven, with Monthly and Annual last so a slip drops only them. Or a smaller first set for release 0.7.
2. **What the History tab shows staff.** Default: who, what, when and the names of the fields that changed; the values only in the admin's audit log. Or: show values too (a request's old and new title or status), at the cost of showing any text a record holds to a Viewer.
3. **Technician workload for every staff role.** Default: yes (PRD: staff and Viewers may run all). Or admins and Viewers only, so technicians do not see colleagues' workload.
4. **Month boundaries.** Default: `America/Jamaica` as a setting, as the weekly digest. Or each organization's own zone, which organizations do not have today (the station's is the nearest).
5. **How long generated summaries are kept.** Default: 30 days, then the file and the job record are deleted. Or keep them until the requester deletes them. (BSD's retention table gets the answer either way.)
6. **Charts.** Default: ApexCharts in headless Chromium as the TRD and DBD D3 decided, with the image size and memory measured in slice 3. Or draw the charts as SVG in Python, which avoids about 400 MB of image and a browser but gives two chart styles (dashboards and PDFs).
7. **Export size.** Default: at most 50,000 rows, asking for narrower filters beyond that. Or a background export job like a summary.
8. **Audit the audit.** Default: exports and integrity checks are recorded in the chain. Or not, to keep the chain to business events.
9. **Boards.** Draw the "AWS-MMS W19 screens" canvas (the three dashboards on desktop and phone, the Calibration due widget, the Reports page with the generator, the job list and a client's limited form, the audit log with filters, the record drawer, Export CSV and the integrity check result, the History tab; light and dark) and get it approved before slices 4 and 5? Default: **yes**, drawn while slices 1 to 3 are built.
10. **Order against W18.** Default: build slices 1 to 3 once the W18 pull requests are on `main` (they share consumer wiring and docs sections); draw the boards now.

## 9. Charts proposed for this phase

At the start of each phase the charts are suggested and you choose (CLAUDE.md). Proposed for W19, from the catalogue:

| Chart | Type | Shows |
|---|---|---|
| Summary reports: inputs to outputs | Logical model flowchart | Read-model collections to the eleven reports, the CSV table and the chart |
| Dashboard figures | Data flow | Events and snapshots into the read model, the 60 s cache, the three views, and the two figures that come from elsewhere (auth, the phone) |
| Summary job | Sequence | Page, report API, queue, worker, Chromium, storage and the polled link |
| Integrity check | Code flowchart | Branch by branch: page the chain, hash, first break, the result, the nightly run |
| J10 | Process flow | Generate and download, search and export, check, History |
| Who may do what with reports, dashboards and audit | Use case | Roles by action, mirroring the authorization matrix |
| Audit record, as built | ER | `audit_events`, `audit_state`, `audit_checks` and what each role sees of a record |

Each is drawn from what its slice built (never from the design), in the slice's own pull request or in one charts pull request before the phase closes, as in W17 and W18. The docs site's Diagram guide lists them under P7 when the first one lands.
