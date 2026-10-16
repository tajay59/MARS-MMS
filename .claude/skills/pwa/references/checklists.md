# Checklists

## Before merging any change to `src/sw/`, `src/offline/`, `vite.config.mts` (PWA part), Nginx caching or CSP

- [ ] Pre-flight questions in SKILL.md §1 answered in the PR description (one line each is enough).
- [ ] No API, mutation or upload response is cached; Cache Storage holds only the precache and `mms-tiles`.
- [ ] Every record change and its outbox op are written in one Dexie transaction, with no foreign `await` inside.
- [ ] Local data is deleted only after server confirmation (OFF-8).
- [ ] Every Dexie query is filtered by the current `user_id`.
- [ ] No token is written to any storage; refresh goes through `mms-auth-refresh`.
- [ ] Dexie version bumped with an upgrade test if the schema changed; `outbox` and `blobs` survive.
- [ ] Op payload version (`v`) set; the server accepts it (F8).
- [ ] No `skipWaiting()` outside the `SKIP_WAITING` handler; `sw.js` path unchanged.
- [ ] Every field route still loads offline from a cold start (Playwright, production build).
- [ ] Precache size checked in the build output (under about 5 MB); no file over the size limit.
- [ ] CSP: no inline script, no wasm, no new origin without a TRD §15 change.
- [ ] Works on iOS by design (ios-safari.md §1); real-device step named if `offline/` or `sw/` changed (TP).
- [ ] Vitest (with `fake-indexeddb`) and Playwright pass; axe clean in light and dark for touched screens.
- [ ] TRD, AFD or BSD updated if behaviour or a table changed; findings.md updated if a finding was decided.
- [ ] Developer docs site updated if the wiring changed (CLAUDE.md).

## Before each release that changes the worker

- [ ] The previous release's `/assets/` stay on the server (F9).
- [ ] `sw.js`, `index.html`, `theme-init.js`, `manifest.webmanifest` served `no-cache` (curl the headers on staging).
- [ ] Update prompt seen and accepted on staging from the previous build, in a browser tab and in the installed app.
- [ ] Offline cold start of `/unlock` and `/visits/:id/field` on staging.
- [ ] Kill-switch build procedure is in the runbook and was tested once (service-worker.md §6).

## Starting a phase

- [ ] Read [phase-map.md](phase-map.md) for the phase.
- [ ] Re-check versions and any fact the phase leans on against [sources.md](sources.md); update dates.
- [ ] Bring the findings due in this phase to the user ([findings.md](findings.md)).
- [ ] Propose the phase's diagrams for the docs site (CLAUDE.md "Charts"), including the PWA ones.
