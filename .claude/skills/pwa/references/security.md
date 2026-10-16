# Security in the PWA

Sources: TRD §2.1, §6.1, §7.6, §15; BSD "Data classification and encryption"; TP "Frontend quality" and "Offline sync and the field session"; R11.

## 1. Tokens

- **Access token:** memory only (Pinia; the worker keeps its own in memory). Never in IndexedDB, Cache Storage, localStorage or a URL.
- **Refresh token:** httpOnly, Secure, SameSite=Strict cookie on path `/api/v1/auth`. JavaScript can't read it; the browser sends it to `/refresh` from pages and from the worker (same origin).
- **One refresh at a time:** take the Web Lock `mms-auth-refresh`, call `/refresh`, share the new token over `BroadcastChannel`; others wait. The server's 30-second grace window covers races (TRD §6.1, TP refresh-race test).
- The worker never adds `Authorization` headers to page requests and never caches responses that carry one.

## 2. The offline PIN is an access gate, not encryption

- The PIN verifier (PBKDF2-SHA-256, 310,000 iterations, random salt) stops a casual finder of the phone from opening the field screens. It does **not** encrypt Dexie: IndexedDB data is readable by anyone who can inspect the device's browser storage.
- At-rest protection comes from **device encryption** (phone passcode), which BSD and R11 rely on. Field phones must have a passcode; include it in the training checklist (IP Phase 8).
- No token is stored, so a stolen phone can't sync or reach the server. Admins disable the user; the offline session ends at `offline_until`.
- Five wrong PINs disable unlock. Store the failure count before showing the result.

## 3. CSP and the worker

TRD §15: `script-src 'self'; worker-src 'self'; connect-src 'self' https://files.<host> https://tile.openstreetmap.org wss://<host>; img-src 'self' https://files.<host> https://tile.openstreetmap.org data: blob:; media-src 'self' https://files.<host> blob:`.

- Register the worker from bundled code (`injectRegister: false` + `useRegisterSW`). No inline registration script.
- The worker is same-origin at `/sw.js`; `worker-src 'self'` covers it and any Web Worker used for image resizing.
- **No WebAssembly** unless the CSP adds `'wasm-unsafe-eval'` (it doesn't). This rules out wasm hashing libraries (F4).
- `blob:` is allowed for images and media, which local previews of captured photos and offline documents need.
- Playwright fails on any CSP violation (TP), so an inline script or CDN font is caught.

## 4. Shared devices and logout

TRD §7.6, TP "Shared device":

- The worker caches no API responses, so nothing of user A can be served to user B.
- Logout deletes the user's `bundles`, `files`, `visits`, offline profile and PIN verifier, and clears runtime caches. Queued `outbox` and `blobs` stay, tagged with `user_id`, and only that user can sync them.
- Every Dexie query filters by the current `user_id`.
- Pinia stores are reset on logout; a reload isn't required but is the safest end state.

## 5. Files and visibility

- Presigned URLs expire and are never stored for offline use; offline files are blobs (TRD §7.1).
- Files are staff-only until the owning service shares them (ADR-19). A prepared bundle contains only what the staff user could already see.
- The worker doesn't touch `files.<host>` traffic.

## 6. Messages between page, tabs and worker

- `BroadcastChannel` and worker `postMessage` are same-origin only. Still, validate message `type` and shape before acting, and never pass tokens in a message the page doesn't need.
- `SKIP_WAITING` and `CLEAR_RUNTIME_CACHES` are the worker's only commands (service-worker.md §2). Add new ones deliberately.

## 7. Updates as a security tool

- A security fix reaches phones only when the new worker activates. Keep the hourly update check and the prompt visible (service-worker.md §3).
- The self-destroying worker is the emergency brake (service-worker.md §6).
- The Phase 7 security review should cover the worker, the CSP, logout cleanup and the PIN session (IP Phase 7, TRD §15).
