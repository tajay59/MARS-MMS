# Offline data: Dexie, the outbox, blobs and sync

Sources: TRD §6.1, §7; PRD OFF-1 to OFF-11; AFD J5, J6, §6; BSD "Device store"; [Learn PWA: Offline data](https://web.dev/learn/pwa/offline-data); [Dexie docs](https://dexie.org/docs/), [best practices](https://dexie.org/docs/Tutorial/Best-Practices), [Vue tutorial](https://dexie.org/docs/Tutorial/Vue); [MDN Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API). Dexie **4.4.6** (2026-10-16).

Code lives in `frontend/src/offline/`: `db.ts` (schema), `session.ts` (PIN), `outbox.ts`, `sync.ts`, `blobs.ts`, `bundles.ts` (TRD §13.1).

## 1. Schema (`offline/db.ts`)

Tables are fixed by TRD §7.1. Indexes below are a proposal; record the final ones in BSD "Device store" when built.

```ts
import Dexie, { type EntityTable } from 'dexie'

export const db = new Dexie('aws-mms') as Dexie & {
  bundles: EntityTable<Bundle, 'visit_id'>
  files: EntityTable<LocalFile, 'media_id'>
  visits: EntityTable<LocalVisit, 'id'>
  outbox: EntityTable<OutboxOp, 'seq'>
  blobs: EntityTable<LocalBlob, 'media_id'>
  meta: EntityTable<MetaRow, 'key'>
}

db.version(1).stores({
  bundles: 'visit_id, user_id',
  files: 'media_id, user_id, visit_id',
  visits: 'id, user_id',
  outbox: '++seq, &op_id, user_id, [user_id+visit_id], status',
  blobs: 'media_id, user_id, state',
  meta: 'key',
})
```

- **`outbox` has a local auto-increment `seq`** for strict order, and a unique `op_id` (UUIDv7) for idempotency. UUIDv7s are time-ordered, but two ops in the same millisecond, or a phone clock change, shouldn't be able to reorder a visit.
- Only indexed fields go in `stores()`. Blobs and payloads are stored but not indexed.
- **One shared `db` instance** (singleton), imported everywhere, including the worker's sync core.
- IDs: `uuid` package `v7()`. `crypto.randomUUID()` is v4 only.

### Upgrades

- Forward-only, like server migrations. Bump `db.version(n)` and add `.upgrade(tx => …)` when data must be reshaped.
- **Never lose `outbox` or `blobs` rows in an upgrade.** Keep the upgrade functions for every version a real phone might still have.
- Test each upgrade path with `fake-indexeddb`: open at version n−1, write data, reopen at n, assert.
- Handle `db.on('versionchange')` (another tab upgraded): show "AWS-MMS was updated in another tab. Reload to continue."

## 2. Writing: one transaction per user action

The device mirrors the server's outbox rule: the change and its op are written together or not at all.

```ts
await db.transaction('rw', db.visits, db.outbox, async () => {
  await db.visits.put(updatedVisit)
  await db.outbox.add({
    op_id: v7(), v: 1, user_id, visit_id, type: 'work.save',
    payload: { visit_id, station_id, work_record, base_version },
    created_at: new Date().toISOString(), attempts: 0, status: 'pending',
  })
})
```

- **No non-Dexie `await` inside a transaction** (no `fetch`, no `crypto.subtle`, no timers). IndexedDB commits a transaction as soon as it has no pending requests; Dexie warns, but code after the foreign await runs outside it. Hash, resize and fetch **before** opening the transaction.
- Op types and payloads are TRD §7.2. Sensor actions and config versions travel inside `work.save`, with device-generated IDs.
- Each op carries `v` (payload version), so ops queued before an app update still sync (service-worker.md §3).
- Save on every step change (AFD J6: "Every step saves to the phone"). Don't keep unsaved state in Pinia alone.

## 3. Reading in Vue

Use `liveQuery`; it re-runs when the data changes, in this tab or another. A small composable avoids adding RxJS:

```ts
import { liveQuery } from 'dexie'
import { onScopeDispose, shallowRef } from 'vue'

export function useLiveQuery<T>(query: () => T | Promise<T>) {
  const value = shallowRef<T>()
  const error = shallowRef<unknown>()
  const sub = liveQuery(query).subscribe({ next: v => { value.value = v }, error: e => { error.value = e } })
  onScopeDispose(() => sub.unsubscribe())
  return { value, error }
}
```

`value` is `undefined` until the first result: render a loading state, not an empty state. The sync badge counts (OFF-4) are live queries on `outbox` and `blobs` for the current user.

## 4. Blobs and media

- Photos: read capture time (EXIF or `lastModified`) **first**, then resize with `createImageBitmap` + canvas to ≤ 2560 px, JPEG 0.85 (TRD §7.5). `createImageBitmap` applies EXIF orientation by default. Do the resize in a Worker with `OffscreenCanvas` where available to keep the UI responsive; test with the TP fixtures (iPhone HEIC, Android JPEG).
- Videos: store the `File` as recorded. A 200 MB file is copied into IndexedDB; check quota first (storage.md).
- SHA-256 for a 200 MB video: `crypto.subtle.digest` needs the whole file in memory. See **findings.md F4** before building.
- Offline copies of manuals and configs are blobs in `files` (never presigned URLs). Show them with `URL.createObjectURL(blob)` and revoke the URL when the view closes.
- Camera: `<input type="file" accept="image/*,video/*" capture="environment">` (TRD §13.2).

## 5. Sync (`offline/sync.ts`)

Protocol: TRD §7.3. The runner, as a sketch:

```ts
export async function runSync(reason: SyncReason): Promise<SyncResult> {
  return navigator.locks.request('mms-sync', { ifAvailable: true }, async (lock) => {
    if (!lock) return { skipped: 'already-running' }          // another tab or the worker is syncing
    const token = await ensureAccessToken()                     // under 'mms-auth-refresh' (TRD §6.1)
    if (!token) return { needsLogin: true }                     // AFD §6: "Log in to finish syncing"
    await uploadPendingBlobs(token)                             // media first, resumable 8 MiB parts
    await pushOps(token)                                        // ≤ 100 ops per request, in seq order
    return { ok: true }
  })
}
```

- **Lock names:** `mms-auth-refresh` (TRD) and `mms-sync` (proposed, findings.md F11). Web Locks work in tabs and in the worker.
- **Uploads:** `POST /uploads` is idempotent by `media_id`. PUT only the parts missing from `parts_done[]`, save each part's `ETag` as it completes, then `complete`. A dropped connection resumes from the next part (OFF-6). The files host exposes `ETag` via CORS (TRD §2.1).
- **`media.attach` is queued after its upload completes** (TRD §7.2).
- **Results per `op_id`:** `applied` or `duplicate` → delete the op; `conflict` → keep the op and the local data, store the reason code and server copy, show it under "Needs attention" with **Export**; `error` → keep, `attempts++`, back off. **A failed op stops later ops for that visit only.**
- **Delete local copies only after the server confirms** (OFF-8): blobs after `complete` and their `media.attach` is applied; bundles after the visit is synced and ended (BSD).
- **Triggers:** `online` event, app start, every 5 minutes while online, "Sync now", and Background Sync where supported (service-worker.md §5). Debounce so triggers don't stack; the lock makes overlaps harmless anyway.
- **Backoff:** for network errors, exponential with jitter (for example 2 s doubling to 5 min). Reset on success or on "Sync now".
- `navigator.onLine` only says a network interface exists. Treat a failed request as offline; don't block "Sync now" on `onLine`.
- iOS stops JavaScript when the app is in the background or the screen locks. Uploads pause and resume next time (ios-safari.md). Tell the user to keep the app open while it syncs.

## 6. Users, logout and shared devices

From TRD §6.1 and §7.6, BSD "Device store":

- Every row carries `user_id`. Every query filters by the current user, including the badge counts.
- **Logout or change of user:** delete that user's `bundles`, `files`, `visits`, the offline profile and PIN verifier in `meta`; clear runtime caches (`CLEAR_RUNTIME_CACHES` to the worker). **Keep `outbox` and `blobs`**, tagged with `user_id`; they sync only when that user logs in again.
- A second user on the device never sees, counts or syncs the first user's queued work.

## 7. Conflicts and export

TRD §7.4 and AFD §6 define each reason code and its message. There is no merge (ADR-18). The device copy stays until it is exported or an admin resolves it.

Export (proposal): one file per conflicted station with the work record JSON and its media, shared with the Web Share API (`navigator.share({ files })`, supported on iOS and Android) or downloaded where sharing isn't available.

## 8. The offline PIN session (`offline/session.ts`)

TRD §6.1, ADR-20, AUTH-12:

```ts
async function pinVerifier(pin: string, salt: Uint8Array): Promise<ArrayBuffer> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveBits'])
  return crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations: 310_000 }, key, 256)
}
```

- Salt: 16 random bytes from `crypto.getRandomValues`. Store salt, verifier, `offline_until`, failed count and the profile in `meta`. Never the PIN, never a token.
- Compare the derived bytes in full (no early exit). Count failures in Dexie before showing the result, so killing the app can't reset the count. Five failures disable unlock until the next online login; data stays.
- 310,000 iterations take roughly a second on a mid-range phone; show a progress state on `/unlock`.
- `/unlock` is a public-shell page and must load fully offline from the precache.
