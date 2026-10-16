# Storage: quota, persistence and eviction

Sources: [MDN: Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria), [WebKit: Updates to Storage Policy](https://webkit.org/blog/14403/updates-to-storage-policy/), [WebKit: 7-day cap](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/), [web.dev: Storage for the web](https://web.dev/articles/storage-for-the-web), [Persistent storage](https://web.dev/articles/persistent-storage), [WebKit bug 271401](https://bugs.webkit.org/show_bug.cgi?id=271401). Checked 2026-10-16. This is risk **R4** (TRD §21).

## 1. Quotas per origin

| Browser | Best-effort | Persistent |
|---|---|---|
| Chrome, Edge | Up to 60% of total disk | Same 60% |
| Firefox | Smaller of 10% of disk or 10 GiB (group limit) | Up to 50% of disk (cap 8 TiB) |
| Safari 17+ / iOS 17+ (Safari and Home Screen apps) | Up to about 60% of total disk | Same |
| Safari before 17 | 1 GiB, then a permission prompt | — |

- Quotas are upper bounds, not promises. Free disk space limits you first on a full phone.
- Exceeding the quota throws `QuotaExceededError`. Catch it on every blob write and show the storage warning.
- `navigator.storage.estimate()` returns `{ usage, quota }`. Show it on `/sync` (OFF-4) and warn when `quota - usage` is under 1 GB (TRD §7.1, AFD §6).
- Opaque responses count about 7 MB each in Chrome (caching.md §4).

## 2. Eviction

- **Best-effort** origins can be deleted under storage pressure, least recently used first. **Persistent** origins are skipped.
- Eviction is **all or nothing per origin**: Dexie, Cache Storage and the worker go together. Unsynced field work would be lost with them.
- **Safari's 7-day rule:** with tracking prevention on, Safari deletes all script-written storage (IndexedDB, Cache Storage, worker registrations, localStorage) of a site after **seven days of Safari use without user interaction** on that site. **Home Screen web apps are not part of Safari** and keep their own day counter, which only advances when the app is used; WebKit doesn't expect their data to be deleted. One more reason field work must happen in the installed app on iOS (findings.md F2).

## 3. Persistent storage

`navigator.storage.persist()` asks to make the origin persistent; `navigator.storage.persisted()` reports the current state.

| Browser | How it's granted |
|---|---|
| Chrome, Edge | Silently, by heuristics (engagement, installed app, bookmarks, notification permission) |
| Firefox | Asks the user with a permission prompt |
| Safari | Silently, by heuristics, "like whether the website is opened as a Home Screen Web App" |

Known problem: WebKit bug 271401 (open, unassigned since March 2024) reports `persist()` always returning `false` in Safari 17, including for a Dock web app. Whether the state changes anyway is unanswered. **Don't assume `true` on iOS** (findings.md F3).

What AWS-MMS does (TRD §7.1, plus expert additions):

1. Call `persist()` on first field use (J5 step 4, Prepare for field), from the installed app on iOS. In Firefox this shows a prompt, so call it right after the user's tap with a sentence explaining why.
2. Store the result in `meta` and show it on `/sync`: "Storage: kept on this device" or "Storage: may be cleared by the browser".
3. Call `persisted()` at every app start; if it's `false`, call `persist()` again (heuristics change as the app is used).
4. Whatever the result, **upload as soon as there is signal**. Persistence lowers the risk; only syncing removes it.

## 4. Budgeting a visit

PRD NFR-1: up to 50 media items per visit; MED-6: video up to 200 MB, image up to 25 MB (images are resized to ≤ 2560 px before storage, so a few hundred KB to 2 MB each).

A heavy visit: 47 photos × ~1 MB + 3 videos × 200 MB ≈ **650 MB**, plus prepared manuals. Before **Start visit** and before each video capture, check `estimate()` and warn early. The W13 check (50 photos and 3 videos survive a restart on an iPhone) tests exactly this.

## 5. Other storage APIs

- **localStorage:** only `mms-theme` (TRD §13.2). Never data, never tokens.
- **Cache Storage:** the worker's precache and tiles only (caching.md).
- **OPFS / File System Access:** not used. IndexedDB blobs are enough and work everywhere.
- **Storage Buckets API:** Chromium only. Not used.
- **Cookies:** the refresh cookie lives outside these quotas and isn't evicted with site data. On iOS 17.2+, installing the app copies Safari's login cookies into it, so the user stays logged in after installing.
