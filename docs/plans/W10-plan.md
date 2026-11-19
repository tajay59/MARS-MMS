# Phase 4 · W10 plan: visits, request status from visits, checklist templates

Proposed 2026-10-21, waiting for your answers (section 7) and the mock-up boards (section 4). Nothing is built.

Delivers VIS-1 to VIS-4, VIS-8 (the template editor and which template applies), VIS-9 (the choice at the end of a visit), VIS-11 (clients see visits), the scheduling step of J5 (steps 3, 5 and 5b), ADR-17 (request status from visits) and the "Start visit" action. Depends on W8 and W9 (merged), and on Q5 (a starter checklist template) from you before slice 2 ends.

**Not in W10** (so it is clear where it goes): work records and sensor actions (W11), media on visits and the image and video pipeline (W11), the VIS-6 end rules, the field shell and the client's view of media (W12), `/sync` and the offline bundle (W13 to W14).

## 1. Order of work

Four slices, each its own branch and pull request. Slice 1 is the only one the others need; 2 does not depend on it.

| Slice | Branch | What | Size |
|---|---|---|---|
| 1 | `feat/p4-w10-visits-api` | Back end: the `visits` module in `operations` (domain, repo, routes, events, migration), `derive_status` wired to visits in the same transaction, request cancel cancels planned visits, release refused while visits exist, `/internal/snapshot/visits`. All the visit tests. | L |
| 2 | `feat/p4-w10-checklists` | Back end: `checklist_templates` (versioned), routes, `resolve`, the starter template (Q5). Front end: `/admin/checklists` list and editor. | M |
| 3 | `feat/p4-w10-visit-screens` | Front end: Schedule visit, `/visits/:id` (staff and client views), Reschedule, Cancel, Change owner, the online lifecycle controls (Start, Arrive, Depart, End), the Visits tab in Work, "My upcoming visits" on the dashboard, a Visits tab on the request page. Playwright J5. | L |
| 4 | `feat/p4-w10-visit-notifications` | Platform: recipient rules, emails and live updates for the visit events (Appendix B rows), preferences for the new types. | S |

Slices 1 and 2 touch only `operations` and the front end's admin area, so they can go in parallel. Slice 3 needs slice 1's API. Slice 4 needs slice 1's events.

## 2. Decisions to approve (proposed W10-1 to W10-12)

1. **A visit is a document in `site_visits`** (TRD §5.4 shape), reference `VR-YYYY-NNNN-NN`: the request's number and a two-digit visit number from a counter keyed by the request. Created with a device-made `id` (rule 9), idempotent like requests (W8-4): a retry returns the same visit with 200. Times are stored in UTC (rule 8). The form takes dates in the **first station's time zone** (shown beside the fields); each station on the visit page shows its own local time.
2. **The visit state table is one table**, as W8-1: `domain/visits/state.py` holds the allowed moves (planned to started, planned to cancelled, started to ended, cancelled to planned by restore), who may make each, and nothing else decides. A move that is not a row is a 409 for everyone.
3. **Who can do what (VIS-1, ADR-18).** The request's assigned staff or an admin schedule. Attending staff are any active technicians or admins (checked through auth's lookup, the W9 `StaffApi`), one of them the **lead**; each station has an **owner** chosen from the attending staff (the lead by default). While planned, any of the scheduler, the attending staff or an admin edits dates, staff, lead, stations, owners and notes. Once started, only owners change, by the lead or an admin. Viewers never mutate (rule 5).
4. **Assigned staff and attending staff are separate lists.** `assigned_staff` on the request stays what Assign and Claim set (the people responsible); attending staff belong to a visit. A client sees both by name (A7, D4): never an email or phone number.
5. **A station can be in only one live visit of a request at a time** (planned or started). Parallel visits are for different stations (two teams, two islands). A second live visit on the same station answers 409 `station_in_other_visit`. Without this, two owners could record on one station, which ADR-18 exists to prevent. (Question 2.)
6. **Request status is derived in the same transaction as every visit change.** One function, `recompute(request, visits)` in `operations/domain/requests`, calls the existing `derive_status` and writes the status, the `status_history` entry, the milestones (`first_visit_at` on the first start) and `request.status_changed` through the existing outbox path (rule 2). It runs only while the request is in a derived status (Assigned, Scheduled, In progress, Client review); `report_status` is `none` until Phase 6, so a finished visit with no more visits needed waits in In progress, as the table says.
7. **Cancelling and releasing.** An admin cancelling a request cancels its planned visits in the same transaction (TRD §3.2.2); a started visit is left alone. **Release is refused while the request has any live visit** (409 `has_visits`): without that, a technician could send a request with a booked visit back to the queue. This closes a gap in W9.
8. **The lifecycle functions are written for sync.** Start, arrive, depart and end are pure functions in `domain/visits/` that take the actor, the state and an `at` time, and return the new state or one of the TRD §7.4 conflict codes (`not_owner`, `locked`, `visit_cancelled`, `already_ended`). The routes call them now; `/sync` calls the same functions in W14, so there is one rule. A repeat of the same move by the same person (a lost response, then a retry) is a 200 with the same state, not an error. `at` is the device's time: accepted when it is at most 5 minutes in the future and 30 days in the past, else 422.
9. **Arrival and departure get routes now** (`POST /visits/{id}/stations/{sid}/arrive` and `/depart`, owner or admin). The TRD lists none because W11's work-record save was going to carry them; the field's Arrive button (J6 step 3) needs one first. Depart before arrive is a 409. **End in W10 is the lifecycle only**: `additional_visit_required` and `follow_up_notes` (required when true) move the request; the VIS-6 check (a Before and an After image per station, or an override with a reason) needs media on visits and lands in W12 through the `overrides[]` field the route already accepts.
10. **Clients see visits of their own organization's requests** (VIS-11) with dates, status, stations, lead and attending staff by name, and the time each station was arrived at and left. They never see the visit's `notes`, `prepared_on`, work records or media (media and finalized reports arrive with W12 and Phase 6). Filtered in `repo/` (rule 6); another organization's visit is 404 (rule 4).
11. **Checklist templates are immutable versions.** `PATCH` writes a new version of the same template (`version + 1`, same `family_id`) and leaves the old rows, so a visit that copied version 3 keeps meaning version 3. Templates are per station `type` (exact match, one active per type) with optional **sensor-model add-ons**: for each model installed at the station that has an active add-on, its items join the list under "Sensors". `GET /checklist-templates/resolve?station_id=` returns what would apply. The copy into a visit's work record is W11; W10 builds the editor and the resolution.
12. **Only admins write templates; staff read them** (TRD route table). A template cannot be deleted, only made inactive.

## 3. Back end

### operations (slices 1 and 2)

New routes (all in `tests/api/test_authorization_matrix.py`; paths and roles from TRD §3.2, additions marked **new**):

| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/api/v1/visits` | assigned staff, admin | `{id, request_id, planned_start, planned_end, staff_ids, lead_staff_id, stations:[{station_id, owner_staff_id?}], notes?}`; request must be Assigned, Scheduled or In progress; Section 2 items 1, 3 and 5; request becomes Scheduled |
| GET | `/api/v1/visits/mine` | technician, admin | my upcoming and active visits, soonest first |
| GET | `/api/v1/visits` | any in scope | `request_id`, `staff_id`, `from`, `to`, `status`; clients get their organization's, with Section 2 item 10 |
| GET | `/api/v1/visits/{id}` | any in scope | the visit with stations, owners and staff names |
| PATCH | `/api/v1/visits/{id}` | see item 3 | planned: everything; started: `stations[].owner_staff_id` only (lead or admin); sends `visit.rescheduled` or `visit.station_owner_changed` |
| POST | `/api/v1/visits/{id}/cancel` | scheduler, attending staff, admin | planned only; `{reason?}` |
| POST | `/api/v1/visits/{id}/restore` | admin | cancelled to planned (built now, used by sync in W14) |
| POST | `/api/v1/visits/{id}/start` | attending staff | `{at?}`; planned to started; request In progress |
| POST | `/api/v1/visits/{id}/stations/{sid}/arrive` | station owner, admin | **new**; `{at?}` |
| POST | `/api/v1/visits/{id}/stations/{sid}/depart` | station owner, admin | **new**; `{at?}` |
| POST | `/api/v1/visits/{id}/end` | attending staff | `{additional_visit_required, follow_up_notes?, overrides?, at?}`; started to ended |
| GET | `/internal/snapshot/visits` | service | backfill for the report read model |
| GET | `/api/v1/checklist-templates` | staff | list (active, or all with `?all=true`, admin) |
| POST | `/api/v1/checklist-templates` | admin | `{name, station_type, sensor_model_id?, items:[{id, label, help?}]}` |
| PATCH | `/api/v1/checklist-templates/{id}` | admin | new version; or `{active:false}` |
| GET | `/api/v1/checklist-templates/resolve` | staff | **new**; `?station_id=`, Section 2 item 11 |

`actions` on the request detail gains `schedule_visit` (assigned staff or admin, status Assigned, Scheduled or In progress). The detail already promises "a visit summary" (TRD): it gets `visits: [{id, ref, status, planned_start, planned_end, lead}]`.

Events (schemas in `mms_common.events.operations`, audit mapping updated; the TRD §8 names, keyed by `request_id`, each written in the same transaction as the change):

- `visit.scheduled`, `visit.rescheduled`: `visit_id, request_id, planned_start, planned_end, staff_ids, lead_staff_id, station_owners`.
- `visit.cancelled`, `visit.restored`: `visit_id, request_id`.
- `visit.started`: `visit_id, request_id, started_at`.
- `visit.ended`: `visit_id, request_id, station_ids, additional_visit_required, overrides`; `sensor_actions` and `config_versions` stay empty until W11 (optional fields, so version 1 holds).
- `visit.station_owner_changed`: `visit_id, station_id, from, to`.
- `visit.station_arrived`, `visit.station_departed` (**new**, audit only): `visit_id, station_id, at`.
- `request.status_changed` as built; every visit event also carries `title`, `ref` and `org_id` for the notification text (the W9 rule).

Collections and indexes (migration `NNNN_visits`): `site_visits` (TRD §5.4) with `(request_id, planned_start)`, `(staff_ids, planned_start)` and `(status, planned_start)`; `counters` rows `VR-YYYY-NNNN`. `requests` gains nothing new: `first_visit_at` is already a milestone. Slice 2 adds `checklist_templates {_id, family_id, name, station_type, sensor_model_id, version, items, active, created_by, created_at}` with `(station_type, active)`.

Layers, as for requests: `app/{domain,repo,api}/visits/` (`state.py`, `schedule.py` for the rules in items 3 and 5, `lifecycle.py`, `owners.py`), `app/events/publish.py` gains the visit emitters, `domain/requests/recompute.py` is new. `domain/` has no FastAPI, Mongo or Kafka imports (rule 7).

### platform (slice 4)

`domain/notifications.plan()` grows the Appendix B rows that exist now. Each is one more `match` branch and a row in the table-driven test:

| Event | Told | Channel |
|---|---|---|
| `visit.scheduled`, `visit.rescheduled`, `visit.cancelled` | the client who made the request, and every attending staff member | in-app and email |
| `visit.ended` | attending staff | in-app ("Visit ended"; the "draft report ready" wording waits for Phase 6) |
| `visit.station_owner_changed` | the old and the new owner | in-app |

The person who did it is never told (W9-11). New preference types: `visit.scheduled` (scheduled and rescheduled), `visit.cancelled`, `visit.ended`, `visit.owner_changed`; the preferences screen lists the first two for clients and staff, the others for staff. `entity.updated` gains `kind: visit` for every visit event, to staff and to the organization's users, so an open request page and an open visit page refetch.

## 4. Front end

Mock-up boards to draw and get approved before slice 3 (the "AWS-MMS W10 screens" canvas, light and dark where it matters):

1. Schedule visit, desktop dialog and phone sheet: dates, staff with a lead star, stations with an owner each, notes.
2. `/visits/:id` planned, staff view: status chip, dates in station time, staff, a station row per station with its owner, Reschedule, Cancel visit, Start visit.
3. `/visits/:id` started: Arrive and Depart per owned station, read-only rows for other people's stations ("Owned by Devon Brown"), End visit.
4. `/visits/:id` client view: dates, stations, names only, no notes.
5. Reschedule and Cancel dialogs, with the warning for a visit that is prepared on a phone (J5 step 5). The warning text is built; the "prepared on" data arrives in W13.
6. Change owner dialog (J5 step 5b).
7. End visit dialog: Another visit needed? Yes asks for notes on what remains.
8. The request page: the Visits tab and the "Schedule visit" action.
9. Work › Visits: my upcoming visits as a table, cards on phones; the same widget on the dashboard.
10. `/admin/checklists`: list by station type, and the editor with items you can reorder, an Inactive switch, and "New version" on save.
11. Notification rows and the visit scheduled email.

New files, following the layout:

- `features/visits/`: `VisitsPage.vue` (the tab and the list), `VisitPage.vue`, `ScheduleVisitDialog.vue`, `RescheduleDialog.vue`, `CancelVisitDialog.vue`, `ChangeOwnerDialog.vue`, `EndVisitDialog.vue`, `StationRow.vue`, `StaffPicker.vue` (taken from `AssignDialog`, which keeps using it), `visits.ts` (labels, time-zone formatting through `app/format.ts`), `useVisitActions.ts`.
- `features/admin/checklists/`: `ChecklistsPage.vue`, `TemplateEditor.vue`.
- `src/api/operations.ts` gets `visitsApi` and `checklistsApi`; types come from the regenerated `openapi/operations.json`.
- Navigation: Work gets a **Visits** tab after Requests, for staff and clients. The visit record opens in the URL (`/visits/:id`), the list sits in the pane, as requests do. Admin gets **Checklist templates**.
- The visit page carries the lifecycle buttons for now. W12 moves Start, Arrive, Depart and End into the field shell (`/visits/:id/field`); the API and the rules stay.

## 5. PWA pre-flight (answers)

1. **Device.** Scheduling, rescheduling, cancelling and changing an owner are online-only (OFF-10, AFD §5.2): offline they say "This needs a connection" and keep the form. Start, arrive, depart and end are offline work in Phase 5, so their domain functions and routes are built for that now (item 8), but W10 gives them no Dexie or outbox code. iOS and Android behave the same here: nothing in this slice uses a browser feature.
2. **Network.** Every write is idempotent: create by the device-made `id`, the lifecycle moves by "same move, same person, same state is 200". A response lost mid-request and retried changes nothing.
3. **Lifecycle.** A waiting service worker never reloads a page with an open schedule form; the existing update prompt rules apply. Forms use `useFormDialog` so a dirty form asks before it closes.
4. **Data and loss.** Nothing enters the outbox or Dexie in W10. `at` is stored as the device sent it (within limits), so a visit started offline in W14 keeps its real time.
5. **Storage.** No new IndexedDB or cache use.
6. **Caching.** The service worker still caches no API response. `/visits/:id` is a client route inside the precached shell.
7. **Security and shared devices.** The client view is filtered in the repo layer, not the screen. Nothing of a visit is kept after logout beyond what the existing stores empty.
8. **Proof.** Vitest for the labels and time-zone formatting; domain tests for every move; Playwright J5 (below); the real-device proof for offline use is W14.

## 6. Tests and the exit checks

- **Domain:** the state table (every move and every refusal), owners and lead rules, the station-in-another-visit rule, `at` bounds, idempotent repeats, `recompute` for every row of `derive_status` through real visits (two parallel visits, a cancelled one, another visit needed, a finished visit with no more needed).
- **API** with real Mongo and Redis: matrix entries for every route, viewer 403, client on staff routes 404, client on another organization's visit 404, a client's visit response has no `notes`.
- **Exit check 1 (parallel visits).** Two visits on different stations of one request: request Scheduled when the first is planned, In progress when either starts, Assigned again after both end with "another visit needed", cancelling the last planned visit returns Scheduled to Assigned. Every change is one transaction with its `request.status_changed`, and the audit chain has them.
- **Exit check 2 (owners).** Only the owner arrives, departs and (in W11) edits the work record; the lead changes an owner after the start; both owners are told; a station in two live visits is refused.
- **Exit check 3 (release and cancel).** Release is refused with a live visit; cancelling the request cancels its planned visits and leaves a started one.
- **Playwright J5 end to end:** a technician claims, schedules a visit with a colleague as lead and two stations with different owners, the client sees the dates and the names; the lead starts it, the owners arrive and depart, the lead ends it saying another visit is needed, and the request is Assigned again; axe in light and dark on every new screen and on `/admin/checklists`.
- Review: `web-design-guidelines` on each new screen, `writing-guidelines` on the copy, the visit email and the starter template.

## 7. Questions for you

1. **Q5, the starter checklist template.** The PRD default is that one is provided. Do you have your own list, or may I draft one from a typical automatic weather station site visit (section 9 proposes twelve items) for you to correct?
2. **One live visit per station.** Item 5 stops two overlapping visits on the same station. Right, or do you need two teams on one station (for example a calibration team and a comms team the same day)? If yes, the rule becomes a warning and ownership stays one per station per visit.
3. **Assigned and attending staff stay separate** (item 4). Or should scheduling a visit add its attending staff to the request's assigned staff, so "who is on this request" is always one list?
4. **Time zones.** Dates are entered in the first station's time zone (item 1). For a visit across two zones, is that acceptable, or should the form ask?
5. **What a client sees.** Item 10 hides the scheduling notes and, until W12, media. Should clients also see **follow-up notes** (the remaining work after a visit ends)? The default is yes, since the status says "another visit needed" and they will ask why.
6. **A Visits tab in Work.** AFD lists `/visits/:id` only; "My upcoming visits" is a dashboard widget. I propose the tab as well (a list to switch between, as Requests has). OK?
7. **Templates by station type.** Stations have a free-text `type`. Template matching is exact on it. Do you want a fixed list of station types, or keep it free text and match what is typed?

## 8. Developer docs site (updated at the end of each slice)

Decisions W10-1 to W10-12, routes, events, collections, the visits and checklists sections, the changelog and the status badges. Charts for Phase 4 in this week (the sensor-action and media charts belong to W11):

1. State: a visit's status and what changes it (planned, started, ended, cancelled, restore).
2. Sequence: scheduling a visit, one transaction (visit, status derivation, outbox, then platform and the client's page).
3. Decision tree: who may change this visit or this station (scheduler, attending, owner, lead, admin; planned versus started).
4. Event storming: visit and request events, consumers and read models.
5. Code flowchart: `recompute` and `derive_status` wired to visits, branch by branch (an update to the existing decision tree).
6. Product flowchart: template versions (a PATCH writes a version; a visit keeps the version it copied).

## 9. Starter checklist template (proposal for question 1)

Station type "AWS" (one list for any automatic weather station; edit freely in the editor):

1. Site access and security: fence, gate, lock, signs
2. Mast or tower: condition, guy wires, corrosion, grounding
3. Vegetation and obstructions around the sensors
4. Enclosure: seals, desiccant, water inside, pests
5. Power: solar panel clean and angled, battery voltage, charge controller status
6. Datalogger: clock against a reference, program name, memory
7. Communications: signal strength, SIM or antenna, last successful upload
8. Each sensor: mounted level, clean, cable and connector, reading plausible against a reference
9. Rain gauge: funnel clear, level, tipping bucket moves freely
10. Data downloaded (and the period) or confirmed as sent
11. Photos: before, after, and any damage
12. Anything left to do on the next visit
