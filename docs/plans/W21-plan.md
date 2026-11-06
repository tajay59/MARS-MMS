# W21 plan: close out Phase 7 (buffer week 1)

Date: 2026-11-06. W21 is the first of two buffer weeks (IP.md, "Buffer W21–W22"). Chosen scope (product owner): **close out W20 and Phase 7.** No new features.

## Goal

Release 0.7.0 is on staging and checked by people, the dependency updates are dealt with, and the five security deviations have an answer, so Phase 8 can start on W23 (or earlier) with nothing from Phase 7 hanging.

## PWA pre-flight

| Question | Answer |
|---|---|
| Device | Release 0.7.0 shows the update prompt to installed phones. The F19 fix (reload on `controllerchange`) is in this release, so "Reload now" must work when the release is found while the app is open. Check it on the Android phone. iPhone check stays postponed (see `iphone-checks-deferred`). |
| Network, lifecycle, data | No change to sync contracts, op payloads (version 1) or the Dexie schema. A phone with queued ops on 0.6 syncs them on 0.7. |
| Caching, CSP | No change. D-5 (`style-src 'unsafe-inline'`) is a decision, not a change. Dependency bumps to Vuetify, Workbox or Dexie (PR #125) change the service worker or the precache: the offline e2e (fewer than 30 precached files) must pass. |
| Proof | CI, `e2e/update.spec.ts`, `e2e/offline.spec.ts`, and the staging checks below. |

## Slices

1. **Merge #151** (W20 slice 6, release 0.7.0) once its checks are green. The deploy carries 0.7.0 to staging.
2. **Staging checks for release 0.7** (people, not CI): see the list below.
3. **Dependabot triage** (PRs #122 to #150). Rule: patch and minor bumps with green CI go in small batches (one service, or the frontend, at a time); a major version, or any red check, is looked at alone. Add grouping to `.github/dependabot.yml` so the same bump does not open one PR per service.
4. **Security decisions D-1 to D-5** for the product owner (table below).
5. **Docs:** docs site status, changelog and decisions W21-1 onward; IP.md "W21 as built"; CLAUDE.md state.

## Status (2026-11-06)

- **Slice 1 done:** #151 merged; release 0.7.0 deployed to staging, `@smoke` 3 of 3 passed.
- **Slice 3 under way:** #123 (Actions) merged. The 21 Python version-floor PRs (#130 to #150) are applied as one change in #152. #127 (`npm-run-all2` 9, needs Node `^22.22.2 || ^24.15 || >=26`; this PC has 24.6.0, so run `npm install` with a newer Node or expect an engine warning) waits for its branch update and CI.
- **Held, each needs its own look:**
  - #128 TypeScript 7: `openapi-typescript@7.13.0` does not accept it (ERESOLVE). Close and revisit when it does.
  - #126 ESLint 10, #129 `@types/node` 26, #125 frontend group: a check is failing on each; some of these are the Mongo start flake (rerun), not the code.
  - #122 and #124 (`infra` images): move **Mongo 8.0.34 to 8.3.13** on staging, whose database holds the real stations, plus Prometheus 3.5 to 3.15, Grafana 12.0 to 12.4, SeaweedFS 4.48 to 4.50 and others. A server upgrade needs a plan (feature compatibility version, a backup first, and the rollback guard refuses going back). Do not merge as a batch; split Mongo from the monitoring images.
- **Mongo start flake:** `mongo did not start in 90 s` still hits some runners despite `GLIBC_TUNABLES`. Look at the runner kernel range before W22.

## Staging checks for release 0.7

- An admin and a Viewer run each summary report type (PDF and CSV) for real stations and compare the dashboards with what they know (IP, staging release 0.7).
- The audit viewer: `verify` passes; export a CSV.
- The update prompt between 0.6 and 0.7 in the installed Android app: the prompt appears, Reload now reloads, no queued op is lost.
- A restore into staging from a real backup, then the audit chain check (exit criterion; needs a backup host: open).
- One alert fired for real and delivered (needs recipients: open).

## Decisions for the product owner (security deviations)

| # | Question | Recommendation | Cost to close |
|---|---|---|---|
| D-1 | Minimum password length 10 or 12? | Raise to 12 | One constant and the PRD line (AUTH-9); existing passwords stay valid. |
| D-2 | Second factor for admins? | Accept for the pilot; TOTP for admins in a later release | A feature (enrolment, recovery); not before the pilot. |
| D-3 | 30-day sliding sessions? | Accept (technicians work offline for days; PIN unlock, 15-minute access tokens, instant revocation) | None. Optionally shorten for admins. |
| D-4 | No TLS between containers on the one host? | Accept for one host | Revisit if the stack is split across hosts. |
| D-5 | `style-src 'unsafe-inline'`? | Accept (Vuetify writes inline styles) | Revisit when Vuetify supports nonces cleanly. |

## Still waiting on people or hosts (not built by W21)

A production host and a backup host, the backup key holder, alert recipients, the `production` environment with reviewers in GitHub, the first production deploy, the full load run on production, and the two pilot client organizations and two technicians named (IP: due W21).

## Exit

#151 merged and deployed; the staging checks above done or listed with an owner; every Dependabot PR merged, closed with a reason, or held with a reason; D-1 to D-5 answered or carried; docs updated.
