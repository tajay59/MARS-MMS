# Caching: what the service worker may cache, and how

Sources: [The Offline Cookbook](https://web.dev/articles/offline-cookbook), [Learn PWA: Caching](https://web.dev/learn/pwa/caching), [Serving](https://web.dev/learn/pwa/serving), [Assets and data](https://web.dev/learn/pwa/assets-and-data), [Workbox: storage quota](https://developer.chrome.com/docs/workbox/understanding-storage-quota), [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/).

## 1. The rule

Cache Storage holds **static files only**. Data lives in Dexie. This is TRD §7.6 and §13.3, and it is also good practice: data in IndexedDB is keyed by user, versioned, queryable and deleted deliberately; HTTP responses in a cache are none of those.

| Resource | Strategy | Where defined |
|---|---|---|
| App shell: `index.html`, JS and CSS chunks, fonts, `theme-init.js`, icons, manifest | **Precache** (build-time list, revisioned) | `precacheAndRoute(self.__WB_MANIFEST)` |
| SPA navigations (`/visits/123/field`) | Precached `index.html` | `NavigationRoute` with denylist |
| Map tiles (our own PMTiles file, `/tiles/`) | Not a worker route: the page keeps each byte range it reads in `mms-tiles` (`features/map/tiles.ts`), as viewed only | TRD §13.3; F1, W7-9 |
| `/api/**` | **Never cached.** Network only (no route) | TRD §7.6 |
| Mutations and uploads | **Never cached.** Through the Dexie outbox | TRD §13.3 |
| `files.<host>` (presigned GET/PUT) | **Not routed.** Offline copies are blobs in Dexie `files` / `blobs` | TRD §7.1 |
| `/ws` | Not routed (WebSockets bypass the worker anyway) | — |

## 2. The strategies, and where each would fit

| Strategy | Behaviour | In AWS-MMS |
|---|---|---|
| Precache | Fetched at install, served from cache, replaced per revision | App shell |
| Cache first | Cache, else network and store | Tiles (only) |
| Network first | Network, else cache | **Not used.** It's how API caching sneaks in |
| Stale-while-revalidate | Cache now, refresh in background | Not used. A candidate for tiles if F1 is decided that way |
| Network only | Never cache | Default for everything not routed |
| Cache only | Never network | Not used |

Don't add a route without updating TRD §13.3 in the same change.

## 3. Precache: what goes in and how big

- `injectManifest.globPatterns`: `**/*.{js,css,html,woff2,png,svg,ico,webmanifest}`. Everything a field route needs must be precached, including lazily loaded route chunks, or `/visits/:id/field` breaks offline.
- **Fonts:** `@fontsource-variable` ships one `woff2` per unicode subset (latin, latin-ext, cyrillic, greek, vietnamese). The browser downloads only the subsets a page uses, but precache would download all of them. Precache `latin` and `latin-ext` only (`globIgnores` the rest). Names with other scripts still render, falling back to a system font offline.
- **Size budget:** keep the precache under about 5 MB. Check the list printed by `vite build`. ApexCharts is only needed on dashboards and reports; it's fine in the precache, but keep it lazy-loaded so it doesn't slow first paint.
- vite-plugin-pwa **fails the build** if a file exceeds `maximumFileSizeToCacheInBytes` (default 2 MiB). Raise the limit deliberately or split the chunk; don't silence it.
- `theme-init.js` is in `public/`, so it is copied to `dist/` and matched by the glob. Confirm it appears in the manifest.

## 4. Map tiles, in detail

- Leaflet loads tiles as `<img>`. Without CORS they are **opaque responses**: status 0, unreadable, and Chrome counts each one as about **7 MB** of quota. 2,000 opaque tiles would "use" 14 GB and push out real data. Fix both sides:
  - Leaflet `L.tileLayer(url, { crossOrigin: true })`, so requests are CORS. OSM tiles send `Access-Control-Allow-Origin: *` (checked 2026-10-16).
  - `CacheableResponsePlugin({ statuses: [200] })`, so an opaque response is never stored.
- `ExpirationPlugin({ maxEntries: 2000, maxAgeSeconds: 30 days, purgeOnQuotaError: true })`.
- CSP: the tile host is in `img-src` and `connect-src` (the worker fetches tiles), TRD §15.
- **Map tiles (F1, W7-9):** OSM's servers say "Offline use is not permitted", so production uses our own Protomaps extract. The worker does not touch it; `CachedRangeSource` stores `Range` answers (206 only, exact length) under a synthetic key `…?bytes=a-b`. A file name is never reused, because the keys are offsets. Never add prefetching of the whole file to the service worker: it is 552 MB.
- Attribution "© OpenStreetMap contributors" stays visible on every map.
- Logout clears `mms-tiles` (TRD §7.6: "clears runtime caches").

## 5. What breaks if you cache API responses

These are the reasons behind the TRD rule, for code review:

- **Shared devices:** user B sees user A's cached data after logout (TP shared-device test).
- **Scoping:** a client could be served a cached response fetched for staff.
- **Staleness:** a request's derived status (ADR-17) shown from a cache looks current but isn't.
- **Two sources of truth:** offline data would come from both Cache Storage and Dexie.
- **Auth:** cached `401`/`403` or responses keyed without the `Authorization` header.

If a feature seems to need cached API data, it needs a Dexie table and a prepare step instead (OFF-1).
