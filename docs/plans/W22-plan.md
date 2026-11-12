# W22 plan: TOTP for admins (buffer week 2)

Date: 2026-11-12. W22 is the second buffer week (IP.md, "Buffer W21–W22"). The product owner answered ASVS deviation D-2 on 2026-11-12: **build a second factor (TOTP) for admins before the pilot.** This plan is that feature. Phase 8 (pilot) starts after it, so it is the one thing between W21 and W23.

Answers already given (2026-11-12):

| Question | Answer |
|---|---|
| How strict on the day it ships? | **Required for admins, with a 7-day setup window.** After the window, sign-in is blocked until the admin is enrolled. |
| Who else? | **Any staff may opt in** (admin, technician, viewer) from My profile. Clients cannot. |
| Lost phone? | **10 one-time recovery codes**; another admin can reset someone's TOTP; `python -m app.cli reset-totp` on the server as the last resort. |

## Goal

An admin signs in with a password and a 6-digit code from an authenticator app. Nothing changes for technicians in the field: the offline PIN, the 30-day session and the refresh flow stay as they are. The ASVS review line 2.2.x / 2.8.x moves from "deviation" to "met".

## PWA pre-flight

| Question | Answer |
|---|---|
| Device | Admins use desktops and phones. The sign-in page gets a second step; the code field must use `autocomplete="one-time-code"`, `inputmode="numeric"` and work with the phone's keyboard suggestion. |
| Network | The second step needs a connection (sign-in always does). **Refresh does not ask for a code**: MFA is at sign-in only, so a technician or admin who is already signed in is never interrupted, and a refresh in the service worker or a background tab keeps working. |
| Lifecycle | `/unlock` (offline PIN) is untouched: it opens the cached profile with no token. `session.reconnect()` signs in "for real" when signal returns; check in slice 1 that it uses the refresh cookie and not `/login`. If the refresh session has expired (30 days), the admin signs in again and meets the code step. |
| Data loss | None: no sync op, Dexie table or payload changes. Enforcement applies to sign-in, never to a live session, so nobody is cut off mid-visit and queued ops sync as before. One case to check in slice 1: a person with both the admin and technician roles who is blocked at sign-in after the window has no way to sync on a new phone until enrolled; the window and the banner are the mitigation, and the plan treats a blocked sign-in as a prompt to enrol, not a lock. |
| Storage | No new browser storage. The challenge lives in memory on the page. |
| Caching, CSP | No change. Auth responses stay `no-store`. The QR for enrolment is drawn in the browser by the existing lazy `qrCode.ts` (not precached; the page needs a connection anyway). |
| Old clients | A phone with the old app and an admin who has TOTP would get a response it cannot read. `LoginIn` gets an optional `supports_mfa`; without it the server answers **401 `update_required`** ("Reload the app, then sign in") instead of a challenge. The update prompt (F19 fix) takes the phone to the new release. |
| Proof | Python unit tests with RFC 6238 vectors, API tests, the authorization matrix and leak checks, Vitest, Playwright (an admin with TOTP signs in; an admin in the window sees the banner; a lost-phone reset), axe light and dark, and the offline shell and update specs unchanged. |

## Design (decisions W22-1 to W22-10, proposed)

- **W22-1 The flow.** `POST /api/v1/auth/login` checks the password exactly as now. If the user has TOTP enabled, it creates **no session** and answers `200 {"mfa_required": true, "challenge": "<opaque>", "expires_in": 300}`. `POST /api/v1/auth/login/totp` with `{challenge, code}` (or `{challenge, recovery_code}`) then returns the normal `TokenResponse` and sets the refresh cookie. The challenge is a random token whose hash is stored in Redis (`auth:mfa:<hash>` → user id, 5 minutes, at most 5 tries, single use). It is not a JWT and carries no rights.
- **W22-2 Failures share the account lock.** A wrong code counts on the same per-account throttle as a wrong password (5 failures, 15 minutes; `throttle.py`), and the answer never says whether the password or the code was wrong beyond "the code is incorrect". Nginx's per-IP limit (10 a minute) covers `/login/totp`.
- **W22-3 The algorithm.** RFC 6238 TOTP: HMAC-SHA1, 6 digits, 30 s step (what every authenticator app supports), a window of one step either side for clock drift, and **replay refused**: the last accepted step is stored and a code at or before it fails. Pure code in `domain/totp.py` (no dependency; about 30 lines; tested with the RFC's vectors). The server clock is the injectable `ctx.clock`.
- **W22-4 The secret is encrypted at rest.** 20 random bytes, shown once as base32 and as an `otpauth://` URI (issuer `MARS-MMS`), stored encrypted with AES-GCM (`cryptography`, already an auth dependency) under `AUTH_TOTP_KEY` (32 bytes, base64). Mongo alone never gives the secret. **The key must be on every host's `infra/.env` before the deploy** (the stack refuses to start without it), and `.env.example`, the dev stack and CI get a dev value.
- **W22-5 User fields (BSD).** `users.totp = {secret_enc, enabled_at, last_step}` or absent; `users.recovery_codes = [{hash, used_at}]` (10 codes, 10 characters of base32 in two groups, SHA-256 hashed, shown once, regenerating replaces all); `users.mfa_grace_until` (set on the first sign-in after the release, and when a user is given the admin role, to now + `AUTH_TOTP_GRACE_DAYS`, default 7). Migration `0004`.
- **W22-6 Enforcement.** `AUTH_TOTP_REQUIRED_ROLES=admin`. An admin without TOTP inside the window signs in as today, and the token response carries `mfa_setup: {required_by}` so the app shows a banner. After the window, `/login` answers `{"mfa_required": true, "enrol": true, "challenge": …}`: the challenge allows only `POST /login/totp/enrol/begin` and `/confirm`, then signs in. No half-session is ever issued, so no other service has to learn about MFA.
- **W22-7 Enrolment and management** (signed in, from My profile): `POST /me/totp/begin` (password required) returns the secret and URI; `POST /me/totp/confirm {code}` enables it and returns the recovery codes once; `POST /me/totp/recovery-codes` regenerates (password and code); `DELETE /me/totp` (password and code) is **refused for a role that requires it** (admins) and allowed for staff who opted in. Enabling does not end other sessions; disabling or a reset does (the revocation list, AUTH-11).
- **W22-8 Lost phone.** An admin signs in with a recovery code (single use, the answer says how many are left). Another admin resets someone: `POST /api/v1/users/{id}/totp/reset` (admin only, never on oneself, audited, ends that user's sessions, restarts their window). With no other admin, `python -m app.cli reset-totp --email …` on the server, which writes the same audit event.
- **W22-9 Events and audit.** New security events in `mms_common.events.auth`: `auth.totp_enrolled`, `auth.totp_disabled`, `auth.totp_reset` (with the admin who did it), `auth.mfa_failed`, `auth.recovery_code_used`. Never the secret, a code or a hash. The audit chain records them by default (AUD-1). Event schema changes mean the rollback guard refuses a rollback over this release without `--allow-older-schema`: that is intended.
- **W22-10 Passwords and invitations.** A password reset does not sign anyone in (`/password-reset/confirm` answers 204), so it cannot skip the code. An invitation to an admin signs in at acceptance inside the window, as any first sign-in. Changing a password does not change TOTP.

## Slices

1. **Back end** (`feat/p7-w22-totp-api`). `domain/totp.py`, `domain/recovery.py`, `repo/totp.py`, `repo/mfa_challenges.py` (Redis), the routes above in `api/totp_routes.py` plus the changes to `session_routes.py`, `AUTH_TOTP_*` settings, migration `0004`, events, `reset-totp` CLI, OpenAPI export. Tests: RFC vectors, window and replay, challenge single use and attempts, the shared lock, the attacks in the existing suite repeated with a second factor (no session before the code, an old challenge, another user's challenge, a recovery code twice), the authorization matrix (every new route) and the leak check, no secret or code in any log, event or audit record. Fix the test seeds: `mms_common.testing.seed` gets an admin with TOTP and a known secret for the other services' and Playwright's use; check no counts break.
2. **Screens: mock-ups first.** Boards for: the code step on Log in (with "Use a recovery code"); the enrol dialog (QR, manual key, confirm) and the recovery-codes sheet; the My profile card ("Two-step sign-in"); the banner inside the window; the blocked-window enrol page; the admin's "Reset two-step sign-in" on Users. Approval before slice 3 (CLAUDE.md UI workflow).
3. **Front end** (`feat/p7-w22-totp-screens`): the sign-in second step in `LoginPage.vue`, `features/profile/TwoStepCard.vue` and its dialogs, the banner, the Users action, API client types, Vitest, Playwright `e2e/totp.spec.ts` (a small RFC 6238 function in the test; the clock is real, so the code is computed at the moment it is typed). The precache stays under 30 files (check `e2e/offline.spec.ts`).
4. **Close-out.** Docs site (decisions, auth routes, settings, events, a sequence chart of the two-step sign-in and a decision chart of the enforcement rules), PRD (new requirement AUTH-14 and the D-2 line), TRD §6, AFD J2 and the profile page, BSD users fields, TP, ASVS review lines 2.2.x and 2.8.x to "met", CLAUDE.md. Release 0.8.0. Staging check: an admin enrols, signs out and in, uses a recovery code, is reset by another admin; the audit chain still verifies.

## Status (2026-11-12)

**Slice 1 (back end) is built** on `feat/p7-w22-totp-api` (stacked on this plan's branch), not committed yet. Auth 212 tests (91%), `mms_common` 149, platform 213 (the audit mapping gained a "second factor" action), Vitest 773, Ruff and mypy clean. Checked in slice 1: `session.reconnect()` signs in through the refresh cookie (`refreshSession`), never `/login`, so it cannot meet the code step.

Where the build differs from the text above:

- **A sixth event**, `auth.recovery_codes_regenerated` (a recovery sheet replaced is a security event), and an optional `mfa` (`totp` or `recovery`) on `auth.login_succeeded`.
- **The window also starts at refresh.** An admin already signed in when 0.8 ships has a 30-day session and may not sign in again for weeks, so `refresh` starts the window (and the banner) too. Enforcement is still at sign-in only.
- **`mfa_setup` rides on every `TokenResponse`** (login and refresh), so the banner survives a page reload. `Me` gains `totp_enabled` and `recovery_codes_left`.
- **The password alone never clears the failure count** when a code is still owed: only a finished sign-in does, so someone with the password cannot reset the code limit by signing in again between guesses.
- **Pending secrets live in Redis** (sealed, 10 minutes), not on the user record, until a code confirms them. The challenge has a purpose (`verify` or `enrol`) and cannot be used for the other.
- **`admin_mfa`** is a new seed user (`mms_common.testing.seed`, public test secret); `admin` stays without a factor so no other service's tests or the Playwright journeys change. `python -m app.cli seed` enrols it when `AUTH_TOTP_KEY` is set.
- **`AUTH_TOTP_KEY` is required by `compose.yml`** (`:?`) and by the service outside `local`. `.env.example` has a dev value. **Staging's `infra/.env` needs a generated key (`openssl rand -base64 32`) before this merges**, or the deploy stops at "required variable missing" without changing anything.
- Until slice 3, an admin with two-step sign-in on cannot sign in through the current screens (the app does not send `supports_mfa`, so it gets 401 `update_required`). Nobody is enrolled on staging; do not enrol anyone before 0.8.

**Slice 3 (screens) is built** on `feat/p7-w22-totp-screens` (stacked on slice 1), from the "AWS-MMS W22 screens" boards approved 2026-11-12 (answers: reset is a danger button; no print; no reason on reset; the banner on all pages). `features/auth/twoStep/` (`LoginCodeStep`, `LoginEnrolStep`, `OtpField` on Vuetify's `VOtpInput`, `TwoStepQr` with the lazy `qrCode.ts`, `RecoveryCodes`, pure `twoStep.ts`), `features/profile/{TwoStepCard,TwoStepEnrolDialog,TwoStepProofDialog}`, `features/admin/TwoStepResetDialog`, `components/MfaNotices` (the banner, in the app and field shells, and the recovery-code toast), the session store's `login` (a `challenge` result), `finishLogin`, `reloadMe`, `mfaRequiredBy`. Playwright `e2e/totp.spec.ts` (four journeys; the code is computed in the test from the secret on screen, RFC 6238); Vitest 776.

Where the build differs from the approved boards:

- **Users is a table, not a list with a detail pane**, so Reset is a row action in a new "Two-step" column (a chip and a "Reset" button, not offered on your own row).
- **No "On since" date** on the card: `Me` has no enrolment date. Adding `totp_enabled_at` is one field in auth if wanted.
- **Enrolment at login** shows a plain "Your time to set this up has ended" (the challenge carries no date), and no step bar.
- **The old-app message** ("Reload it, then log in") is mapped but can only be shown by an app that already knows `update_required`; the old app shows its generic wrong-password text. The update prompt is what moves phones to the new release.
- My profile's form is filled when the person is known, not on every profile change, so turning two-step sign-in on or off does not wipe unsaved edits.

## Questions on defaults

| # | Question | Default |
|---|---|---|
| 1 | Issuer and account name in the authenticator app | `MARS-MMS` and the email |
| 2 | Show the QR only, or the manual key too | Both (some password managers need the key) |
| 3 | Do staff who opted in get the same 5-try lock | Yes |
| 4 | Should enabling end the user's other sessions | No (resets and disabling do) |
| 5 | Recovery codes: 10, hashed, regenerate replaces all | Yes |
| 6 | Does an admin's setup window restart after a reset | Yes, a full 7 days |

## Needs from people

- The `AUTH_TOTP_KEY` on the staging host's `infra/.env` (a generated 32-byte key; keep a copy with the other secrets, because losing it makes every enrolled secret unreadable and needs every TOTP reset), and later on the production host.
- Every admin to have an authenticator app (any: the phone's built-in password manager, Authenticator apps, 1Password).
- Approval of the slice 2 boards.

## Exit

An admin in the window sees the banner and signs in; after the window is blocked until enrolled; an enrolled admin signs in with a code and with a recovery code; another admin resets them; a technician who opts in is covered; the audit chain verifies with the new events; auth, Vitest and Playwright pass; ASVS 2.2.x and 2.8.x are "met"; release 0.8.0 is on staging.
