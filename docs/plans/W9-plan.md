# Phase 3 · W9 plan: assign, claim, queue, comments, notifications

Approved 2026-10-21 (mock-ups approved as drawn; answers in section 7). Slice 1 is built. Mock-ups: the "AWS-MMS W9 screens" canvas (13 boards: queue, claim sheet, assign dialog, comments in light and dark, client comments on a phone, new-request attachments, notification list in light, dark and on a phone, email preferences, two emails).

Delivers REQ-7, REQ-9, REQ-10, REQ-3 (PDFs), NOT-1 to NOT-5, CAL-5, the claim step of J5 and J4 step 4. Depends on W8 (merged), Q6 (default categories stay), T3 (Gmail interim stays).

## 1. Order of work

Four slices, each its own branch and pull request, in this order. Slice 1 and 2 are the user's "1 and 2".

| Slice | Branch | What | Size |
|---|---|---|---|
| 1 | `feat/p3-w9-assign-queue` | Back end: `POST /requests/{id}/assign`, `/claim`, `GET /queue`, `GET /requests/workload`, auth `POST /internal/users/lookup`, events `request.assigned` and `request.staff_changed`. Front end: `/queue`, Assign dialog, Claim, "Assigned to" on the request page and list. | M |
| 2 | `feat/p3-w9-comments` | Back end: comments (list, post, edit within 15 min, staff toggle internal), PDF attachments on requests and comments, owner checks, `media.visibility_requested`. Front end: Comments tab, composer, attachment chips, new-request attachments. The internal-attachment exit check. | L |
| 3 | `feat/p3-w9-notifications` | Platform: `user_directory`, recipient rules, `notifications`, REST list/read, `/ws` with Redis fan-out and `entity.updated`. Front end: socket client, store, rail badge, `/notifications`, live refresh of the request page and list, snackbar. | L |
| 4 | `feat/p3-w9-email` | Platform: email for every Appendix B event that has one so far, per-type preferences (`GET/PUT /notifications/preferences`), weekly calibration digest (internal due-list endpoint in operations, cron, `digest_runs`). Front end: Email preferences on My profile. | M |

Slices 1 and 2 touch only `operations` and the frontend, so they can merge before platform work starts. Slice 3 needs the events from 1 and 2.

## 2. Decisions to approve (proposed W9-1 to W9-12)

1. **Claim and assign share the one table row** (`Approved → Assigned`, `Action.ASSIGN`). A technician's claim takes no body and always means themselves. An admin's assign takes `staff_ids` (1 to 10). `staff_count` in `transition()` is the count after the call.
2. **Eligible staff** are active users with role `technician` or `admin`. Operations checks them with auth's new `POST /internal/users/lookup {ids}` (service token; returns `id, name, roles, status` only) and stores `{id, name}` in `assigned_staff`. Viewers can never be assigned.
3. **A claim race has one winner.** The update names `expected_status: approved` (W8-5), so the second claim gets 409 `already_assigned` with the winner's name; the page reloads and says so.
4. **Admin can change staff while the request is Assigned** (same `/assign` route, no status change, event `request.staff_changed` with added and removed). From Scheduled on, staff come from visits (Phase 4), so the route answers 409 there. **A technician can release their claim** (`POST /requests/{id}/release`, a new row in the state table: Assigned to Approved, technician or admin): they remove only themselves; when nobody is left the request goes back to the queue (event `request.released`, `assigned_at` cleared), otherwise `request.staff_changed`. An admin's release clears everyone (shown as Unassign). Answered yes on 2026-10-21.
5. **The queue is `GET /api/v1/queue`**: status Approved, `assigned_staff_ids` empty, oldest `approved_at` first, with the same filters as the list (country, priority, category, search). Staff only; a client gets 404. The nginx `queue` prefix already routes to operations.
6. **Comments are a collection in `operations`** (`comments`, TRD §5.4): flat, oldest first, author name and role stored on the row. Body 1 to 5,000 characters. Clients can post; viewers cannot. A client's comment is never internal (the server ignores the flag).
7. **Edit window:** the author edits the body within 15 minutes of posting (server clock, `edited_at` set). Staff may also toggle `internal` on any comment of theirs within the same window. Nobody deletes a comment.
8. **Attachments are PDFs only** (the media documents path already takes them; photos wait for Phase 4, W8-3). Up to 5 per request and 5 per comment, 25 MB each. They upload before the comment or request exists, with owner references `request:<id>` and `comment:<request_id>:<comment_id>` (IDs made on the device, rule 9). The Post and Submit buttons wait until every file is `ready` (the mock-ups show this). This is online-only work (OFF-10): offline the composer keeps its text and says "This needs a connection".
9. **Internal-comment files stay staff-only.** Operations emits `media.visibility_requested` in the same transaction as `comment.added`: `org` for a client-visible comment, `staff` for an internal one. A later toggle to internal emits `staff` with a higher `visibility_version`, and media applies only the newest. Operations' owner check refuses a client who names a comment that is internal or not on their request (404, rule 4).
10. **Notifications carry no comment text.** A row holds type, title, a short line built from the request (reference, title, actor's name) and a link. If a comment is later made internal or edited, nothing in a client's list has to change. (The mock-ups were corrected to match.)
11. **Never notify the actor.** A person who does the action does not get a notification or email for it. Admin-created requests, own claims and own comments make no row for their author.
12. **Email preferences list only types the person can receive by email.** Defaults are on for everything Appendix B marks "In-app + email". Account emails are locked on. In-app is always on. Comments are in-app only (Appendix B), so they have no switch.

## 3. Back end

### operations (slices 1 and 2)

New routes (all in `tests/api/test_authorization_matrix.py`):

| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/api/v1/requests/{id}/assign` | admin | `{staff_ids, version?}`; Approved → Assigned, or staff change while Assigned |
| POST | `/api/v1/requests/{id}/claim` | technician, admin | self only |
| POST | `/api/v1/requests/{id}/release` | technician, admin | a technician removes themselves, an admin everyone; nobody left means back in the queue |
| GET | `/api/v1/queue` | technician, admin, viewer | Section 2, item 5. Viewers read, never claim |
| GET | `/api/v1/requests/workload` | admin | open requests per staff id, for the Assign dialog |
| GET | `/api/v1/requests/{id}/comments` | any in scope | clients get no internal rows, and no files of them |
| POST | `/api/v1/requests/{id}/comments` | technician, admin, client | `{id, body, internal, media_ids}`; idempotent by `id` like requests (W8-4) |
| PATCH | `/api/v1/requests/{id}/comments/{cid}` | author | body, and `internal` for staff; 15 minutes |
| GET | `/internal/calibrations/due` | service | slice 4: the digest's list, the same query as `GET /calibrations/due` |
| POST | auth `/internal/users/lookup` | service | slice 1 |

`actions` on the request detail gains `assign` (admin, Approved or Assigned), `claim` (technician or admin, Approved, unassigned). `OFFERED` grows by `ASSIGN`.

Events (schemas in `mms_common.events.operations`, audit mapping updated; all extra fields are optional so version 1 stays):

- `RequestData` gains `title` and `created_by` (notification text and the client recipient).
- `request.assigned`: `staff_ids`, `staff_names`, `claimed` (true when the technician claimed), `by_id`.
- `request.staff_changed`: `added`, `removed`.
- `comment.added`: `comment_id`, `author_id`, `author_name`, `author_role`, `internal`, `attachment_count`. No body.
- `comment.updated`: `comment_id`, `internal`, `edited`.

Keys are `request_id`, as the naming rules say. Each is written inside the same transaction as the change (rule 2).

Collections and indexes (migration `NNNN_comments`): `comments {_id, request_id, org_id, author_id, author_name, author_role, body, internal, attachments:[{media_id, name, size}], created_at, edited_at, version}` with `(request_id, created_at, _id)`; `requests` gains `(status, assigned_staff_ids, approved_at)` for the queue. Org scoping and the internal filter live in `repo/requests/comments.py` (rules 3 and 6); `domain/requests/comments.py` holds the 15-minute rule and text cleaning (rule 7).

Media side: `/internal/attachable` learns `request:<id>` and `comment:<request_id>:<comment_id>`. The request may not exist yet when the owner is `request:<id>` (the same rule as W8-3), so the check only proves the person could create or see a request for that organization.

### platform (slices 3 and 4)

Notification module, layers as the rest of the service (`api → jobs → events → repo → domain`):

- **`user_directory`** from `user.*` events, backfilled from auth's snapshot at start (the same pattern as operations' organization copy). Recipient rules query it.
- **Recipient rules** (`domain/recipients.py`, no I/O): one pure function from an event and its context to a list of `(user_id, channel set)`. It implements PRD Appendix B for the events that exist now: `user.registered`, `request.submitted`, `request.approved`, `request.denied`, `request.assigned`, `request.staff_changed`, `request.cancelled`, `comment.added`, and the calibration digest. A table-driven test walks every row of the matrix and every role.
- **`notifications`** as TRD §5.5, plus `event_id` and `entity {type, id}`; unique `(user_id, event_id)` so a redelivered event writes nothing twice. TTL one year. The consumer writes the rows and `processed_events` in one transaction (TRD §8.5), then publishes to Redis `ws:user:{id}` after commit.
- **REST:** `GET /notifications?after=&unread=&type=&limit=`, `POST /notifications/{id}/read`, `POST /notifications/read-all`, `GET /notifications/unread-count`, `GET/PUT /notifications/preferences`. Everything is scoped to the caller's `user_id`; another person's id is 404.
- **WebSocket `/ws`:** first message `{type:"auth", token}` within 5 s (TRD §13.4). The server verifies with the same `Authenticator` and checks the Redis revocation list on connect and on each 25 s heartbeat; a revoked or expired token closes with code 4401. The client may send a new `auth` message to extend the session before the token ends, so a 15-minute token needs no reconnect. Each instance subscribes to `ws:user:{id}` only for its connected users.
- **`entity.updated`:** for `request.status_changed`, `request.assigned`, `comment.added`, `comment.updated`. Sent to every staff member with a socket and to the request's organization's users. For an internal comment only to staff. The message carries `entity`, `id`, `status`, and `kind` (`status` | `comment`) and no content; the page refetches.
- **Email:** the existing sender and `email_queue` grow a `kind: notification` row that holds the notification id and a template name, rendered at send time with the request's current title. The sender skips the row when the person has turned that type off at send time, not at queue time. Templates are plain HTML plus text, DBD "PDF reports and email" style (see the two email boards).
- **Weekly digest:** a cron under the Redis lock (`PLATFORM_DIGEST_CRON`, default Monday 07:00 in `PLATFORM_DIGEST_TZ`, default `America/Jamaica`) calls operations `/internal/calibrations/due` with a service token (rule 1), and writes one `digest_runs` record keyed by ISO week before queuing, so a restart or a second instance sends it once. Admins only; no digest when nothing is due.
- Platform's Kafka user already consumes `mms.operations.events`; `notification_topics` grows from auth only to auth and operations. No ACL change.

## 4. Front end

New files, following the existing layout:

- `features/requests/`: `QueuePage.vue` (table, cards on phones), `ClaimSheet.vue` (`ModalSheet`), `AssignDialog.vue`, `RequestComments.vue`, `CommentItem.vue`, `CommentComposer.vue`, `AttachmentChip.vue`. `RequestDetailView` gains the Comments tab (`?tab=comments`) with a count. `RequestForm` gains the Attachments fieldset (uploads through the existing engine `src/offline/upload.ts`, owner reference `request:<id>`).
- `src/api/notifications.ts` (generated types from `openapi/platform.json`, a new export), `src/app/realtime/socket.ts` (no Vue, the PWA rule: reconnect with backoff 1 to 30 s, on `visibilitychange` and `online`, auth by `getAccessToken()` so refresh stays under the `mms-auth-refresh` lock), `stores/notifications.ts`, `features/notifications/NotificationsPage.vue`, `NotificationRow.vue`, `features/profile/EmailPreferences.vue`.
- The rail already has a Notifications button (placeholder route). It gets the unread badge (`99+` cap), and the phone bar's Me tab gets the same dot.
- `useLiveEntity()` composable: pages register an entity; on `entity.updated` it refetches after 300 ms, never while a form is dirty or the composer has focus (it shows the "Maya Clarke commented · Show" chip instead, so the thread never jumps under a thumb).

## 5. PWA pre-flight (answers)

1. **Device.** iOS Safari kills the socket in the background and has no Background Sync. So: connect only while the page is visible; reconnect on `visibilitychange` and `online`; the first thing after a reconnect is `GET /notifications?after=<last id>` and an unread-count refresh (NOT-2). Email is the fallback when the app is closed. Web Push would be the next step and is not in the PRD; raised in section 7.
2. **Network.** Mid-upload loss is the existing engine's job (resumable parts, idempotent `POST /uploads` by `media_id`). A comment post is idempotent by its device-made `id`; a retry after a lost response returns the same comment (200). The socket reconnects with backoff and a jitter.
3. **Lifecycle.** A waiting service worker never reloads a page with an open composer or an upload in flight (the update prompt rule). Socket and composer state are in memory and survive the prompt only if the person accepts it after sending.
4. **Data and loss.** Comments, queue and notifications are online-only (OFF-10, AFD §5.2); nothing enters the outbox or Dexie. The unsent comment text is held in the composer's memory and in `sessionStorage` per request (a convenience, wrapped in try/catch, cleared on post and on logout). Nothing about a client's comments is stored on a shared device after logout.
5. **Storage.** PDFs go straight to the files host and are never stored locally. Nothing new in IndexedDB.
6. **Caching.** The service worker still caches no API response, and the socket is not a fetch. `/ws` stays out of the navigation fallback (already in the denylist). Presigned PDF links are asked for on click and not kept.
7. **Security.** Tokens only in memory; the socket authenticates with the in-memory access token and re-authenticates after refresh, so no token goes in the URL (it would reach logs). **Check:** `connect-src 'self'` covers `wss://` on current Safari; confirm on the iPhone run, and if not add an explicit `wss://` host to the CSP. Logout closes the socket and empties the notifications store before the next user signs in.
8. **Proof.** Vitest with a fake socket (backoff, auth message, visibility). Playwright: two browser contexts (admin and technician) see a claim and a comment appear without reload; the `@phone` project covers the bottom-bar badge. A real-device step joins the postponed iPhone checks: background the installed app for a minute, return, and see the missed notification arrive.

## 6. Tests and the exit checks

- Domain: assign and claim rules (staff count, role, race), comment window, text cleaning, recipient table (every Appendix B row today, every role, actor excluded).
- API with real Mongo and Redis; matrix entries for every new route; viewer 403; client on `/queue` 404; client on another organization's comment 404.
- **Exit check 1 (internal attachments).** With real media and SeaweedFS, a staff comment marked internal with a PDF: a client of the same organization (a) does not see the comment in the list, (b) gets 404 for the media's link by its ID, (c) cannot start an upload against that comment's owner reference (404), (d) receives no notification row and no `entity.updated` for it, and (e) after the comment is toggled internal later the file goes `staff` and the old link is refused. A Playwright journey repeats (a) and (b) as the client.
- **Exit check 2 (fan-out).** Claim and comment produce the matrix rows, exactly once after a Kafka redelivery; a socket receives its own user's message and nobody else's; a revoked token is dropped within one heartbeat.
- Playwright J4 end to end: client submits, admin approves and assigns, technician sees it in Work, client sees "Assigned to"; axe in light and dark on queue, comments, notifications, preferences.
- Review: `web-design-guidelines` on each new screen, `writing-guidelines` on the copy and the two emails.

## 7. Open questions for you

Answers on 2026-10-21: release a claim, yes (item 3); digest Monday 07:00 America/Jamaica, yes (item 4); Web Push, not yet (item 5); all 13 boards approved (item 6). T3 and Q6 stay on their defaults.

1. **T3.** Is the SMTP relay live? The plan keeps the Gmail interim on staging (about 500 emails a day, sender is a gmail.com address). Slice 4 needs no change when the real relay arrives, only the settings.
2. **Q6.** Categories and priorities stay as the PRD lists them unless you say otherwise.
3. **Release a claim?** Technicians who claim by mistake have no way back in this plan; an admin can reassign. Add "Release" (Assigned back to Approved, one more row in the state table) now, or leave it?
4. **Digest time.** Monday 07:00 in `America/Jamaica`. Right for the first organization?
5. **Web Push** for the installed app (iOS 16.4+ and Android) would deliver notifications while the app is closed. It is not in the PRD; it needs VAPID keys and a subscription store. Worth a later phase?
6. **Mock-up approval.** Anything to change on the 13 boards before slice 1 starts? In particular the Assign dialog (workload counts), the amber composer for internal comments, and the badge on the rail.

## 8. Developer docs site (updated at the end of each slice)

Decisions W9-1 to W9-12, routes, events, collections, config (`PLATFORM_DIGEST_CRON`, `PLATFORM_DIGEST_TZ`, `PLATFORM_WS_HEARTBEAT_S`), changelog, status badges. Charts for Phase 3, beyond the three already added in W8 (request status, `derive_status` tree, "who moves a request forward" swimlane):

1. Sequence: a comment travels to a client's open page (outbox, Kafka, recipients, Redis, socket, refetch).
2. Decision tree: who receives a notification (recipient rules, actor excluded, internal filter).
3. Decision tree: can a client see this comment's file (the exit check as a diagram).
4. State: the socket connection (connecting, authenticated, reconnecting, suspended, closed).
5. Event storming: request and comment events, consumers and read models.
6. Code flowchart: `claim` and `assign` branch by branch (race, role, status).
