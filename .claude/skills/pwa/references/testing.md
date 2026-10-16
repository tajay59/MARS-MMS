# Testing and checking the PWA

Sources: TP (Test levels, Offline sync and the field session, Frontend quality, Tests by phase); [Chrome DevTools: PWAs](https://developer.chrome.com/docs/devtools/progressive-web-apps); [Edge DevTools: PWAs](https://learn.microsoft.com/en-us/microsoft-edge/devtools/progressive-web-apps/); [Lighthouse PWA](https://developer.chrome.com/docs/lighthouse/pwa); [Playwright: Service workers](https://playwright.dev/docs/service-workers); [Learn PWA: Tools and debug](https://web.dev/learn/pwa/tools-and-debug).

## 1. Levels (from TP, PWA view)

| Level | Tool | PWA scope |
|---|---|---|
| Frontend unit | Vitest + `fake-indexeddb` + MSW | Dexie schema and upgrades, outbox writes, sync runner (results, ordering, stop-per-visit, backoff), blob upload resume, PIN session, refresh lock, logout cleanup |
| End to end | Playwright against the Compose stack | J5 prepare, J6 offline visit, `/unlock`, `/sync`, update prompt, CSP violations, axe in light and dark |
| Visual | Playwright screenshots | Field shell at 390 px in both themes |
| Field test | Real iPhone and Android | W13 check, W15 field test, pilot |

## 2. Vitest patterns

- `import 'fake-indexeddb/auto'` in the setup file. Create a fresh database name per test, or `await db.delete()` after each.
- **Fault injection** (TP): throw from the MSW handler mid-upload, then rerun and assert only missing parts are sent; expire the token during sync; make a blob write throw `QuotaExceededError`; kill a transaction halfway (throw inside it) and assert neither the record nor its op was written.
- **Properties:** syncing the same batch twice gives the same state; conflicts leave device copies in place.
- **Upgrade tests:** open at version n−1 with data, upgrade, assert `outbox` and `blobs` survive.

## 3. Playwright and the service worker

- Playwright's service-worker APIs (routing worker requests, `context.serviceWorkers()`) are documented as **Chromium only**. TP plans "Playwright offline in Chromium and WebKit with the real service worker"; whether WebKit runs and controls pages with our worker under Playwright must be proven in W14 before relying on it (F6). The real iPhone stays the proof for iOS.
- Run against a **production build** (`vite build` + preview or the Compose stack). The dev server's worker is not the real one.
- Default `serviceWorkers: 'allow'`. Wait for control before going offline:

```ts
await page.goto('/')
await page.evaluate(async () => { await navigator.serviceWorker.ready })
await page.reload()                                   // now controlled
await context.setOffline(true)
await page.goto('/visits/' + visitId + '/field')      // must load from precache
```

- The J6 offline test (TP): whole visit offline, reload, unlock with PIN, go online, assert every record and file on the server.
- **Update prompt test:** deploy build A, open the app, deploy build B (or swap `sw.js`), trigger `registration.update()`, assert the snackbar, accept, assert reload and new version.
- **Shared-device test:** user A prepares and logs out; user B logs in; nothing of A is shown or served (TP).
- **CSP:** fail on any console CSP violation (TP), including in the worker.

## 4. Manual checks in DevTools

Application panel (Chrome or Edge):

- **Manifest:** installability errors and warnings, icons, `id`. This replaces Lighthouse's PWA category: **PWA testing in Lighthouse is deprecated** (F7).
- **Service workers:** state (installed, waiting, active), **Update on reload**, **Offline**, **Bypass for network**, push a `sync` event by tag (`mms-sync`).
- **Storage:** usage, **Clear site data**, and **Simulate custom storage quota** to test `QuotaExceededError` and the under-1-GB warning.
- **IndexedDB:** inspect the Dexie tables.
- **Cache storage:** confirm only the precache and `mms-tiles` exist and that no `/api/` URL is in them.
- Network panel: throttle to "Slow 4G" and toggle offline mid-upload.

**Reaching the dev PC from a phone** (learned in the Phase 0 spike): `*.localhost` names mean the phone itself, so every origin the page uses must be reachable by the PC's LAN address. The dev PC's firewall (Wi-Fi profile Public, ESET) lets port 8080 in but silently drops others such as 8081; a dropped request shows as "Failed to fetch", like a CORS error. Keep one port and give the second origin a host name such as `<LAN_IP>.sslip.io`, which resolves to the PC. For service worker tests the phone also needs HTTPS with a trusted certificate (vite-pwa-vue.md §6).

Android: `chrome://inspect` on desktop Chrome with the phone on USB debugging. iPhone: Safari Web Inspector on a Mac, or the diagnostics panel (ios-safari.md §4).

## 5. Real-device checklists

**W13 (iOS storage and session):** install from Safari; log in; set PIN; prepare a visit; with no signal, capture 50 photos and 3 videos; restart the phone; open from the Home Screen; unlock; all media present; note `persisted()` and `estimate()`.

**W15 field test (both phones, IP Phase 5 exit):** full visit with no signal, restart and PIN unlock mid-visit, a station whose owner changes while offline, sync on return, then: no lost or duplicated records or files; syncing again changes nothing; the owner-change conflict can be exported.

**Every release touching `src/offline/` or `src/sw/`:** the TP field-test level applies.

## 6. Definition of done additions for PWA work

- Works offline from a cold start (precache) for every field route.
- Light and dark, axe clean, including `/unlock` and `/sync`.
- No API URL in Cache Storage; logout leaves no user data except queued ops and blobs.
- Tested in Chromium and WebKit where Playwright allows; real-device step named when the change touches `offline/` or `sw/`.
