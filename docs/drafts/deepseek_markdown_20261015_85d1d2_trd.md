# Technical Requirements Document (TRD)
## Automatic Weather Station (AWS) Maintenance Tracker

| Field | Value |
|---|---|
| Version | 0.1 (Draft) |
| Status | Draft — pending answers to open questions |
| Author | TBD |
| Last Updated | TBD |

---

## 1. Purpose

Define the technical architecture, stack, data model, APIs, and operational
requirements for the AWS Maintenance Tracker, aligned with the PRD.

---

## 2. Architecture Overview

- **Style:** Microservices, event-driven (Kafka-based).
- **Deployment:** On-premise (single organization), containerized.
- **Edge:** Nginx (reverse proxy / static SPA) + Kong (API gateway).
- **Client:** Single Vue SPA (all roles), PWA-capable for offline field use.
- **Async backbone:** Kafka (or Redpanda — see Open Questions).
- **Storage:** MongoDB (data), local filesystem (media/docs).

### 2.1 High-Level Diagram (Textual)

    [ Vue SPA (PWA) ]
            |
        [ Nginx ]
            |
        [ Kong API Gateway ]
            |
    ┌───────┴───────────────────────────────────────────────┐
    │  Auth | Stations | Requests | Visits | Media |         │
    │  Reports | Notifications | Audit                       │
    └───────┬───────────────────────────────────────────────┘
            |
        [ Kafka ]
            |
    [ MongoDB ]   [ Local File Store ]   [ SMTP ]

---

## 3. Technology Stack

| Layer | Choice |
|---|---|
| Frontend | Vue 3, Vuetify, PrimeVue, Tailwind CSS |
| Backend | FastAPI (Python) |
| Database | MongoDB |
| Messaging | Kafka (Redpanda alternative) |
| API Gateway | Kong |
| Reverse Proxy | Nginx |
| File Storage | Local filesystem |
| Auth | Local email/password, JWT |
| Realtime | WebSockets |
| Email | Local SMTP |
| Containerization | Docker (Compose for MVP; K8s if scale demands) |
| Offline | PWA (Service Worker + IndexedDB) |

> **Note (UI stack):** Vuetify and PrimeVue overlap heavily. Recommendation:
> **Tailwind + PrimeVue** OR **Tailwind + Vuetify**, not all three. If all three
> are used, define strict ownership: e.g., Vuetify = forms/tables, PrimeVue =
> data viz/specialized widgets, Tailwind = layout/utility. See Open Questions.

---

## 4. Microservices

| Service | Responsibility | Key Events |
|---|---|---|
| Auth | Login, registration, password reset, RBAC, JWT issuance | `user.registered`, `user.login`, `password.reset` |
| Stations | Station CRUD, params, sensors, docs, configs (versioned), QR | `station.created`, `station.updated`, `doc.uploaded` |
| Requests | Request lifecycle, approval, assignment, SLA, disputes | `request.submitted`, `request.approved`, `request.denied`, `request.reopened`, `request.closed` |
| Visits | Visit lifecycle, check-in/out, notes, maintenance log | `visit.started`, `visit.ended`, `visit.completed` |
| Media | Image/video/doc storage and metadata | `media.uploaded`, `media.processed` |
| Reports | PDF report generation, analytics | `report.generated` |
| Notifications | Email + WebSocket push | consumes all above |
| Audit | Immutable log of actions | consumes all above |

> **Assumption:** Sensors/Parameters are folded into **Stations** for MVP.

### 4.1 Event Flow Example — Visit Completion → Report

    Visits: visit.completed
        → Reports: generate PDF
        → Notifications: email client
        → Audit: log event

---

## 5. Data Model (MongoDB — indicative)

### 5.1 users
    { _id, email, passwordHash, roles: [String], orgId, createdAt, active }

### 5.2 organizations
    { _id, name, type: "internal" | "client", inviteCode, domain }

### 5.3 stations
    {
      _id, name, type, ownerOrgId, lat, lon, elevation,
      parameters: [{ name, unit }],
      sensors: [{ model, paramRef }],
      docs: [{ docId, version, uploadedAt }],
      configs: [{ configId, version, uploadedAt }],
      qrCode
    }

### 5.4 requests
    {
      _id, clientOrgId, createdBy, stationIds: [ObjectId],
      priority, status, slaDueAt,
      assignedTeam, assignedStaffId,
      visits: [ObjectId],
      comments: [ObjectId],
      attachments: [ObjectId],
      dispute: { reason, reopenedAt },
      history: [{ status, at, by }]
    }

### 5.5 visits
    {
      _id, requestId, staffId,
      checkInAt, checkOutAt,
      startMedia: [ObjectId], endMedia: [ObjectId],
      maintenanceLog, midNotes: [ObjectId],
      reportId, syncStatus
    }

### 5.6 media
    { _id, ownerType, ownerId, kind, path, mime, size, uploadedAt }

### 5.7 reports
    { _id, visitId, requestId, path, generatedAt, templateVersion }

### 5.8 audit_log
    { _id, actorId, action, targetType, targetId, at, meta }

---

## 6. API Surface (REST, via Kong)

### Auth
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/password-reset`
- `POST /auth/password-reset/confirm`

### Stations
- `GET/POST /stations`
- `GET/PUT/DELETE /stations/{id}`
- `POST /stations/{id}/docs`
- `POST /stations/{id}/configs`
- `GET /stations/{id}/qr`

### Requests
- `POST /requests`
- `GET /requests` (role-scoped)
- `GET /requests/{id}`
- `PATCH /requests/{id}/status` (approve/deny)
- `POST /requests/{id}/assign`
- `POST /requests/{id}/comments`
- `POST /requests/{id}/attachments`
- `POST /requests/{id}/confirm`
- `POST /requests/{id}/dispute`

### Visits
- `POST /visits` (under request)
- `POST /visits/{id}/check-in`
- `POST /visits/{id}/check-out`
- `POST /visits/{id}/media`
- `POST /visits/{id}/notes`
- `POST /visits/{id}/complete`

### Reports
- `POST /reports/generate`
- `GET /reports/{id}`
- `GET /reports?type=...`

### Realtime
- `WS /ws/requests/{id}` (comments, status)
- `WS /ws/notifications`

---

## 7. Offline & Sync

- **Approach:** PWA (Service Worker + IndexedDB + Background Sync).
- **Offline scope:** check-in/out, media capture, notes, maintenance log.
- **Sync:** queue mutations, replay on reconnect.
- **Conflict resolution:** TBD — options: (a) merge, (b) prompt user,
  (c) last-write-wins. Recommend prompt for comments, LWW for visit fields.
- **Media:** stored locally in IndexedDB until uploaded; resumable uploads.
- **Open:** confirm field device OS/browser targets.

---

## 8. Security

- JWT-based auth; refresh tokens; short-lived access tokens.
- RBAC enforced at gateway and service level.
- Password hashing: Argon2id.
- Audit log (immutable, append-only collection).
- File upload validation: MIME + extension allowlist (pdf, jpg, png, mp4, mov).
- HTTPS terminated at Nginx.
- No PII beyond email; retention policy TBD.

---

## 9. Non-Functional Requirements

| Area | Target |
|---|---|
| Availability | 99% (on-prem, single node — best effort) |
| Latency | < 300ms p95 for API calls |
| Scale | ~50 (units TBD) |
| Media size | Video caps — TBD (recommend ≤ 200MB/file) |
| Backup | Daily MongoDB dump + file store snapshot |
| Logging | Centralized (e.g., Loki/ELK) — TBD |

---

## 10. Deployment

- **Containerization:** Docker images per service.
- **Orchestration:** Docker Compose (MVP) → Kubernetes (if scale/HA required).
- **Gateway:** Kong (routes, auth plugins, rate limiting).
- **Proxy:** Nginx (TLS, static SPA, Kong upstream).
- **Message broker:** Kafka or Redpanda (recommend Redpanda for on-prem solo ops).
- **Storage:** Local volume mounted to Media service.
- **Email:** Local SMTP relay.
- **CI/CD:** TBD (GitHub Actions → registry → on-prem pull).

---

## 11. Observability

- Structured JSON logs from all services.
- Metrics via Prometheus + Grafana (recommended).
- Tracing (OpenTelemetry) — recommended, optional for MVP.
- Audit service as business-level log.

---

## 12. Testing Strategy

- Unit tests per service (pytest).
- Integration tests against Docker Compose stack.
- Contract tests for Kafka events.
- Frontend: Vitest + Playwright.
- Offline sync: simulated network loss tests.

---

## 13. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Solo build + microservices | High | Modular monolith first; extract services later |
| Kafka ops on-prem | High | Use Redpanda (single binary) |
| All three UI libs | Medium | Pick two, or enforce strict ownership |
| Offline sync complexity | High | Start with capture-only offline; expand later |
| Media volume growth | Medium | Retention policy; compression; quotas |
| No K8s skills/hardware | Medium | Docker Compose on single node for MVP |

---

## 14. Open Questions

1. Confirm single- vs multi-tenant interpretation.
2. UI library final decision (2 vs 3).
3. Field device OS/browser targets.
4. Offline scope + conflict resolution policy.
5. Kafka vs. Redpanda.
6. Nginx vs. Kong responsibilities at edge.
7. Hardware: single node vs. cluster.
8. Media volume estimates.
9. SMTP provider details.
10. Scale clarification ("50" = ?).
11. Report export formats beyond PDF.
12. Comment model (threaded vs. flat).
13. Compliance/retention requirements.
14. CI/CD tooling.
15. Observability stack choice.

---

## 15. Appendix — Recommended Service Extraction Order

If starting as a modular monolith, extract in this order:
1. **Auth** (clear boundary, low coupling)
2. **Media** (I/O heavy, independent scaling)
3. **Reports** (CPU heavy, event-driven)
4. **Notifications** (pure consumer)
5. **Audit** (pure consumer)
6. **Visits** / **Requests** (higher coupling — extract last)
7. **Stations** (stable, low churn)