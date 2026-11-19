# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Existing codebase, so nothing to choose: a Vue 3.5 + TypeScript PWA built with Vite, Vuetify 4 and Tailwind CSS 4, with Pinia, Dexie (offline) and Workbox. Five FastAPI services behind an Nginx gateway on the organization's own servers. Installed on phones and desktops from the browser; there is no native app.

## Users

AWS-MMS (shown to people as MARS-MMS) is used by two sides.

**Staff** of the organization that maintains weather stations for other organizations:
- **Technicians** record whole site visits on iPhones and Android phones, often with no signal, in sun, glare and rain, sometimes for days before they sync. **When design decisions conflict, the field technician wins.**
- **Admins** (the office) approve registrations and requests, assign and plan visits, manage users, stations, sensors and documents, finalize reports and read the audit log, mostly on a desktop.
- **Viewers** read everything and change nothing.

**Clients** are people at external organizations in several countries who own the stations. They request work, follow its progress, read reports and documents, and sign the work off. They see only their own organization's stations, and they never see staff contact details, internal comments or draft reports.

## Product Purpose

A self-hosted system for maintaining automatic weather stations the organization runs for client organizations. Clients ask for work and sign it off; staff plan, record and report site visits. It replaces ad hoc records with one trail from request to signed report.

Success: a technician records a full visit offline and it syncs with **zero lost or duplicated records or files**; a client can see what was done to their station and accept or reject it; every change is attributable and the audit trail verifies.

## Positioning

What a neighbouring product could not truthfully copy:
- Offline-first visit recording for field staff on iOS and Android, with every offline write replayed exactly once and local copies deleted only after the server confirms.
- One accountable owner per station on a visit, so there is nothing to merge.
- Client sign-off on finalized, immutable report versions, with a hash-chained, insert-only audit trail.
- Self-hosted by the maintaining organization; clients are isolated from one another by organization.

## Operating Context

- Field: a technician arrives at a site with a phone, prepares the visit while online (the files and station data are stored on the phone), works with no signal, unlocks the app with a device PIN, and syncs when the signal returns. The camera, QR labels on stations, large photos and videos (up to 200 MB) and signatures are part of the job.
- Office: requests, queues, visit planning, reports as PDFs, summary reports and CSV, dashboards, and the audit log.
- Stations belong to client organizations, have an IANA time zone for display, and carry sensors with calibration due dates and configuration versions.
- Clients meet the app through an invitation email, a request form, a request page, documents and reports, and a review-and-sign page.
- Time is stored in UTC and shown in the station's zone. Dates are written like `12 Sep 2026`.

## Capabilities and Constraints

- Requests move through a fixed lifecycle (submitted, approved, assigned, in progress, client review, closed, and the denied and cancelled branches). Status after assignment is derived from visits, never set by hand.
- A visit has a board of elements per station: notes, tasks, recommendations and configuration files. Visit reports are signed and finalized, then immutable; a change means reopening as a new version.
- Offline scope is site visits and station lookup only. Approvals, request creation, signing and admin work say "This needs a connection".
- Staff sign in with a password; admins also use a second factor (TOTP, since release 0.8, W22) at sign-in only; other staff may opt in. Clients cannot use offline mode.
- Roles are client, technician, admin and viewer. Viewers see read-only views, with action buttons hidden, not disabled.
- Light and dark themes ship; brand colours come from a Material 3 theme that admins can change for everyone. Status colours are reserved for status.
- The service worker never caches API responses. The CSP is strict (`script-src 'self'`; no inline scripts, no CDN, fonts bundled).
- Hosting: the pilot runs on the staging site for now (W23-8); a production host, backup host and alert recipients are still to come (a hosting decision, not a design one).

## Brand Commitments

- The product is called MARS-MMS in emails and on the public pages; AWS-MMS is the project name.
- The logo comes from `/logo` (`npm run brand` rebuilds the files and PWA icons).
- **`docs/DBD.md` is the binding design source** (tokens, fonts, shells, components, "Voice and microcopy"), then the TRD conventions. Google Sans for titles, Roboto Flex for text, JetBrains Mono for references and file names; Material Design Icons.
- Person avatars may use a brand gradient; no other decorative gradients.
- Planning documents (`docs/PRD.md`, `docs/AFD.md`, `docs/BSD.md`) win on product behaviour and flows.

## Evidence on Hand

- The planning documents and a developer docs site (`docs/index.html`) describe the product in detail.
- A staging site exists with real station data imported from the organization's earlier system. That data, client names and internal addresses are **not in this repository** (it is public) and must never be put in a mock-up, test or example.
- Demo data is made up (organizations A and B, "Example" requests).
- There are no testimonials, case studies, customer logos or benchmarks. Do not invent any.
- Approved mock-ups exist per feature in the design canvases (for example "AWS-MMS W19 screens"); the W22 two-step sign-in screens are built.

## Product Principles

1. **Never lose or duplicate field work.** Anything that could drop, reorder or repeat an offline record is a defect, however small.
2. **Design for the technician with one hand, no signal and sun on the screen.** Big targets, plain words, honest sync state; the office adapts around that.
3. **Say what is true and what to do next.** Offline, queued, conflicted and failed states are always named, with the way forward.
4. **Clients see only their own work, and only what is meant for them.** Out of scope is "not found", and staff-only detail never leaks to a client.
5. **Every change leaves a trail.** Finalized reports are immutable and the audit chain verifies.

## Accessibility & Inclusion

- WCAG 2.2 AA, checked with axe in light and dark for every screen.
- Reduced motion is honoured and there is a setting to turn animations off.
- Users are in several countries; dates and zones are explicit, and wording stays plain for readers who may not be native English speakers.
- Usable on small phones, with safe areas on iPhones and a bottom bar below 1024 px.
