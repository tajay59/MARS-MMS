# Pitfalls: what to catch in review

Each line is a mistake that is common in PWA code (several appear in popular community PWA skills) and the rule it breaks here.

## Service worker

| Mistake | Why it's wrong here | Do instead |
|---|---|---|
| `self.skipWaiting()` in `install` | New worker takes over mid-visit; old tabs lose their chunks | Only on the `SKIP_WAITING` message (service-worker.md §3) |
| `registerType: 'autoUpdate'` or reloading on `controllerchange` without asking | Reloads a technician mid-step | Prompt; `onNeedReload` flushes Dexie first |
| Network-first or stale-while-revalidate for `/api/` | Breaks TRD §7.6; shared-device leaks | No API route at all |
| A catch-all offline page for every failed request | Answers API and image requests with HTML | `NavigationRoute` only, with the denylist |
| `cache.addAll` of a hand-written list | One 404 fails the install; list drifts from the build | `precacheAndRoute(self.__WB_MANIFEST)` |
| Hard-coded `CACHE_NAME = 'v1'` and no cleanup | Old files kept for ever | Workbox revisions + `cleanupOutdatedCaches()` |
| Caching opaque responses | ~7 MB quota each in Chrome | `crossOrigin: true` on tiles + `CacheableResponsePlugin({ statuses: [200] })` |
| Renaming `sw.js` or moving it | Old worker stays installed on every phone | Same path for ever |
| Inline registration script | Blocked by `script-src 'self'` | `injectRegister: false` + `useRegisterSW` |
| Business logic in the worker | Hard to test, hard to update | Worker routes and caches; logic in `src/offline/` |
| Routing `files.<host>` through the worker | Breaks presigned PUTs and video range requests | Leave it to the network |

## Offline data and sync

| Mistake | Why it's wrong here | Do instead |
|---|---|---|
| `fetch` or `crypto.subtle` awaited inside a Dexie transaction | The transaction commits early; later writes aren't atomic | Do async work before the transaction |
| Writing the record and the op in separate transactions | A crash leaves a change that never syncs | One `rw` transaction for both |
| Deleting local data when the request is sent | Loses work if the response never arrives | Delete only on `applied` / `duplicate` (OFF-8) |
| Treating `navigator.onLine` as "server reachable" | Captive portals, dead links | A failed request means offline |
| Last-write-wins or field merge on conflicts | ADR-18: no merge | Keep the device copy; show the reason; export |
| One failed op stops the whole queue | TRD §7.3: only later ops for that visit stop | Per-visit stop |
| `crypto.randomUUID()` for IDs | v4, not time-ordered | UUIDv7 (`uuid` `v7()`) |
| Storing presigned URLs for offline use | They expire | Store blobs |
| Queries without `user_id` | User B sees or syncs user A's work | Filter every query by the current user |
| Rewriting queued ops during an upgrade | Changes what the server receives | Ops are immutable; version them (F8) |
| Background Sync as the only trigger | iOS and Firefox never fire it | `online`, app start, 5-minute timer, "Sync now" |
| Reading a 200 MB video into an `ArrayBuffer` | Out of memory on iPhones | Chunked hashing (F4) |
| Two tabs syncing at once | Double uploads, confusing UI | Web Lock `mms-sync` |

## Auth and session

| Mistake | Why it's wrong here | Do instead |
|---|---|---|
| Access token in localStorage or IndexedDB | TRD §6.1: memory only | Pinia memory; refresh cookie |
| Refreshing without the Web Lock | Reuse detection revokes the family | `mms-auth-refresh` + BroadcastChannel |
| Calling the PIN "encryption" | It isn't; device encryption protects data at rest | Gate wording; passcode in training |
| Resetting failed-PIN count on reload | Bypasses the five-attempt lockout | Store the count before showing the result |

## Install and UX

| Mistake | Why it's wrong here | Do instead |
|---|---|---|
| Waiting for `beforeinstallprompt` on iOS | It never fires | iOS instructions sheet |
| Install banner on first visit, for everyone | Noise; clients don't need it | Staff, at Prepare for field |
| Relying on the browser back button or pull-to-refresh | Absent in standalone | In-app navigation; "Sync now" |
| `navigator.standalone` for detection | Deprecated | `matchMedia('(display-mode: standalone)')` |
| Assuming maskable icons work on iOS | Ignored | Opaque 180 px apple-touch-icon |
| Promising features iOS lacks (push, background sync, NFC) | Not available | Check ios-safari.md first |
