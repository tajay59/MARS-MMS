# Product Requirements Document (PRD)
## Automatic Weather Station (AWS) Maintenance Tracker

| Field | Value |
|---|---|
| Version | 0.1 (Draft) |
| Status | Draft — pending answers to open questions |
| Author | TBD |
| Last Updated | TBD |
| Target Release | MVP — TBD |

---

## 1. Overview

A web application for tracking maintenance of Automatic Weather Stations (AWS). It
enables **clients** to raise and track maintenance requests, and **staff** to
schedule, perform, and report on site visits. The system stores station metadata,
documentation, and media, and generates PDF reports.

---

## 2. Goals & Objectives

- Centralize AWS maintenance requests, visits, and station records.
- Give clients visibility into request status and a channel to confirm/dispute work.
- Enable field staff to capture visit evidence (photos/video/notes) on-site, including offline.
- Auto-generate standardized PDF visit reports.
- Store station config, datasheets, and manuals in one place.
- Provide reports and audit trail for admins.

### Non-Goals (MVP)
- Real-time sensor data ingestion from AWS.
- Calibration tracking (explicitly out of scope).
- Multi-tenant SaaS (single organization deployment).
- Mobile native apps (PWA only for MVP).

---

## 3. Users & Roles

### 3.1 Staff (internal to the organization)
| Sub-role | Description | Key permissions |
|---|---|---|
| Admin Staff | Oversees requests and users | Approve/deny requests, assign staff, manage stations, generate reports, view audit log |
| Instruments Staff | Field technicians | Create visits, upload media, log maintenance, generate visit reports |
| Dev Staff | Maintains the application | System-level access, logs, config |

- A staff member may hold **multiple sub-roles**.
- Staff accounts are **created by admins** (no self-registration).

### 3.2 Clients (external)
- Belong to **one** client organization.
- Self-register; join an existing organization via invite code / domain match.
- Can own/manage multiple AWS stations (if permitted by admin).
- Scope: can only see **their organization's** stations and requests.

> **Assumption (A1):** Each client organization is isolated from others; the
> deploying company is a single organization serving multiple client companies.

---

## 4. Definitions

- **Maintenance Request** — Client-initiated ticket. May span multiple stations and
  contain one or more site visits. Lifecycle ends when client confirms completion.
- **Site Visit** — A single journey to a site to perform work. Always belongs to a
  maintenance request.
- **Station (AWS)** — Automatic Weather Station. Has parameters, sensors, docs, configs.

---

## 5. Functional Requirements

### 5.1 Authentication & Authorization
- FR-AUTH-1: Local email + password login.
- FR-AUTH-2: Self-registration for clients.
- FR-AUTH-3: Password reset via email.
- FR-AUTH-4: Role-based access control (RBAC) per Section 3.
- FR-AUTH-5: Audit log of authentication events and key actions.

### 5.2 Station Management
- FR-STN-1: Store station info: name, type, owner/organization, parameters
  (flexible list with units), sensor models, lat, lon, elevation.
- FR-STN-2: Store documentation: datasheets, operational & maintenance manuals.
- FR-STN-3: Store configuration files, **versioned**.
- FR-STN-4: Generate a QR code per station; scanning opens the station view.
- FR-STN-5: Both admin staff and instruments staff can create/edit stations.

### 5.3 Maintenance Requests
- FR-REQ-1: Clients create maintenance requests.
- FR-REQ-2: Clients view status of their requests.
- FR-REQ-3: Lifecycle:
  `submitted → approved | denied → scheduled → in-progress (≥1 visit) → awaiting client confirmation → closed | reopened`
- FR-REQ-4: Admin staff approve or deny requests.
- FR-REQ-5: Requests can be assigned to a team and/or a specific staff member.
- FR-REQ-6: Requests have priority levels (urgent / normal / low) and SLA tracking.
- FR-REQ-7: A request may span multiple stations.
- FR-REQ-8: Clients see the overall request with a list of its visits (not separate tickets).
- FR-REQ-9: Clients may edit/cancel a request **before technicians arrive in country**.
- FR-REQ-10: On completion, clients confirm or dispute.
- FR-REQ-11: On dispute, clients submit reasons and may re-open the request.
- FR-REQ-12: Clients can comment on requests (threaded or flat — TBD) and attach PDFs.

### 5.4 Site Visits
- FR-VIS-1: Staff manually create a site visit under a request.
- FR-VIS-2: No site visit may exist without a parent request.
- FR-VIS-3: Explicit check-in and check-out actions timestamp and lock the visit.
- FR-VIS-4: Staff upload images/videos at start of visit.
- FR-VIS-5: Staff record maintenance carried out.
- FR-VIS-6: Staff upload images/videos at end of visit.
- FR-VIS-7: Staff can add notes/photos mid-visit.
- FR-VIS-8: Visit data must be capturable offline and synced when online.
- FR-VIS-9: Generate a PDF visit report from a template.

### 5.5 Reports
- FR-RPT-1: Auto-generate a PDF visit report.
- FR-RPT-2: Reports downloadable (not auto-emailed in MVP).
- FR-RPT-3: Client confirmation captured in the report (sign-off section).
- FR-RPT-4: Admin/client report generation on-demand.
- FR-RPT-5: Reports include: requests per month, avg time-to-resolution, visits
  per station, overdue requests, staff workload.
- FR-RPT-6: Export formats: PDF (primary). CSV/Excel (TBD — see Open Questions).

### 5.6 Media & Files
- FR-MED-1: Store images and videos from visits.
- FR-MED-2: Store documents (PDF) for stations and requests/visits.
- FR-MED-3: Client-submitted PDF reports attachable to a request, visit, or both.
- FR-MED-4: Local file storage on the deployment server.

### 5.7 Notifications
- FR-NOT-1: Email notifications on request status changes, visit completion, comments.
- FR-NOT-2: Real-time in-app updates (WebSocket) for comments and status.

### 5.8 Offline & Sync
- FR-OFF-1: Field staff can capture visits offline (check-in/out, media, notes).
- FR-OFF-2: Sync occurs automatically when connectivity is restored.
- FR-OFF-3: Conflict resolution strategy — TBD (see Open Questions).

---

## 6. Non-Functional Requirements

- NFR-1: Single-organization deployment; on-premise.
- NFR-2: Single Vue SPA for all roles.
- NFR-3: Expected scale: ~50 (units TBD — see Open Questions).
- NFR-4: Audit trail for all critical actions.
- NFR-5: Compliance/retention — TBD (see Open Questions).

---

## 7. Assumptions

- A1: Single deploying organization; clients belong to isolated client companies.
- A2: Staff accounts are admin-created.
- A3: Field devices support PWA installation (tablets/phones).
- A4: Local SMTP available for email.
- A5: No calibration tracking required.

---

## 8. Open Questions

1. Are client sub-roles needed (e.g., client admin vs. client viewer)?
2. How do self-registered clients join their organization (invite code, domain match)?
3. Single-tenant or multi-tenant — confirm interpretation of A1.
4. Can a station be owned by a client AND serviced by internal staff? (assumed yes)
5. Which UI libraries in production: Tailwind + Vuetify + PrimeVue? (recommendation: pick two)
6. Field device OS/browser targets for offline PWA.
7. What must work offline (capture only vs. view docs/configs)?
8. Offline conflict resolution: merge, prompt, or last-write-wins?
9. Scale clarification: "50" = stations, users, or requests/month?
10. Hardware: single server, cluster, or VM(s)?
11. Media volume estimate (GB/TB) — drives storage sizing.
12. Compliance/retention requirements.
13. Timeline and MVP boundary.
14. Report export formats beyond PDF (CSV/Excel?).
15. Comment model: threaded vs. flat; editable/deletable.
16. Kafka vs. Redpanda (on-prem operational simplicity).
17. Nginx vs. Kong roles at the edge.

---

## 9. Milestones (Proposed)

| Phase | Scope |
|---|---|
| M0 — Foundations | Auth, users, roles, station CRUD, audit log |
| M1 — Requests | Client request creation, admin approve/deny, status view |
| M2 — Visits (Online) | Visit creation, check-in/out, media upload, notes, PDF report |
| M3 — Offline | PWA offline capture + sync |
| M4 — Reports & Notifications | Reports dashboard, email + WebSocket notifications |
| M5 — QR & Polish | Station QR codes, UI refinements, docs library |

---

## 10. Success Metrics (Proposed)

- % of maintenance requests completed and confirmed within SLA.
- Average time-to-resolution per request.
- % of visits with complete start/end media evidence.
- Offline sync success rate.
- Client dispute rate.