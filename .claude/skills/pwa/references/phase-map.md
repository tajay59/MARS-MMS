# PWA work in each IP phase

Read this at the start of every phase. It lists the PWA work the IP assigns to the phase, what an expert would add (marked **proposal**: raise it, don't just do it), and the PWA checks before the phase closes. IP and TP remain the plan; this file only says what they mean for the PWA.

## Phase 0 · Readiness (W1)

- Buy the test phones by W13 at the latest (V4). Earlier is better: Phase 0 checks need them.
- **Proposal:** on both phones, use [What PWA Can Do Today](https://whatpwacando.today/) (installed and in the browser) to record `persist()`, storage estimate, wake lock and camera capture. That answers F3 eleven weeks before W13.
- Decide F1 (OSM tiles) together with T1 (outbound internet, tile fallback).
- Note the open findings in [findings.md](findings.md) with the product owner.

## Phase 1 · Foundations (W2–W4)

IP: shells, public pages, Web Lock refresh coordination, Nginx with CSP, Playwright with CSP checks.

- Refresh coordination must already include the worker as a participant (`mms-auth-refresh`, BroadcastChannel), even if the worker arrives later.
- Nginx: `no-cache` for `sw.js`, `index.html`, `theme-init.js` and `manifest.webmanifest`; one year for `/assets/`; keep the previous release's assets after deploy (F9, F10).
- CSP already includes `worker-src 'self'` (TRD §15).
- Field shell: `viewport-fit=cover`, safe-area padding, no reliance on the browser back button (F13, manifest-install.md §5).
- **Proposal F5:** add vite-plugin-pwa now with the minimal worker (precache, navigation fallback, prompt update; no tiles, no Background Sync) and the manifest. The update flow, headers, CSP and precache budget then get four phases of use before Phase 5 needs them.

## Phase 2 · Stations (W5–W7)

- QR scanning (own camera loop; `BarcodeDetector` or jsQR in a worker, not `qr-scanner`: F16) and the label scan on real phones (W7) also exercise camera permissions in the installed app. Test both installed and in the browser.
- Map with Leaflet: `crossOrigin: true` on the tile layer, attribution visible, no prefetch (caching.md §4).
- Documents downloaded later for offline use: keep the download path blob-based so Phase 5 can reuse it.

## Phase 3 · Requests (W8–W9)

- WebSocket client reconnect with backoff (TRD §13.4) behaves well when the app returns from the background, especially on iOS where the socket dies while suspended. Reconnect on `visibilitychange` and `online`.
- "This needs a connection" state for online-only actions (AFD §5.2) as a shared component, used from here on.

## Phase 4 · Visits online (W10–W12)

- Field shell screens on phones (W12). Every step saves on change, even online: this is the Phase 5 foundation.
- Media capture: resize, capture time, hash, resumable multipart upload. Build these in `src/offline/blobs.ts`-ready form so Phase 5 only adds queuing (F4 decided before this).
- Video playback in iOS Safari after processing (IP exit criterion).

## Phase 5 · Offline field mode (W13–W15): the PWA phase

IP deliverables: installable app with vite-plugin-pwa (`injectManifest`), install prompt, `storage.persist()`, worker caching the shell and tiles; PIN session; prepare for field; outbox; `/sync`; conflicts; sync UI.

| Week | PWA work | Reference |
|---|---|---|
| W13 | Worker (or extend the Phase 1 one), manifest, icons, install prompt incl. the iOS sheet; Dexie schema; PIN and `/unlock`; prepare download to Dexie; offline QR; diagnostics panel | service-worker.md, manifest-install.md, offline-data.md |
| W13 | **W13 iOS check** | testing.md §5 |
| W14 | Outbox, sync runner and locks, resumable uploads, conflicts and export, Background Sync where supported; Vitest fault injection; Playwright offline (prove WebKit support, F6) | offline-data.md, testing.md |
| W15 | Field test on both phones; fixes | testing.md §5, ios-safari.md §6 |

Before closing: the kill switch (`selfDestroying` build) tested once on staging; op payload versioning in place (F8); docs site charts suggested for P5 (prepare-for-field sequence, offline op state, conflict decision tree, device storage data flow).

## Phase 6 · Reports and signatures (W16–W18)

- Signing and finalizing are online-only (OFF-10): the "needs a connection" state on `/visit-reports/:id`.
- Draft reports come from synced data; the "Draft report ready" notification arrives after sync. Make sure the sync UI says that work is synced before people expect the draft.

## Phase 7 · Summaries and hardening (W19–W20)

- Security review covers the worker, CSP, logout cleanup, PIN session, shared device (security.md §7).
- Release runbook: deploy keeps old assets; update prompt; kill switch steps.
- Precache size and first-load performance checked on a mid-range Android (NFR-2).

## Phase 8 · Pilot and go-live (W23–W25)

- Training: install on iOS and Android, PIN, keeping the app open while syncing, phone passcode required (security.md §2).
- Second field test on the pilot technicians' own phones (TP): note OS versions and `persisted()` in the diagnostics panel.
- Hypercare (W26–W27): watch sync conflicts, failed uploads and stuck queues daily.
