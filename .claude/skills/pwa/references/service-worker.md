# Service worker: lifecycle, the AWS-MMS worker, updates, kill switch

Sources: [web.dev lifecycle](https://web.dev/articles/service-worker-lifecycle), [Learn PWA: Service workers](https://web.dev/learn/pwa/service-workers), [Update](https://web.dev/learn/pwa/update), [Vite PWA injectManifest](https://vite-pwa-org.netlify.app/guide/inject-manifest.html), [Workbox: handling updates](https://developer.chrome.com/docs/workbox/handling-service-worker-updates), [Workbox: remove buggy service workers](https://developer.chrome.com/docs/workbox/remove-buggy-service-workers), vite-plugin-pwa source (`src/client/build/register.ts`, read 2026-10-16).

## 1. Lifecycle in one page

1. **Register.** The page calls `register('/sw.js')`. Scope `/` (the file sits at the root).
2. **Install.** The new worker downloads and precaches every file in `self.__WB_MANIFEST`. If one file fails, the install fails and the old worker stays. That is the safety net.
3. **Waiting.** If an older worker controls open pages, the new one **waits**. It won't take over while any tab of the app is open, unless it calls `skipWaiting()`.
4. **Activate.** Old worker gone; `cleanupOutdatedCaches()` removes precache entries from older revisions.
5. **Control.** Open pages switch to the new worker (`controllerchange`). On the very first install, the open page stays uncontrolled until reload unless the worker calls `clients.claim()`.

The browser checks for a new `sw.js` on navigation and on `registration.update()`. It compares bytes, so any change in the precache manifest (a new build) makes a new worker.

**Why waiting matters for AWS-MMS:** a technician mid-visit runs JS from build N. If build N+1's worker took over and deleted build N's precached chunks, the next lazy-loaded route would fail offline. Waiting until the user agrees protects them.

## 2. The AWS-MMS worker (`frontend/src/sw/sw.ts`)

A blueprint for Phase 5 (and the minimal Phase 1 version if F5 is accepted). Keep the worker **small**: routing and caching only. Business logic lives in `src/offline/`.

```ts
/// <reference lib="webworker" />
import { CacheableResponsePlugin } from 'workbox-cacheable-response'
import { clientsClaim } from 'workbox-core'
import { ExpirationPlugin } from 'workbox-expiration'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { CacheFirst } from 'workbox-strategies'

declare let self: ServiceWorkerGlobalScope

// 1. App shell: everything the build emitted (JS, CSS, fonts, index.html, theme-init.js, icons)
cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)

// 2. SPA navigations get the precached index.html, offline included.
//    Never answer API, WebSocket, internal or well-known paths with HTML.
registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html'), {
  denylist: [/^\/api\//, /^\/ws(\/|$)/, /^\/internal\//, /^\/\.well-known\//],
}))

// 3. Map tiles, as viewed (TRD §13.3). Read caching.md and findings.md F1 before changing.
registerRoute(
  ({ url, request }) => url.origin === 'https://tile.openstreetmap.org' && request.destination === 'image',
  new CacheFirst({
    cacheName: 'mms-tiles',
    plugins: [
      new CacheableResponsePlugin({ statuses: [200] }),          // never cache opaque (status 0) responses
      new ExpirationPlugin({ maxEntries: 2000, maxAgeSeconds: 30 * 24 * 60 * 60, purgeOnQuotaError: true }),
    ],
  }),
)

// 4. Everything else (API, files host, WebSocket) is not routed: it goes to the network untouched.

// 5. Messages from the page
self.addEventListener('message', (event) => {
  switch (event.data?.type) {
    case 'SKIP_WAITING':            // the user accepted the update prompt
      self.skipWaiting()
      break
    case 'CLEAR_RUNTIME_CACHES':    // logout or change of user (TRD §7.6)
      event.waitUntil(caches.delete('mms-tiles'))
      break
  }
})

// 6. First install only: control the open page at once, so tiles viewed in the first session are cached.
clientsClaim()

// 7. Background Sync (Chromium only; never the only trigger, TRD §7.3). See §5.
self.addEventListener('sync', (event: Event) => {
  const e = event as SyncEvent
  if (e.tag === 'mms-sync') e.waitUntil(syncFromWorker())
})
```

Notes:

- **Never call `skipWaiting()` during install.** Only on `SKIP_WAITING` from the prompt.
- `clientsClaim()` matters only for pages that have no controller. It doesn't change the update flow: pages already controlled switch to a new worker when it activates anyway.
- `SyncEvent` isn't in TypeScript's WebWorker lib. Declare a minimal interface in `src/sw/types.d.ts`.
- `import.meta.env.MODE`, `DEV` and `PROD` are available inside the worker.
- No `navigationPreload`: navigations are answered from precache, so there is nothing to preload.
- Don't route requests to the `files.` host. Presigned GETs and PUTs must hit the network unchanged, and media streaming needs range requests ([web.dev](https://web.dev/articles/sw-range-requests)).

## 3. Updates: the prompt flow

How vite-plugin-pwa behaves in prompt mode (read in its source):

- When a new worker is **waiting**, every open tab gets `onNeedRefresh` (`needRefresh.value = true` in `useRegisterSW`).
- When the user accepts in one tab, `updateServiceWorker()` sends `SKIP_WAITING`. When the new worker takes control, **every tab that showed the prompt reloads**, or calls `onNeedReload` if you passed one.
- `useRegisterSW` (Vue) defaults to `immediate: true`.

AWS-MMS rules:

1. **Prompt, don't force.** A Vuetify snackbar: "A new version is ready." with **Reload**. Text checked against DBD voice with `writing-guidelines`.
2. **Not in the middle of field work.** In the field shell, show the prompt only on the station list, `/sync` or after **End visit**, never on a step with the camera or a form open.
3. **Pass `onNeedReload`** that flushes pending Dexie writes and saves the current route before reloading, so a tab reloaded by another tab's accept loses nothing.
4. **Check hourly while online**, and on `visibilitychange` to visible (see vite-pwa-vue.md for the code).
5. **Keep the previous release's hashed assets on the server** for at least a few days after each deploy. A tab still on build N will lazy-load build N's chunks; if they 404, the route breaks. Also handle `router.onError` for failed dynamic imports with "A new version is ready" + reload.
6. **The file name `sw.js` and its scope never change.** A renamed worker leaves the old one installed on every phone.

### Compatibility across versions (expert rule)

A phone may hold ops queued by build N for days before syncing with build N+1, against a server that has moved on too.

- **Every op payload carries a schema version** (e.g. `v: 1`). The client never rewrites queued ops on upgrade, and the server's `/sync` accepts the last N versions (record the range in the TRD when built).
- **Dexie upgrades must keep queued data.** Never drop or reshape `outbox` or `blobs` in a version upgrade without a tested migration.
- **Old tab, new schema:** when another tab opens the database at a higher version, Dexie closes the old connection (`versionchange`). Show "AWS-MMS was updated in another tab. Reload to continue." rather than failing silently.

## 4. Nginx and registration details

- `sw.js`, `index.html`, `theme-init.js`, `manifest.webmanifest`: `Cache-Control: no-cache` (TRD §2.1 lists the first three; add the manifest).
- Hashed assets in `/assets/`: one year, immutable.
- Register with `updateViaCache: 'none'` default behaviour (browsers already bypass the HTTP cache for `sw.js` itself; `no-cache` covers imported scripts).
- The worker must be same-origin and served as JavaScript. `worker-src 'self'` in the CSP allows it.
- Register **after** the app has mounted (the plugin does this; don't register in `theme-init.js`).

## 5. Background Sync, carefully

TRD §7.3 lists Background Sync as one trigger "where supported; not on iOS". Expert design (proposal, confirm in Phase 5):

- The page registers `registration.sync.register('mms-sync')` after queuing an op while offline (feature-detect `'sync' in registration`).
- In the worker, `syncFromWorker()`:
  1. If any window client is open, `postMessage({ type: 'RUN_SYNC' })` to it and return. The page already holds the auth state and the sync runner.
  2. With no window open, run the same sync core from `src/offline/sync.ts`, which must therefore have **no DOM, Vue or Pinia imports**. It takes the `mms-sync` and `mms-auth-refresh` Web Locks like any tab (Web Locks and Dexie both work in workers), calls `/refresh` with the cookie, and syncs.
- Browsers limit how long a `sync` event may run. Work in a time budget, upload whole parts only, and let the promise reject if work remains so the browser retries later.
- iOS never fires `sync`. The `online` event, app start, the 5-minute timer and "Sync now" must be enough on their own.

## 6. Kill switch (ready before the first production release)

If a broken worker ships, phones keep running it. Two tools:

1. **Fix forward:** deploy a corrected build. Waiting workers reach users on their next navigation or hourly check.
2. **Self-destroying worker:** build with vite-plugin-pwa's `selfDestroying: true`. The emitted `sw.js` unregisters itself and the page stops using a worker. Ship it at the **same path** (`/sw.js`).

Before using 2, remember what it breaks: no offline shell, no tile cache. **Dexie data and queued ops are not touched** (they are IndexedDB, not Cache Storage), so no field work is lost. Write the steps into the release runbook (IP Phase 7) and test the kill switch once on staging.
