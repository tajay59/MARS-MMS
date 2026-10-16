---
name: pwa
description: PWA expert for AWS-MMS. Load before any task in this repo, and always before touching frontend/, the service worker (src/sw), offline code (src/offline), Dexie, sync, media capture or upload, install or update UX, auth refresh or the offline PIN session, Nginx caching headers or CSP, Playwright offline tests, or a planning document about any of these. Gives the expert pre-flight, the project's PWA rules (TRD §6.1, §7, §13.3, §15), verified browser facts with iOS Safari first, vite-plugin-pwa injectManifest + Workbox + Dexie patterns, PWA work per IP phase, open findings and curated sources.
---

# AWS-MMS PWA expert

AWS-MMS is a PWA first. Technicians record whole visits on phones with no signal (NFR-4), on iOS Safari as well as Android Chrome (NFR-5), and the launch criterion is **zero lost or duplicated records or files** (PRD §8). Every change, front end or back end, is judged by what it does to a phone in a field with no signal, holding unsynced work.

## 1. Pre-flight: think like a PWA expert before doing anything

Answer these before you plan, write code, review or edit a document. Most take seconds; say so when one doesn't apply. If an answer is "I don't know", read the reference file named in §4 before going further.

1. **Device.** Does this behave the same on iOS Safari (installed and in a tab), Android Chrome, desktop Chrome/Edge, Firefox? iOS is the floor: no Background Sync, no install prompt, separate storage for the installed app, JS suspended in the background. → [ios-safari.md](references/ios-safari.md)
2. **Network.** What happens online, offline, on a flaky link, and when the connection drops halfway (mid-upload, mid-`/sync`, mid-refresh)? `navigator.onLine === true` does not mean the server is reachable.
3. **Lifecycle.** What happens when a new service worker is waiting while a technician is mid-visit? When an old tab runs against a new Dexie schema? When ops queued by version N are synced by version N+1? → [service-worker.md](references/service-worker.md)
4. **Data and loss.** Where does the truth live at each moment (Dexie, outbox, server)? When is the local copy deleted, and only after the server confirmed it (OFF-8)? Could this change drop, duplicate or reorder a queued op? → [offline-data.md](references/offline-data.md)
5. **Storage.** How big is it (200 MB videos)? Is it inside quota, is the origin persisted, what does eviction do to it? → [storage.md](references/storage.md)
6. **Caching.** Is anything new being cached by the service worker? API responses never are (TRD §7.6, §13.3). → [caching.md](references/caching.md)
7. **Security and shared devices.** Does it keep tokens off the device, work with `script-src 'self'`, and leave nothing of user A visible to user B after logout? → [security.md](references/security.md)
8. **Proof.** How will you show it works: Vitest with `fake-indexeddb`, Playwright offline in Chromium (and WebKit where it works), and which real-device check (W13, W15)? → [testing.md](references/testing.md)

## 2. The PWA contract (from the planning docs; never break it)

1. **Build:** vite-plugin-pwa with `strategies: 'injectManifest'`, the worker in `frontend/src/sw/`, Workbox modules only (TRD §13.1, §13.3).
2. **Service worker caches only** the precached app shell (JS, CSS, fonts, `theme-init.js`, `index.html`) and map tiles. **API responses, mutations and uploads are never cached** (TRD §7.6, §13.3). Offline data comes only from Dexie, keyed by user.
3. **Dexie tables are the TRD §7.1 set:** `bundles`, `files`, `visits`, `outbox`, `blobs`, `meta`. Offline files are stored as blobs, never as presigned URLs.
4. **Every offline write is an op in the outbox** with a client UUIDv7 `op_id` (rules 9, ADR-8). The `/sync` API is idempotent per `op_id` (OFF-7). Local copies are deleted only after the server confirms (OFF-8).
5. **No merge (ADR-18, OFF-11).** One owner per station. On any conflict the device keeps its copy until it is exported or an admin resolves it (TRD §7.4).
6. **Tokens never touch storage.** Access token in memory (Pinia), refresh token in an httpOnly cookie. Refresh only under the Web Lock `mms-auth-refresh`, shared over `BroadcastChannel` (TRD §6.1). The service worker follows the same rule.
7. **Offline PIN session (ADR-20, AUTH-12):** PBKDF2-SHA-256, 310,000 iterations, random salt, Web Crypto; five wrong PINs disable offline unlock; logout removes the profile and bundles, keeps queued ops for the same user. Clients have no offline session.
8. **`navigator.storage.persist()` on first field use**, quota shown, warning below 1 GB free (TRD §7.1, R4).
9. **Media in the browser:** images resized to ≤ 2560 px, JPEG 0.85; video stored as recorded; SHA-256 via Web Crypto; capture time read before resizing (TRD §7.5). Uploads are resumable 8 MiB parts to the `files.` host (TRD §7.3).
10. **Sync triggers:** `online` event, Background Sync where supported (not iOS), app start, every 5 min while online, "Sync now". At most 100 ops per request. A failed op stops later ops for that visit only (TRD §7.3).
11. **CSP** `script-src 'self'; worker-src 'self'` and the rest of TRD §15. No inline scripts, no CDN, so no inline SW registration.
12. **Nginx** serves `sw.js`, `index.html` and `theme-init.js` with `no-cache`, and hashed assets for one year (TRD §2.1).
13. **Offline scope is site visits and station lookup only** (OFF-10). Approvals, request creation, signing and admin work show "This needs a connection" (AFD §5.2).

## 3. Expert defaults where the documents are silent

Use these unless a document says otherwise. If one becomes a lasting decision, record it in the TRD.

- **Update UX is a prompt, never a silent reload** (`registerType: 'prompt'`). Never apply an update while a field form or the camera is open. Keep the worker file name `sw.js` for ever.
- **Precache everything a field route needs**, so `/unlock`, `/visits/:id/field`, `/scan`, `/stations/:id` and `/sync` load with no network after one online visit.
- **Navigation fallback** to the precached `index.html`, with a denylist for `/api/`, `/ws`, `/internal/`, `/.well-known/`.
- **One Dexie transaction per user action** that writes both the working copy and its outbox op, mirroring the server's outbox rule.
- **One sync runner at a time** across tabs and the worker, under a Web Lock (proposed name `mms-sync`).
- **Version the op payloads** so ops queued by an older app version still sync after an update.
- **Keep the sync core free of DOM, Vue and Pinia**, so the service worker can run it from a Background Sync event.
- **A kill-switch worker is ready** before the first production release ([service-worker.md](references/service-worker.md) §6).

## 4. Which reference to read

| Working on | Read |
|---|---|
| Any phase start, or "what PWA work is in this phase?" | [phase-map.md](references/phase-map.md) |
| Manifest, icons, install prompt, standalone UX, desktop Edge | [manifest-install.md](references/manifest-install.md) |
| `src/sw/`, lifecycle, updates, kill switch | [service-worker.md](references/service-worker.md) |
| What to cache and how (tiles, shell, fonts) | [caching.md](references/caching.md) |
| `vite.config.mts`, `useRegisterSW`, TS setup for the worker, icons generation | [vite-pwa-vue.md](references/vite-pwa-vue.md) |
| `src/offline/`: Dexie schema, outbox, sync, blobs, locks, conflicts | [offline-data.md](references/offline-data.md) |
| Quota, `persist()`, eviction, big media | [storage.md](references/storage.md) |
| Anything an iPhone will run | [ios-safari.md](references/ios-safari.md) |
| Tokens, PIN, CSP, shared devices, logout | [security.md](references/security.md) |
| Tests, DevTools, real-device checks, debugging a phone | [testing.md](references/testing.md) |
| Code review of PWA code | [pitfalls.md](references/pitfalls.md) + [checklists.md](references/checklists.md) |
| Gaps found between the documents and browser reality | [findings.md](references/findings.md) |
| Where a fact came from, or to read further | [sources.md](references/sources.md) |

## 5. Precedence and keeping current

- **Order:** PRD/TRD/AFD/IP/TP (the project's decisions) → this skill (how to carry them out on real browsers) → external docs. If browser reality contradicts a document, don't quietly work around it: add or update the item in [findings.md](references/findings.md), tell the user, and when a decision is made, fix the document in the same change (CLAUDE.md).
- **Facts here were checked on 2026-10-16** (vite-plugin-pwa 2.0.0, Workbox 7.4.1, Dexie 4.4.6, firt.dev iOS notes of 13 Oct 2026). Before a phase that leans on a fact, re-check it against [sources.md](references/sources.md) and update the file and its date.
- **Not used here:** generic community PWA skills (secondsky, curiositech, alinaqi, claude-dev-suite). They cache API responses, call `skipWaiting()` on install or reload without asking, which breaks rules in §2.
