# CLAUDE.md

AWS-MMS (Automatic Weather Station Maintenance Management System). A self-hosted web app for maintaining weather stations the organization runs for external client organizations in several countries. Clients request work and sign it off. Staff plan, record (offline as well) and report site visits.

## Think like a PWA expert first (required)

AWS-MMS is a PWA: technicians record whole visits on iPhones and Android phones with no signal, and nothing may be lost or duplicated. **Before starting any task in this repo (code, review, plan or document), load the `pwa` skill ([.claude/skills/pwa/](.claude/skills/pwa/SKILL.md)) with the Skill tool and answer its pre-flight questions.** For back-end-only work this takes seconds, but still check the effect on the device: sync contracts, idempotency, auth refresh, caching headers, CSP, presigned uploads. The skill holds the PWA rules from the TRD, verified browser facts (iOS Safari first), the vite-plugin-pwa, Workbox and Dexie patterns, PWA work per phase, the open findings (F1–F13) and the sources. When browser reality and a planning document disagree, raise it as a finding; don't work around it silently. A `SessionStart` hook in [.claude/settings.json](.claude/settings.json) repeats this reminder at the start of every session and after `/clear` or compaction (text in [.claude/hooks/pwa-session-start.json](.claude/hooks/pwa-session-start.json)).

## Current state

**Planning is done; Phase 0 (readiness) is under way; build has not started.** The repo holds the planning documents, the design reference library, project skills (including the `pwa` expert skill) and the **frontend theme foundation** in [frontend/](frontend/) (Vite, Vue, Vuetify 4, Tailwind 4, brand themes, fonts, icons; no shells or pages yet). There are no backend services yet.

- **Repository:** GitHub `tajay59/MARS-MMS`, branch `main` (remote `origin`). Text files are LF (`.gitattributes`, `.editorconfig`); keep it that way, because shell scripts and configs run in Linux containers.
- **CI:** [.github/workflows/frontend.yml](.github/workflows/frontend.yml) runs lint, type-check and build (job `check`, `ubuntu-24.04`) on pushes to `main` that touch `frontend/` and on **every** pull request, so `check` can be a required status. Phase 1 replaces it with the full pipeline.
- **GitHub tracking:** project board [AWS-MMS](https://github.com/users/tajay59/projects/2) (linked to the repo), milestones P0–P8 (one per IP phase); Phase 0 work is issues #1–#10. New issues get a milestone and are added to the board. Branch protection on `main` is not on yet: GitHub Free refuses it for private repos (issue #6). Until it is, still work on a branch and merge through a pull request with a green `check`.
- **SeaweedFS spike:** [infra/spikes/seaweedfs/](infra/spikes/seaweedfs/) (throwaway, Phase 0). Not part of the app stack. **Passed 2026-10-16** on SeaweedFS 4.48 (T7 confirmed); Chrome, Firefox 158 and a 152.8 MiB video from an Android phone all passed the same day. All checks done; an iPhone run is optional.
- **Tools installed:** Docker Desktop 29.8.2 (Compose v5.6.0) and draw.io desktop 32.4.1. Docker's CLI is at `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin`; terminals opened before the install don't have it on PATH.
- **Information requested from the organization:** [Claude Doc](https://claude.ai/code/artifact/245278ff-5250-48fb-859d-6bcdba80d911) listing every open input (T, B, P, Q, V items) with owner, due week and default.
- **Developer docs site:** [docs/index.html](docs/index.html), the interactive reference for how the app is wired. **It must be updated every phase** (see "Developer documentation site" below).

When code is added, follow the rules below and update this file.

## Developer documentation site (required)

[docs/index.html](docs/index.html) is the living, interactive reference that lets any future developer see how AWS-MMS is wired: architecture, services and routes, gateway, data and schemas, events, each feature's flows, frontend, security, configuration, infrastructure, CI/CD, decisions, a diagram guide and a changelog. The planning documents say what to build; this site describes what was built.

**Requirement: every phase updates it, and a phase is not done until it has** (it is in the definition of done below). Also update it in any change that alters how the system is wired. Each phase:

1. Update "Build status", the section badges (`badge built` / `progress` / `planned`) and the sidebar dots (`dot built` / `dot progress`).
2. Replace designed shapes with built ones: schemas from the Pydantic models, routes from OpenAPI, events from `mms_common.events`, settings with their real env var names, file and folder tables.
3. Add the diagrams chosen for the phase (see "Charts" below) and update any diagram the phase changed.
4. Record new decisions in the "Decisions" section and in the source document.
5. Add a "Changelog" entry.
6. Open the page in a browser in light and dark and check that no diagram shows "could not be drawn". If the code and the TRD disagree, fix one of them in the same change.

**Constraints:** the page opens straight from disk (`file://`) with **no server, no build step and no network**. Mermaid is vendored and pinned (`docs/assets/vendor/mermaid-11.17.2.min.js`), and the fonts are copied into `docs/assets/fonts/`. Content lives in `index.html` (one `section.doc` per sidebar entry; `.sub[id]` blocks are what search finds); behaviour lives in `docs/assets/docs.js`, styles (brand tokens, light and dark) in `docs/assets/docs.css`. The site is developer tooling, not an app screen, so the UI-skills workflow doesn't apply to it; it still uses the DBD tokens and fonts. The "Maintaining these docs" section in the page has copy-paste snippets.

### Diagrams

- **Mermaid is the default.** Write the source inside `<pre class="mermaid-def">` in a `figure.diagram` with `data-title` (the answer, in a few words) and `data-kind` (a chart type from the catalogue below). Escape `<` as `&lt;` and `&` as `&amp;`. Don't put `;` in sequence messages, or raw `<host>`-style text in labels (it's read as HTML).
- **draw.io** for hand-laid diagrams: true swimlanes, deployment pictures, anything for clients or training. Save as `docs/diagrams/<name>.drawio.svg` (an SVG with the editable diagram inside; GitHub shows it as an image). Edit it in draw.io desktop, app.diagrams.net or VS Code's Draw.io Integration (`hediet.vscode-drawio`). Show it in the site as an `<img>` view; when a Mermaid and a draw.io version of one flow both exist, they are tabs on one figure and must match.
- Use names exactly as in the code and specs. One question per diagram. Brand colours only; status colours only for statuses.

### Charts: suggest them every phase

**At the start of each phase, propose which charts to add to the site** from this catalogue (the 17 types in Figma's [types of flow charts](https://www.figma.com/resource-library/types-of-flow-charts/), plus the UML and data diagrams below). The user picks; the chosen charts are added before the phase closes. The full catalogue with status, and the per-phase suggestions, are in the site's "Diagram guide".

| Chart type | Use it in AWS-MMS for |
|---|---|
| Process flow diagram | One actor's steps and decisions: field visit (J6), CI pipeline, station import |
| Workflow diagram | Staff routines outside the app's flow: hypercare triage, calibration follow-up, release routine |
| Data flow diagram | Event wiring, where secrets and tokens live, notification fan-out, backups |
| Swimlane flowchart | Hand-offs between roles and services: J1 registration, J4 approve and assign, J8 client review (draw.io for true lanes) |
| Decision tree diagram | Rules with many branches: `derive_status`, sync conflicts, client document access |
| System flowchart | Inputs processed by the system: gateway routing, media pipeline, report rendering |
| Document flowchart | Documents that collect signatures: visit report → final → client sign-off; client report form → PDF |
| Product flowchart | Sensor inventory: stock → installed → repair or lab calibration → stock or retired |
| PERT chart | IP phases, dependencies and decision deadlines (Mermaid gantt) |
| Use case flowchart | Roles × actions per service (mirrors the authorization matrix) |
| Event storming flowchart | Commands → domain events → consumers and read models per module |
| Customer journey flowchart | The client's path: invited → first request → follow progress → sign off |
| Production flowchart | Not used (covered by the request swimlane and lifecycle) |
| Logical model flowchart | Summary reports and dashboards: read-model inputs → aggregation → PDF/CSV |
| Code flowchart | Branch-by-branch logic worth a test each: `/login`, `/refresh`, sensor action apply/reverse, sync op apply, finalize retry |
| E-commerce flowchart | Not used (no sales flow) |
| Website flowchart | Pages, shells, route guards and redirects |
| *Beyond Figma:* sequence, state, ER, architecture (C4), gantt | Calls over time; every status field; collections; containers; schedules |

Suggested per phase (adjust to what was built): **P1** J1 swimlane (draw.io), credentials data flow, `/login` and `/refresh` code flowcharts, auth use cases, auth event storming, outbox leader handover sequence, shells and guards website flowchart, local stack architecture. **P2** sensor inventory product flowchart, sensor unit state, document upload and model-document download sequence, station import process flow. **P3** request state (as built), `derive_status` decision tree, J4 swimlane, WebSocket fan-out sequence, request event storming. **P4** visit state, visit-end transaction sequence, sensor action code flowchart, media pipeline system flowchart, media state. **P5** prepare-for-field sequence, offline op state, conflict decision tree, device storage data flow. **P6** visit report document flowchart, finalize saga (as built), client review customer journey, reminders and auto-close state. **P7** summary reports logical model, backup and restore data flow, monitoring system flowchart, production architecture. **P8** hypercare workflow, client onboarding customer journey, go-live gantt.

## Planning documents

Read these before writing a new document or any code. Requirement IDs (AUTH-1, REQ-2, VIS-7, …) belong to the PRD. Service, container and route names belong to the TRD. Journey IDs J1–J10 and page routes belong to the AFD.

| File | Document | Version | Live copy (Claude Doc) |
|---|---|---|---|
| [docs/PRD.md](docs/PRD.md) | Product Requirements | 1.1 | — |
| [docs/TRD.md](docs/TRD.md) | Technical Requirements | 2.0 | — |
| [docs/AFD.md](docs/AFD.md) | App Flow (journeys J1–J10, routes, menus, edge states) | 1.1 | [link](https://claude.ai/code/artifact/51ce0c78-20c6-4218-b22b-4f69ee6024d1) (1.0, stale) |
| [docs/DBD.md](docs/DBD.md) | Design Brief (colour, type, shells, components) | 1.2 | [link](https://claude.ai/code/artifact/b14d2c1e-0106-470a-bd5a-ffc28c4eea37) (1.1, stale) |
| [docs/BSD.md](docs/BSD.md) | Background Schema (data location, schemas, access, retention) | 1.1 | [link](https://claude.ai/code/artifact/bfd6c029-c1d7-4fc0-a6fe-b75502654c02) (1.0, stale) |
| [docs/IP.md](docs/IP.md) | Implementation Plan (phases 0–8, 25 weeks) | 1.1 draft | [link](https://claude.ai/code/artifact/de63972b-b743-4ad1-b5fa-85325dc22312) (1.0, stale) |
| [docs/TP.md](docs/TP.md) | Test Plan (levels, rule-enforcement tests, seed users, CI stages, tests by phase) | 1.1 draft | [link](https://claude.ai/code/artifact/d6d1344c-a8be-466d-931c-2b8c8f5ec225) (1.0, stale) |

- The App Flow file is `docs/AFD.md`. Some older notes call it "APD"; it is the same document.
- [docs/drafts/](docs/drafts/) holds the earlier drafts (Claude, DeepSeek, GPT) and the original `Specification.txt`. The final documents supersede them. Don't edit them, and don't treat them as a source of truth.
- **The local files are the source of truth.** Since 2026-10-16 the Claude Doc live copies are stale: each carries a note pointing to the local file. Update only `docs/*.md` unless the user asks for the live copies to be brought back in step.
- The documents were written one at a time, each consistent with the ones before it. A new document reuses existing IDs, route names, journey numbers, status names and colour tokens rather than inventing new ones.
- When a decision closes an open question, update every document that refers to it.

### Open-question prefixes

| Prefix | Document | Status |
|---|---|---|
| Q | PRD §12 | Open |
| T | TRD §22 | Open, with defaults; T7 decided (SeaweedFS) |
| A | AFD §7 | A7, A9, A10 decided |
| D | DBD | D2–D4 decided; D1, D5, D6 open |
| B | BSD | B2–B6 closed or decided; B1 open |
| P | IP | P5 decided; P1–P4 open |
| V | TP | V1–V5 open, with defaults |

### Decisions already made (don't reopen them)

- **D2:** dark mode ships in v1. A Light / Dark / System setting is stored per user.
- **D3:** ApexCharts (`vue3-apexcharts`) for dashboards, and for summary-report charts in PDFs via headless Chromium.
- **D4:** clients see staff names (`{id, name}`) on requests and visits. Never send staff email or phone to clients.
- **B5:** stations never change owner organization.
- **B6:** there are no personal-data erasure requests.
- **UI framework:** Vuetify 4 + Tailwind CSS 4 replaced PrimeVue 4 (TRD ADR-11, DBD 1.1). Icons are Material Design Icons (`@mdi/js`), not PrimeIcons.
- **Plan:** one developer working with Claude Code. Phase 0 + PRD phases 1–7 (19 weeks) + 2-week buffer + Phase 8 pilot = **25 weeks** to go-live. A staging release goes out after each build phase, for staff only; clients first use the system in the pilot. Notification email is in Phase 1.
- **Engineering review, 2026-10-16** (TRD 2.0, PRD 1.1):
  - **Five services** instead of nine (ADR-1). No integration stub; Nginx returns 501 on `/api/v1/integrations/`.
  - **Kong removed**: Nginx is the gateway (ADR-5).
  - **SeaweedFS** replaces MinIO (ADR-6, T7).
  - **One owner per station** on a visit; no offline merge (ADR-18, OFF-11).
  - **Parallel visits** are allowed; request status is derived from them (ADR-17).
  - **Reopening a report** during Client Review returns the request to In progress; after Closed it stays Closed (RPT-6).
  - **Offline PIN unlock** for staff (ADR-20, AUTH-12).
  - **Files fail closed**: staff-only until the owning service shares them (ADR-19).

## Architecture (TRD)

- **Five FastAPI services**, split by business capability:
  - `auth`: users, organizations, tokens.
  - `operations`: stations, sensors, documents and configs; requests; visits and sync. Its modules share one database and change together in one transaction.
  - `media` (+ `media-worker`).
  - `report` (+ `report-worker`): visit, close-out, client-form, label and summary PDFs; the dashboard read model.
  - `platform`: the notification and audit modules, with two databases and two DB users.
- **Edge and gateway:** Nginx handles TLS, the SPA, path routing to services, `limit_req` rate limits, `X-Request-ID`, and the `files.` host for SeaweedFS. Nginx does not verify JWTs; each service does.
- **Data:**
  - A single MongoDB 8 replica set (`rs0`) with **one database and one DB user per service** (`platform` has two).
  - Files go to SeaweedFS (S3 API) through presigned direct uploads.
  - Kafka 4.x (KRaft) carries domain events between services.
  - Redis 7.4 holds jobs (arq), cache, leader leases, the login throttle and WebSocket pub/sub.
- **Frontend:** a Vue 3.5 + TypeScript PWA built with Vite, Vuetify 4 (`vite-plugin-vuetify`, brand themes + global defaults), Tailwind CSS 4 (no preflight, in a cascade layer before `vuetify-final`), Material Design Icons (`@mdi/js`), Pinia, Dexie (offline), Workbox (`injectManifest`) and Web Locks.
- **Runtime:** Docker Compose on the organization's own servers. Python 3.13.

## Rules that are not negotiable

1. **Never access another service's database.** To get another service's data, call its `/internal/*` endpoint with a service token, or consume its events. (Modules inside `operations` share its database.)
2. **All state changes go through the domain state machine and the outbox.** Update the record and insert the outbox event in **one Mongo transaction**. Never produce to Kafka directly from a request handler. The outbox relay runs only under the service's Redis leader lease.
3. **Org scoping lives in the repository layer** (`repo/`). For a client, every query is merged with `{"org_id": user.org_id}` (`owner_org_id` for stations, `current_org_id` for sensor units). Endpoint code must not be able to bypass it.
4. **A resource outside the user's scope returns 404, not 403** (ADR-16).
5. **Viewers never mutate.** Every mutating route uses `require_roles(...)` without `viewer`, and a test asserts it.
6. Internal comments, draft reports, staff-only documents and config versions are filtered out for clients in the repo layer. **Files start `visibility = staff`** and become client-visible only through `media.visibility_requested`.
7. `domain/` has no FastAPI, Mongo or Kafka imports.
8. Times are stored in UTC. Each station has an IANA time zone that is used for display only.
9. IDs are UUIDv7, generated on the client for anything that can be created offline. Sync operations carry idempotency keys (`op_id`).
10. The audit collection is insert-only and hash-chained. No code updates or deletes audit records.
11. Finalized visit-report versions are immutable. A change means reopening the report as a new version.
12. Mongo queries are built from typed values only. Never pass raw operators from user input.

Also by design (TRD 2.0):

- Request status from Assigned to closure comes only from `derive_status` (TRD §3.2.2), never set by hand.
- Only a station's owner writes its work record.
- Consumers write `processed_events` in their own transaction and guard read models with `aggregate_version`.
- Read models are rebuilt from `/internal/snapshot/*` with `backfill.py`, never by replaying the outbox.
- The service worker never caches API responses.

## Code layout (TRD §3.0, §13.1, §19)

```
services/<name>/app/
  main.py  config.py  api/  domain/  repo/  events/  jobs/  migrations/
  (operations groups each layer by module: stations/ requests/ visits/)
services/<name>/tests/   unit (domain) · api (httpx + testcontainers) · contract (events)
libs/mms_common/         auth, events, outbox, kafka, consumer, mongo, logging, errors, ids, time, snapshot
templates/service/       copier template; create new services from it
frontend/src/            app/ api/ features/ offline/ charts/ components/ stores/ sw/
infra/                   compose*.yml, nginx/, kafka/topics.yml, seaweedfs/, scripts/
```

Every service exposes `GET /health`, `GET /ready`, `GET /metrics` and OpenAPI at `/docs` (disabled in production).

## Naming conventions

- **Public API:** `/api/v1/<plural-kebab-resource>` (for example `/api/v1/sensor-units`). Actions are `POST /{id}/<verb>` (`/approve`, `/claim`, `/verify`). Services mount their own prefix; Nginx routes by prefix and passes the path unchanged. Declare literal paths (`/geo`, `/mine`, `/due`) before `/{id}`.
- **Internal API:** `/internal/...`. Nginx never routes it (returns 404).
- **Kafka topics:** `mms.<service>.events` (`auth`, `operations`, `media`, `report`). Dead letters: `mms.dlq.<consumer-service>`. The message key is the root aggregate ID: `request_id` for request, comment and visit events; `station_id` for station and sensor events.
- **Event types:** `<entity>.<past_tense>` (`request.approved`, `visit.ended`, `report.finalized`). Schemas are Pydantic models in `mms_common.events`, keyed by `(type, version)`, and every envelope carries `aggregate_version`. A breaking change gets a new `version`.
- **Environment variables:** a prefix per service via `pydantic-settings`: `AUTH_`, `OPS_`, `MEDIA_`, `REPORT_`, `PLATFORM_` (for example `OPS_MONGO_URI`, `OPS_AUTO_CLOSE_DAYS`).
- **Migrations:** forward-only `migrations/NNNN_*.py`, run on startup under a lock in `_migrations`.
- **Mongo fields:** snake_case. Use the field and collection names in TRD §5 and docs/BSD.md.

## Frontend and design

- docs/DBD.md is the design source of truth. Brand tokens live in [frontend/src/app/theme/brand.ts](frontend/src/app/theme/brand.ts), which defines Vuetify's `light` and `dark` themes. Tailwind reads the same colours through `@theme` mapped to Vuetify's `--v-theme-*` variables ([tailwind.css](frontend/src/app/theme/tailwind.css)); Tailwind's default palette is removed.
- Primary colour is Horizon blue `#22569A`, a placeholder until the organization supplies branding (D1). Neutrals are slate. **Status colours are reserved** for request and station status (chips, map markers, timeline dots) and are never used for decoration.
- Fonts are Inter and JetBrains Mono from `@fontsource-variable`, bundled (no CDN). Icons are Material Design Icons as SVG from `@mdi/js` (outline variants), listed in `app/theme/icons.ts`. No icon font.
- There are three shells: client (top nav), staff (sidebar) and field (phone: stepper Before → Work → After → Review, bottom nav, sync badge). Public pages, including `/unlock`, use the split panel.
- Dark mode switches Vuetify's theme (`useTheme().change()`) and the `.app-dark` class on `<html>` together ([stores/theme.ts](frontend/src/stores/theme.ts)); Tailwind's `dark:` variant uses `.app-dark`. `public/theme-init.js` is an external script because the CSP is `script-src 'self'`, which rules out inline scripts.
- `app/theme/layers.css` must stay the first import in `main.ts`; the CSS import order there is deliberate (an ESLint import-sort exception).
- Use Vuetify for components and Tailwind for layout and spacing. Avoid custom component CSS unless there is no other way.
- Vuetify's own utility and colour classes are off (`$utilities: false`, `$color-pack: false`, `theme.utilities: false`), so `rounded-*`, `bg-*`, `text-*` and spacing classes are always Tailwind's. Set the look through global `defaults` in `app/theme/vuetify.ts`, not per-page props. Classes Vuetify adds from props (`rounded-md`, `rounded-card`, `elevation-8`) are safelisted in `tailwind.css`. Vuetify's display thresholds match Tailwind's breakpoints (640/768/1024/1280/1536).
- Viewers see read-only views. Action buttons are hidden, not disabled.
- [design/awesome-design-md/](design/awesome-design-md/) is a reference library of other brands' DESIGN.md files (the `design-md-reference` skill). It is for inspiration only and never overrides DBD.md.

## UI skills (required when building UI)

The project skills in [.claude/skills/](.claude/skills/) **must be used** when designing, building or reviewing any screen, PDF or email. Load each skill with the Skill tool at the step where it applies.

**Order of precedence:** docs/DBD.md, then TRD §13.2 conventions, then the skill. Several skills have their own house style (warm monochrome palettes, custom fonts, gradients, GSAP motion, asymmetric or randomised layouts, CDN assets). Use their quality rules, such as hierarchy, spacing, avoiding generic AI patterns and polish, but keep DBD's tokens, palette, fonts, shells and components. Follow Vuetify + Tailwind with no custom component CSS, the CSP (`script-src 'self'`, self-hosted fonts) and `prefers-reduced-motion`.

Claude Code has **no image-generation tool**. The skills that generate images (`imagegen-frontend-web`, `imagegen-frontend-mobile`, `brandkit`, and the image step of `image-to-code`) can't run here. Mock-ups are HTML pages instead.

### Workflow for each screen

1. **Read** the screen's section in DBD.md and its journey in AFD.md.
2. **Reference:** use `design-md-reference` to borrow a specific pattern (a table, card, dark palette or token scale).
3. **Mock up:** build a static HTML mock-up of the screen from DBD tokens (Inter, slate neutrals, Horizon blue, status colours; a phone frame for field screens; light and dark), applying the quality rules from `design-taste-frontend`, `high-end-visual-design` and `minimalist-ui`. Publish it as a private artifact and get the user's approval before building.
4. **Build:** implement the approved mock-up in Vue with Vuetify components and Tailwind layout, matching it closely.
5. **Review:** run `web-design-guidelines` on every screen, together with the axe check in the definition of done. Check UI text and email copy against DBD's "Voice and microcopy" with `writing-guidelines`.
6. **Polish:** use `redesign-existing-projects` for improvement passes on screens that already exist.

### When each skill applies

| Skill | Use it for | Limits in this project |
|---|---|---|
| `design-md-reference` | Patterns from other design systems | Inspiration only |
| `design-taste-frontend` | Avoiding generic AI patterns on every screen and mock-up; art direction for public pages (login, register, reset, unlock) | Its landing-page directions and palettes don't apply to app screens |
| `high-end-visual-design` | Spacing, depth and card treatment | Keep DBD surfaces, corners and shadows |
| `minimalist-ui` | Calm document-style layouts: request detail, visit report editor, station pages | Slate neutrals, not warm monochrome |
| `stitch-design-taste` | Turning DBD.md into an agent-friendly `DESIGN.md` and keeping it in sync | DBD.md remains the source |
| `industrial-brutalist-ui` | Structure for dense data views: audit log, summary tables, calibration due list | Rigid grids and tabular figures only; none of its decay effects or terminal styling |
| `gpt-taste` | Composition ideas for public pages | No GSAP scroll effects or AIDA structure in app screens; respect reduced motion |
| `image-to-code` | Its implementation and quality rules only (matching a design closely, no cards inside cards), applied to approved HTML mock-ups | Its image-generation step can't run here |
| `redesign-existing-projects` | Audit and upgrade passes on built screens | Must not break behaviour or role rules |
| `pwa` | Loaded first for every task (see "Think like a PWA expert first"); field screens, install and update prompts, `/unlock`, `/sync` | Project skill; TRD and AFD win over it |
| `web-design-guidelines` | Required review of every screen | — |
| `writing-guidelines` | Microcopy, empty states, errors and emails | DBD voice wins |
| `imagegen-frontend-web`, `imagegen-frontend-mobile`, `brandkit` | Not used: they need an image-generation tool | Revisit only if one becomes available (for example for D1 branding) |

`design-taste-frontend-v1` and `design-taste-frontend-v2-experimental` are older versions kept for compatibility. Use `design-taste-frontend` instead.

## Commands

Developer docs: open [docs/index.html](docs/index.html) in a browser (no server needed). To check every diagram renders, with Edge:

```sh
msedge --headless=new --virtual-time-budget=40000 --dump-dom "file:///<repo>/docs/index.html" | grep -c 'id="mmd-'   # = number of diagrams
```

Frontend (run in `frontend/`):

```sh
npm install
npm run dev          # dev server on http://localhost:3000
npm run type-check   # vue-tsc
npm run lint         # ESLint (eslint-config-vuetify); lint:fix to fix
npm run build        # type-check + production build
```

SeaweedFS spike (run in `infra/spikes/seaweedfs/`; needs Docker):

```sh
docker compose up -d --build
docker compose run --rm spike python check.py   # then open http://localhost:8080
docker compose down -v
```

Not yet available. Add these when the repo is scaffolded (IP Phase 1):

- start the local stack (`infra/compose.yml` + `compose.dev.yml`: hot reload, seeded data, Mailpit, self-signed TLS)
- run one service and its tests (pytest, Ruff, mypy)
- frontend tests (Vitest, Playwright)
- regenerate OpenAPI types (`openapi-typescript`)
- create a new service from the copier template
- rebuild a read model (`infra/scripts/backfill.py --consumer <service>`)

## Definition of done (IP)

A feature is done when:

- unit and API tests pass, including org scoping and 404 for out-of-scope records
- new routes are in the authorization matrix, and new tests carry the requirement IDs they cover (`@pytest.mark.req("REQ-3")`, Playwright tag `@REQ-3`); see docs/TP.md
- Ruff, mypy, ESLint and vue-tsc report no errors
- OpenAPI is regenerated, and the event schemas in `mms_common.events` and the audit mapping (PRD AUD-1) are updated
- screens work in light and dark themes and pass an axe check (WCAG 2.2 AA)
- new or changed screens have passed a `web-design-guidelines` review
- changes to `frontend/src/sw/`, `frontend/src/offline/`, caching headers or the CSP pass the `pwa` skill's merge checklist ([checklists.md](.claude/skills/pwa/references/checklists.md))
- the developer docs site ([docs/index.html](docs/index.html)) describes what was built: status, schemas, routes, events, config, decisions, the phase's chosen charts and a changelog entry (see "Developer documentation site")
- CI is green and the build is deployed to staging

Coverage targets: 90% for `domain/`, 70% overall.

## Working with the user

- Planning documents are written **one at a time**, in the order the user names them ("now let's work on: …"). All seven live in `docs/` as Markdown; edit the local files.
