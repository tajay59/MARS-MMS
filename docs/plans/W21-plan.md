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
  - #122 and #154 (`infra` images): propose **Mongo 8.0.34 to 8.3.13** plus Prometheus 3.5 to 3.15, Grafana 12.0 to 12.4, SeaweedFS 4.48 to 4.50 and others. Superseded for Mongo by the decision to go to MongoDB 9 (section below); #154's other images are looked at on their own after that merges.
  - **Update 2026-11-11:** the Trivy fix (zlib1g, #168) is merged; #169 groups Dependabot by dependency; #156 to #167 (floor bumps only) were closed; #128 closed (TypeScript 7).
- **Mongo start flake:** `mongo did not start in 90 s` still hits some runners despite `GLIBC_TUNABLES`. Look at the runner kernel range before W22.

## MongoDB 9 (decided 2026-11-11, decisions W21-1 and W21-2)

The product owner chose MongoDB 9, not the 8.3 that Dependabot proposed (#122, #154). `mongo:9.0.8` is pinned in the stack, the dev stack, the backup image and the test fixture; `pymongo>=4.18` (first fully compatible release). 8.0 to 9.0 is a direct upgrade and needs FCV 8.0. Local proof: `mms_common` 149 tests on a real 9.0.8 container, platform and auth suites, then CI on the PR.

**Staging runbook (by hand; the PR's merge restarts `mongo` on the new image, which is step 1):**

1. **Deploy** (merge). Compose recreates `mongo` on 9.0.8 with the existing volume. mongod 9 opens FCV 8.0 data. The way back is open: a rollback to the previous SHA needs `--allow-older-schema` in the guard (decision W21-2), and runs 8.0.34 on the unchanged data.
2. **Check, before anything else:** every service healthy; `mongosh ... --eval 'db.adminCommand({getParameter:1, featureCompatibilityVersion:1})'` still says `8.0`; the station list loads; `verify-audit` on the chain is clean; Grafana's Mongo panels fill (the `percona/mongodb_exporter:0.44.0` image against a 9.0 server is the one thing not tested in CI); look for `ExceededMemoryLimit` in the service logs (9.0 limits one operation to 1 GB or 20% of memory).
3. **Soak** a few days with real use. Rolling back is still safe in this window.
4. **Back up for real** with the new backup image (`backup.sh mongo`), copy it off the host, and run the restore into staging as the drill (this also closes the open W20 exit check).
5. **Raise FCV** only then: `db.adminCommand({setFeatureCompatibilityVersion: "9.0", confirm: true})` on the primary. **From here a rollback means a restore from the backup in step 4.** Never put this in `infra/mongo/init.js`: it runs on every `up` and would close the door by itself.
6. When 9.0.8 has been stable for the soak: close #122 and #154 as superseded (Dependabot recreates #154 for the monitoring images without the Mongo lines), and, if a run on a CI kernel that failed before passes without `GLIBC_TUNABLES`, drop that variable.

Not covered here: production. The same steps apply when the host exists; do them on staging first.

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
