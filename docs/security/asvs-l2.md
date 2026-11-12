# AWS-MMS against OWASP ASVS 4.0.3, level 2

Reviewed 2026-11-06 (W20 slice 5, plan decision W20-10) against the code on `main`, the running
local stack and an OWASP ZAP passive baseline. It lists the chapters that apply to a web
application and API with file uploads: V2, V3, V4, V5, V7, V8, V9, V12, V13 and V14. V1
(architecture), V6 (cryptography at rest), V10 (malicious code), V11 (business logic), V16
and V19 to V20 are covered by the TRD, the code review habit and the tests, and are not
repeated here. This is a **results** list: every line names the code or the test that answers it, or says why
it does not apply.

**This repository is public.** The file holds results, never the details of an exploitable
weakness. A finding that is open and exploitable is kept private (not in an issue, a pull request or
a chat) until it is fixed, then noted here as fixed. Everything listed as a deviation below is a
known design decision, not a hidden hole.

| Mark | Meaning |
|---|---|
| **Met** | Done, with the evidence named |
| **Met, note** | Done, with a limit worth knowing |
| **Deviation** | Not done as ASVS words it; see the numbered deviation (D-n) and its decision |
| **n/a** | The feature does not exist, so there is nothing to verify |

**Summary: 89 lines. 80 met (10 of them with a note), 4 deviations from ASVS's wording (D-1 to D-4), 5 not applicable.** One more accepted trade-off sits on a line that is met (D-5, styles in the CSP).
Fixed by this review: no `frame-ancestors`, `base-uri` or `form-action` in the CSP (14.4.x), no
Cross-Origin-Opener-Policy, `Cache-Control: no-store` missing on the platform service's API
(8.2.1), no capability drop on our containers (14.1). Added: the cross-organization run through
Nginx, `pip-audit` and `npm audit` in CI, Dependabot, a nightly ZAP baseline.

## Deviations for the product owner to decide

| # | ASVS | What ASVS asks | What we do | Why, and what would close it |
|---|---|---|---|---|
| **D-1** | 2.1.1 | Passwords of at least 12 characters | At least **12** since 2026-11-12 (`AUTH-9`, `services/auth/app/domain/passwords.py`), checked against a breached list | **Decided 2026-11-12: raised to 12; closed.** Passwords already set stay valid until they are changed |
| **D-2** | 2.2.x, 2.8.x | Multi-factor sign-in for the roles that can do most harm | None in v1; admins sign in with a password | Not in the PRD. An admin account is the one to protect. **Decided 2026-11-12: build TOTP for admins before the pilot** (decision W21-3; planned in `docs/plans/W22-plan.md`) |
| **D-3** | 3.3.2 | Re-authentication after 12 hours, or 30 minutes idle, at L2 | A refresh session slides for **30 days** (`AUTH-12`); access tokens last 15 minutes | By design: a technician works offline for days and opens the app with a device PIN. Mitigations: 15-minute access tokens, an admin disabling a user ends every session at once (Redis revocation list), five wrong PINs require an online sign-in, a restore ends all sessions (W20-9). **Accepted 2026-11-12 (30 days, same for admins)** |
| **D-4** | 9.2.2 | TLS on every connection, including between backend components | Traffic between our containers on the one host's private Docker network is not TLS; every store requires authentication (Mongo users, Kafka SASL/SCRAM, Redis password, service tokens) | Single host, no published ports except Nginx. **Accepted 2026-11-12 for one host**; add TLS between components if the stack is ever split across hosts. Backups leave the host over SFTP, encrypted before they leave |
| **D-5** | 14.4.x | A CSP without `unsafe-inline` for styles | `style-src 'self' 'unsafe-inline'` | Vuetify writes inline style attributes. Scripts are `script-src 'self'` (no inline, no eval). **Accepted 2026-11-12**; revisit with a nonce when Vuetify supports it cleanly |

## V2 Authentication

| ASVS | Result | Evidence |
|---|---|---|
| 2.1.1 length | Met (D-1 closed 2026-11-12) | `MIN_LENGTH = 12` in `domain/passwords.py` |
| 2.1.2 long passwords allowed | Met, note | Up to 256 characters; ASVS asks for 64 allowed and over 128 refused. Harmless difference |
| 2.1.3 / 2.1.4 no truncation, all characters | Met | The whole value is hashed (Argon2); no composition rules, only length and the breached list |
| 2.1.5 / 2.1.6 users change their password with the current one | Met | `PATCH /api/v1/auth/me` takes `current_password` and `new_password` (`MePatch`) |
| 2.1.7 breached passwords refused | Met, note | `repo/breached.py`: the HIBP range API (k-anonymity), a local file when it is unreachable; **fails open** with a metric when neither answers, so a break in the check never locks anyone out (W3) |
| 2.1.9 no composition rules | Met | Length and list only |
| 2.2.1 anti-automation | Met | Five failures lock an email for 15 minutes (`repo/throttle.py`, `test_five_failures_lock_the_email_for_15_minutes`); Nginx `limit_req` zone `auth` 10 a minute on login, register and reset |
| 2.2.x multi-factor | **Deviation D-2** | None |
| 2.3.1 initial secrets random and expiring | Met | Invitation and reset links are random single-use tokens, 7 days and 1 hour (`test_reset_link_expires_after_an_hour`), minted when the email is sent and never put in an event (W3) |
| 2.4.1 / 2.4.2 / 2.4.4 password storage | Met | Argon2id, time 3, 64 MiB, parallelism 4, per-password salt (`config.py`) |
| 2.5.1 recovery secret not sent in clear | Met | Links, not passwords; the email carries a link to set one |
| 2.5.2 no password hints or secret questions | Met | None exist |
| 2.5.3 recovery does not reveal the current password | Met | |
| 2.5.4 no default accounts | Met | `create-admin` makes the first admin from a prompt or an environment variable; `seed` refuses production |
| 2.5.6 recovery cannot be used to find accounts | Met | `test_reset_request_always_answers_202`, `test_registering_an_existing_email_looks_the_same_and_changes_nothing`, `test_wrong_password_and_unknown_email_look_the_same` |
| 2.6 / 2.7 / 2.8 lookup secrets, out-of-band, one-time codes | n/a | None used |
| 2.10.1 / 2.10.2 service authentication | Met | Service tokens (short-lived, audience-checked, EdDSA) from `/internal/token`; secrets per service in the host's `.env`, never in the repo; Kafka, Mongo and Redis each need a login of their own |

## V3 Session management

| ASVS | Result | Evidence |
|---|---|---|
| 3.1.1 no session token in URLs | Met | The access token is an `Authorization` header; the refresh token is a cookie |
| 3.2.1 a new session at sign-in | Met | Each login starts a refresh family (`repo/sessions.py`) |
| 3.2.3 tokens kept out of storage the page can read | Met | The access token is in memory (Pinia); the refresh token is an httpOnly cookie; `localStorage` holds only the brand colours, motion and a few UI flags (checked: `grep localStorage frontend/src`) |
| 3.3.1 logout invalidates the session | Met | `test_logout_revokes_the_session_and_is_audited`; a stale cookie still ends the family |
| 3.3.2 periodic re-authentication | **Deviation D-3** | 30-day sliding refresh |
| 3.3.4 users see and end their sessions | Met, note | Logging out ends the session on that device; an admin can disable a user, which ends every session at once (`AUTH-11`). There is no per-device session list in v1 |
| 3.4.1 cookies Secure | Met | `__Secure-mms_refresh` outside local development |
| 3.4.2 cookies HttpOnly | Met | `api/context.py` |
| 3.4.3 SameSite | Met | `Strict`, and the cookie path is `/api/v1/auth` so it is sent to no other route |
| 3.4.5 cookie path restricted | Met | `COOKIE_PATH = "/api/v1/auth"` |
| 3.5.2 / 3.5.3 stateless tokens | Met | EdDSA, 15 minutes, audience and issuer checked; `alg: none` and HS256 with the public key refused (`libs/mms_common/tests/test_auth.py`); every token issued before a revocation time is refused (Redis list) |
| 3.7.1 re-authenticate for sensitive actions | Met, note | Changing a password needs the current one. Approving users and similar actions rely on the live access token, not a fresh password |
| Refresh reuse | Met | A reused refresh token after the 30-second grace revokes the family (`test_reuse_after_the_grace_window_revokes_the_whole_family`); two tabs refreshing together stay signed in |

## V4 Access control

| ASVS | Result | Evidence |
|---|---|---|
| 4.1.1 enforced on a trusted service layer | Met | Every service checks the token itself (`mms_common.auth`); Nginx does not verify tokens |
| 4.1.2 / 4.1.3 least privilege, deny by default | Met | `require_roles(...)` on every route; a viewer never mutates (rule 5) |
| 4.1.5 fail securely | Met | An unknown role fails at import (`test_unknown_role_name_fails_at_import`); an unreachable revocation list refuses |
| 4.2.1 no direct object reference across users | Met | Org scope lives in the repository layer; out of scope answers 404 exactly like a missing record (ADR-16). **Proved from outside by `infra/tests/test_org_isolation.py`**: 25 checks through Nginx as a client of organization A against organization B's station, request, comments, sensor unit, QR token, and the lists |
| 4.2.2 CSRF | Met | The API reads a bearer header, not a cookie; the one cookie is `SameSite=Strict` and read only by `/auth/refresh` and `/auth/logout` |
| 4.3.1 administrative interfaces protected | Met, note | Admin routes need the `admin` role (matrix tests, every service). No second factor: D-2 |
| 4.3.2 no directory browsing, no leftover files | Met | Nginx serves the SPA build and `/tiles/` only; `/.releases/`, `/internal/`, `/.well-known/`, `/metrics` answer 404 (`test_the_gateway_does_not_publish_metrics_or_internal_routes`) |
| Authorization matrix | Met | `tests/api/test_authorization_matrix.py` in every service lists each route against each role and fails when a route is missing |

## V5 Validation, sanitization and encoding

| ASVS | Result | Evidence |
|---|---|---|
| 5.1.1 / 5.1.3 / 5.1.4 inputs validated, allow-lists | Met | Pydantic models on every body, query and path; enums for categories and statuses (a bad `category` is 422) |
| 5.1.5 redirects | n/a | No server-side redirects to user-supplied URLs |
| 5.2.1 / 5.3.3 untrusted HTML and output encoding | Met | Vue escapes output; `v-html` is not used anywhere (`grep v-html frontend/src` is empty); the report PDFs are Jinja templates with autoescape (`select_autoescape`) |
| 5.2.x unsafe evaluation | Met | No `eval`, `pickle.load` or `yaml.load` in service code (grep); pdf.js is configured with `isEvalSupported: false` (F17) |
| 5.3.4 / 5.3.5 query injection | Met | Mongo filters are built from typed values only (rule 12); `test_operators_in_fields_are_rejected`, `test_search_text_is_never_an_operator` |
| 5.2 / 5.3 CSV and formula injection | Met | `mms_common.safecsv` defuses cells that start with `=`, `+`, `-`, `@`, tab or CR (`test_safecsv.py`); used by the audit export and summary CSVs |
| 5.3.8 OS command injection | Met, note | Two places run a program: ffmpeg (media) and Chromium (report charts), both with `create_subprocess_exec` and an argument list, never a shell, and never with user text in an argument |
| 5.5 deserialization | Met | JSON only |

## V7 Error handling and logging

| ASVS | Result | Evidence |
|---|---|---|
| 7.1.1 / 7.1.2 no credentials or tokens in logs | Met, note | Passwords, tokens and email bodies are never passed to the logger (reviewed in auth, platform and `mms_common`); **no test greps a run's output for them yet**: a gap worth a test in the hypercare phase |
| 7.1.3 security events logged | Met | Sign-ins (with IP and device), refusals, role changes, revocations, restores: all in the hash-chained audit log (`test_login_is_audited_with_ip_and_device`, `auth.sessions_revoked`) |
| 7.2.1 / 7.2.2 log content | Met | JSON with service, request id, correlation id (structlog) |
| 7.3.1 log injection | Met | JSON rendering escapes newlines and quotes |
| 7.3.3 / 7.3.4 log integrity and time | Met | Audit records are insert-only, SHA-256 hash-chained, checked nightly and on demand (rule 10); times are UTC |
| 7.4.1 / 7.4.2 generic errors, no stack traces | Met | Every error is `application/problem+json` with a code (`mms_common.errors`); `/docs` and `/openapi.json` are off in production (`test_openapi_is_disabled_in_production`) |

## V8 Data protection

| ASVS | Result | Evidence |
|---|---|---|
| 8.1.1 / 8.2.1 no caching of sensitive data | Met (fixed here) | `Cache-Control: no-store` on every `/api/` and `/internal/` response in all five services. **The platform service lacked it** (notifications, preferences, the audit log); added with a test (`test_api_responses_are_never_cacheable`). The service worker never caches an API response (TRD 13.3) |
| 8.1.2 / 8.2.2 client-side storage | Met | Offline data is in IndexedDB, keyed by user, removed at logout; queued work is kept for the same user only (OFF-8); the PIN is a PBKDF2 verifier |
| 8.3.1 sensitive data not in URLs | Met, note | Ids in paths only. A printed station label carries a revocable QR token in its URL by design (`/s/:token`; regenerating it gives the old one 410) |
| 8.3.4 sensitive data classified | Met | BSD lists each field's location and access; clients never receive staff email or phone (D4) |
| 8.3.x data minimization | Met | Events carry ids and facts, never free text from comments or notes |

## V9 Communications

| ASVS | Result | Evidence |
|---|---|---|
| 9.1.1 / 9.1.2 TLS on the public edge | Met | TLS 1.2 and 1.3 only (`snippets/tls.conf`), session tickets off, HTTP redirects to HTTPS; HSTS one year on the app and files hosts |
| 9.1.3 only strong protocols | Met | |
| 9.2.1 trusted certificates | Met | A real certificate on staging and production; the local one is self-signed |
| 9.2.2 TLS everywhere | **Deviation D-4** | |
| Kafka, Mongo, Redis, SeaweedFS | Met | Each requires authentication (SASL/SCRAM, users per database, password, S3 keys); `infra/tests` checks anonymous access is refused and one service cannot read another's topic or database |

## V12 Files and resources

| ASVS | Result | Evidence |
|---|---|---|
| 12.1.1 size limits | Met | Documents 50 MB and video 200 MB (MED-6); 8 MiB multipart parts; Nginx `client_max_body_size` 10 MB on the API and 16 MB on the files host |
| 12.1.2 / 12.1.3 compressed-file bombs, quotas | Met, note | Archives are not accepted as documents; ClamAV caps are set (`StreamMaxLength`, `MaxScanSize`). There is no per-user storage quota |
| 12.2.1 file type checked | Met | Declared type, extension and **magic bytes** must agree (`services/media/app/domain/media.py`); SHA-256 recorded |
| 12.3.x path traversal and inclusion | Met | The client never chooses a storage key; keys are generated from ids |
| 12.4.1 files stored outside the web root, served from another origin | Met | SeaweedFS behind presigned URLs on the separate `files.` host |
| 12.4.2 antivirus | Met | ClamAV scans every upload in `media-worker`; `MEDIA_SCAN_MODE=off` is refused in production (staging runs `off`, decision T8) |
| 12.5.1 / 12.5.2 downloads not executed | Met, note | Served from the separate `files.` host with a `Content-Type` fixed by the extension table, not by what the upload claimed. **PDFs and plain images open in the browser; every other type is an attachment** (`disposition()` in `domain/media.py`). The app's scripts do not run on the files host |
| 12.6.1 SSRF | n/a | The services fetch no user-supplied URLs; the only outbound calls are to fixed hosts (the breached-password range API, the mail relay) |
| Fail closed | Met | Files start staff-only and become client-visible only through `media.visibility_requested` (rule 6, ADR-19) |

## V13 API and web service

| ASVS | Result | Evidence |
|---|---|---|
| 13.1.1 / 13.1.3 consistent validation, no secrets in URLs | Met | |
| 13.1.4 authorization at every layer | Met | Gateway routes by prefix only; each service re-checks the token and the role |
| 13.2.1 methods allowed per route | Met | FastAPI answers 405; literal routes are declared before `/{id}` |
| 13.2.3 CSRF on RESTful routes | Met | See 4.2.2 |
| 13.2.5 content type checked | Met | JSON bodies only; anything else fails validation (422) |
| 13.1.5 rate limits | Met | `limit_req`: 300 a minute per user on the API, 10 a minute per address on login, register and reset |
| 13.3 / 13.4 SOAP and GraphQL | n/a | None |
| Integrations | n/a | Not in v1; Nginx returns 501 on `/api/v1/integrations/` |

## V14 Configuration

| ASVS | Result | Evidence |
|---|---|---|
| 14.1.x build and deploy | Met | Images are built in CI, scanned with Trivy (HIGH and CRITICAL fail), tagged with the commit and pushed by the pipeline; production deploys by hand after approval (W20-12). **Added here:** our seven containers drop every Linux capability and cannot gain any (`cap_drop: [ALL]`, `no-new-privileges`), tested for production in `test_production_config.py`; they run as a non-root user |
| 14.2.1 / 14.2.2 / 14.2.3 components current and known-vulnerable ones refused | Met (added here) | `pip-audit` on the runtime dependencies of the library and each service, and `npm audit --omit=dev` at high, on every pull request and nightly (`.github/workflows/security.yml`); Dependabot weekly (`.github/dependabot.yml`); Dependabot alerts on. An accepted vulnerability needs a line with its reason in `.github/pip-audit-ignore.txt` |
| 14.2.4 / 14.2.5 dependencies from trusted sources | Met | PyPI and npm with lockfiles for the frontend; base images pinned by version |
| 14.3.1 / 14.3.2 no debug, no stack traces | Met | `/docs` off in production; `server_tokens off`; problem+json errors |
| 14.3.3 no version or technology disclosure | Met | |
| 14.4.4 content type sniffing | Met | `X-Content-Type-Options: nosniff` on every response (`test_security_headers_on_every_kind_of_response`) |
| 14.4.3 CSP | Met (fixed here), **D-5** | `script-src 'self'; worker-src 'self'` and now also `frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'` (the last four do not fall back to `default-src`; ZAP 10055) |
| 14.4.5 / 14.4.6 / 14.4.7 headers | Met | HSTS, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (camera and microphone for self only); `X-Frame-Options: DENY`; **added** `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-origin`. `Cross-Origin-Embedder-Policy` is left out on purpose: the files host's photos and video would each need their own CORP header, for a protection (`SharedArrayBuffer`) the app does not use |
| 14.5.x request headers | Met | A catch-all `default_server` closes the connection (444) for any other Host name over TLS and redirects plain HTTP to HTTPS (301); `X-Request-ID` is kept only if it is well formed (`test_request_id_is_kept_or_generated`) |
| 14.5.3 CORS | Met | No CORS headers at all: the app and API share one origin; the files host takes plain `GET` and presigned `PUT` |

## What the ZAP passive baseline found (local stack, 2026-11-06)

0 failures; 6 warnings at the first run, 62 checks passing. **Fixed:** the three CSP directives with no
fallback, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`. **Accepted, with reasons in
`.zap/rules.tsv`:** `style-src 'unsafe-inline'` (D-5), `Cross-Origin-Embedder-Policy` (above), a 13-digit
number in a vendor bundle read as a timestamp, and three information-level notes about static asset caching and
the single-page shape. The same baseline runs every night against staging (`security.yml`) and
fails only on a high-risk alert; its logs show counts only because this repository is public. For details,
run `infra/scripts/zap-baseline.sh <url>` yourself.

## Not covered here

An active scan and an external penetration test are not part of v1 (TP, V3). The staging server is shared with other
sites, so only the passive baseline runs against it. Items marked "Met, note" are the ones to look at first in a
later review. Real-device behaviour (iPhone and Android) is covered by the W13 to W15 checks, not by this list.
