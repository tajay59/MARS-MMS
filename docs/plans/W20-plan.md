# Phase 7 · W20 plan: production stack with monitoring and alerts, backups and a restore test, the security review, the load test

Proposed 2026-10-29, with W19 on `main` (slices 1 to 5 and the charts, #108 to #115). Questions are in section 9; every one has a default, and the slices below are written on the defaults. Nothing in W20 has a screen, so no boards are needed.

Delivers the second half of IP Phase 7: the production stack (`compose.prod.yml` with Prometheus, Grafana, Loki, Alloy and the exporters, and the alerts of TRD §16.5), backups (nightly `mongodump`, continuous `weed filer.sync` with a nightly `rclone check`) and the first restore test, the TRD §15 / ASVS L2 security review with Trivy, dependency audits, an org-scoping run as a client of another organization and a nightly OWASP ZAP baseline, and the Locust load test (50 users, 20 simultaneous video uploads, a 1-hour soak). It checks NFR-2 (p95 under 1 s), NFR-3 (alerts on downtime) and NFR-9 (backup and recovery), and closes staging release 0.7 with W19.

**Not in W20:** the production data import, training and pilot (Phase 8, W23 to W25); a 3-node Mongo or Kafka (T5: single node plus backups); an external penetration test (TP V3: not in v1); integrations (later release). W20 does not change any screen, the sync contract or the service worker.

## 1. Where things stand (checked 2026-10-29)

- **Metrics:** every service has `GET /metrics` (`mms_common.web`), but it serves only the Python process metrics plus two custom ones: `audit_chain_ok` (platform, W19) and the breached-password counter (auth). **There is no `prometheus-fastapi-instrumentator` and no request, outbox, consumer, queue, sync or render metric**, although TRD §16.5 names all of them. `/metrics` is not published by Nginx.
- **Infra:** `compose.yml` (twelve services plus the init one-shots), `compose.dev.yml`, `compose.prod.yml` (images from GHCR by SHA, nothing published but Nginx) and `compose.staging.yml` (the shared host `rnd.yanacreations.com`: memory caps, behind its edge Nginx). **There is no Prometheus, Grafana, Loki, Alloy, exporter, Alertmanager, backup container or script, and no `infra/prometheus|grafana|loki|alloy` folder.** No production host exists in the repository's records (IP Phase 0 lists it as B1, "disk encryption on both hosts"); staging is a shared server with about 2 GB of free memory (decision W4-8).
- **CI:** `backend.yml` (including the `compose stack` job and `report-visual`), `frontend.yml`, `images.yml` (Trivy on every image, HIGH and CRITICAL, with `.trivyignore`), `release.yml` (staging deploy and `@smoke`). **There is no `pip-audit`, `npm audit`, ZAP, nightly, weekly-restore or load-test workflow, and no `dependabot.yml`** (Dependabot alerts are on in the repository; version updates are not configured). No production deploy workflow.
- **Auth:** access tokens are revoked through a Redis list (`revoke_user`, `revoke_org`) and refresh sessions in Mongo (`sessions.revoke_users`); **there is no operator command that revokes every session at once** (`app.cli` has `create-admin`, `seed`, `import-orgs`).
- **Audit:** the chain, `verify()` (admin API `POST /api/v1/audit/verify` since W19) and the nightly check with the gauge `audit_chain_ok` exist. This is what a restore is judged by.
- **Mongo:** one root user and one user per service database (`infra/mongo/init.js`); no backup user. SeaweedFS runs one process (`weed server -s3`) with `-volume.max=0` and 256 MB volumes.

## 2. Order of work

Six slices, each its own branch and pull request, built in this order because each uses the one before. Slices 1 to 3 are the heart of the week; 4 to 6 are mostly checks and may find work.

| Slice | Branch | What | Size |
|---|---|---|---|
| 1 | `feat/p7-w20-metrics` | `mms_common.metrics`: request middleware, outbox, lease, consumer, DLQ, jobs, sync, render, finalizing and age metrics in the five services; `/metrics` refused at the gateway | M |
| 2 | `feat/p7-w20-monitoring` | `infra/monitoring/`: Prometheus, Alertmanager, Grafana, Loki, Alloy, the exporters, the rules for every TRD §16.5 alert with `promtool` tests, dashboards, an alert drill into Mailpit | L |
| 3 | `feat/p7-w20-backups` | `backup` container and scripts, `weed filer.sync`, `rclone check`, retention, `restore.sh`, `revoke-all-sessions`, the restore drill (CI weekly and on staging), runbook | L |
| 4 | `feat/p7-w20-production` | The production stack: sizing, `compose.prod.yml` completed, the manual-approval deploy workflow and rollback, the production config checks, host preparation | M |
| 5 | `feat/p7-w20-security` | The ASVS L2 review, `pip-audit` and `npm audit` in CI, Dependabot, the nightly ZAP baseline, the cross-organization run through Nginx, fixes it finds | M |
| 6 | `feat/p7-w20-load` | Locust (load, uploads, soak), the 5x seed volume, thresholds, the numbers written down; release 0.7 close-out (version, docs, charts) | M |

Slices 1 to 3 touch `mms_common`, so each runs the whole backend suite. Slices 2 and 3 add containers to the stack job in `backend.yml`; the stack job already takes about 30 of its 35 minutes, so the monitoring and backup checks run in their own jobs (`monitoring`, `backup`) and not inside `infra/tests`.

## 3. Decisions (proposed W20-1 to W20-12)

1. **Metrics names are stable, labels are never identifiers.** One module, `mms_common.metrics`, defines every metric and each service calls `instrument(app, service)`. HTTP metrics label by method, **route template** (`/api/v1/requests/{id}`, never the real path) and status class; nothing carries a user, organization, station, request, token or email. The names follow TRD §16.5: `http_requests_total`, `http_request_duration_seconds`, `outbox_oldest_unpublished_seconds`, `outbox_leader` (1 on the leader), `outbox_leader_changes_total`, `consumer_lag_seconds{group}`, `dlq_messages_total{group}`, `job_duration_seconds{job}`, `job_failures_total{job}`, `sync_ops_total{result,reason}`, `report_render_seconds{kind}`, `reports_finalizing_oldest_seconds`, `clamav_signature_age_seconds`, `audit_chain_ok` (exists), `backup_last_success_timestamp_seconds{kind}`. A test asserts no label value comes from a request path parameter.
2. **Alerts are Prometheus rules, sent by Alertmanager, tested with `promtool`.** The ten alerts of TRD §16.5 are rule files in `infra/monitoring/rules/`, each with a `promtool test rules` case (fires, does not fire, the `for:` window), run in CI. Alertmanager sends email through the platform's SMTP settings (T3; the interim Gmail on staging) to `MMS_ALERT_EMAILS`. Grafana is for looking at things, not for alerting, so an alert does not depend on a login-protected UI and its rules live in code. This adds **Alertmanager** and **node-exporter** (disk usage) to TRD §16.1's list. [Question 2.]
3. **Monitoring is reachable only from the host.** Prometheus, Alertmanager, Loki and Grafana publish nothing; Grafana is on `127.0.0.1:3001` for an SSH tunnel or the VPN (TRD §15). Prometheus scrapes the services on the `backend` network; Nginx exposes `stub_status` on a second, internal-only server block for the exporter, never on 80 or 443. Scrape and exporter credentials are their own users: a Mongo `clusterMonitor` user, a Kafka SCRAM user with Describe on groups and topics only (a line in `infra/kafka/users.yml`, W4-16), a Redis password the exporter reads. No exporter uses the root account.
4. **Logs: Alloy ships container logs to Loki with four labels** (`service`, `level`, `environment`, `container`); `request_id` stays a field in the JSON line, not a label. Loki keeps 30 days. Logs already carry no tokens or message bodies (W3); a test greps a run's output for a sample token, password and email body.
5. **Staging runs a small part of it, and only after its free memory is measured.** The shared host has about 2 GB free and other sites; it gets Prometheus, Alertmanager and the exporters with memory caps (about 350 MB in all) so every alert can be fired once on a real host with a real SMTP relay (IP exit). Grafana, Loki and Alloy do not run there. Nothing is installed on that host before the free memory is read and you agree (CLAUDE.md: changes there affect other sites). The full stack is run and tested locally and in CI. [Question 1, 4.]
6. **Backups: one container, encrypted before they leave the host.** A `backup` service (Mongo tools, `rclone`, `age`) runs a cron: `mongodump --oplog --archive --gzip` of the whole instance (`--oplog` is only valid for all databases, which is what TRD §16.4 asks for), encrypts with `age` to a public key kept on the host, and copies the file to the backup host over SFTP with `rclone`. The private key is not on any server the stack runs on (held by organization IT; [Question 5]). A dedicated Mongo user with the `backup` role does the dump. Retention is 14 daily and 12 monthly, applied by the same job on the backup host. `config-secrets` (the `.env`, the signing key, the Kafka and SeaweedFS credentials) is archived and encrypted when its checksum changes, the last 10 kept. The job writes `backup_last_success_timestamp_seconds` through node-exporter's textfile folder; the alert "backup job failed or missing" fires when it is older than 26 hours.
7. **Objects: `weed filer.sync` to a second SeaweedFS and a nightly `rclone check`.** A `filer-sync` container follows the primary filer into the backup host's SeaweedFS continuously (RPO for files is minutes); a nightly `rclone check --one-way` over the four buckets writes `backup_last_success_timestamp_seconds{kind="objects"}` or a failure metric. Buckets with objects older than 30 days are checked by size and hash. Kafka is not backed up (TRD §16.4).
8. **A restore is a runbook, and a script runs it.** `infra/scripts/restore.sh` does, in this order: stop the services and the relays, `mongorestore --oplogReplay --drop`, start Mongo-dependent services with the outbox relay still stopped, **reset every consumer group to the earliest offset** (`processed_events` makes the replay safe; the audit group replays what the dump lacks, see the replay note in `CLAUDE.md`), run `report`'s backfill, **revoke all sessions** (decision 9), start the relays, then `POST /api/v1/audit/verify` and compare the chain's head and count with the backup's manifest. The script is run weekly in CI against a stack seeded with a made-up chain and by hand against staging; both write `restore_drill_last_success_timestamp_seconds`. Targets: RPO 24 h, RTO 8 h (the drill records its own time).
9. **After a restore, everyone signs in again.** A dump from last night would bring back sessions and users as they were then: a user disabled or a refresh token revoked since the backup would be valid again (finding F18). `python -m app.cli revoke-all-sessions` in auth (new) revokes every refresh session, writes a Redis revocation for every user and organization, and records `auth.sessions_revoked`; `restore.sh` runs it. The audit trail of what changed between the backup and the failure is not recoverable from the dump, so the runbook says so and asks the admin to re-apply disables from the Kafka log if it survived (replay of the `auth` events).
10. **The security review is a checklist with a result per line, not a report.** `docs/security/asvs-l2.md` lists the ASVS L2 items that apply (V2 authentication, V3 sessions, V4 access control, V5 validation, V7 errors and logging, V8 data protection, V9 communication, V12 files, V13 API, V14 configuration), each with the code or test that answers it, or "not applicable: why". It holds results only: a finding that is open is a private GitHub issue until fixed, because the repository is public. CI gains `pip-audit` and `npm audit --omit=dev` that fail on high or critical, `dependabot.yml` (pip, npm, docker, actions: weekly, grouped), and the nightly ZAP baseline.
11. **Load tests are regression tests with numbers, run on a host that can take them.** Locust in `infra/loadtest/`: 50 users in the mix of PRD NFR-1 (browse, dashboard, request page, comments, sync of 20 ops, summary job) at 5x the seed volume (250 stations, 1,000 requests, 500 visits), plus 20 simultaneous presigned video uploads of a 100 MiB file and a 1-hour soak with the nightly check and the digest running. Thresholds: p95 under 1 s for reads (NFR-2), failures under 1%, no DLQ message, outbox lag under 30 s, a summary ready within 2 minutes. **CI runs a 1-minute, 5-user smoke of the same script** so it does not rot. The full run is on the production host before it takes real traffic (data wiped after), never on the shared staging server. [Question 3.]
12. **Production deploys by hand and rolls back by tag.** `production.yml` is `workflow_dispatch` with an image tag, needs approval from the `production` environment, runs `compose.yml` + `compose.prod.yml` over SSH, then `@smoke`; rollback is the same workflow with the previous tag (TRD §18). It is skipped until `PRODUCTION_HOST` is set, as the staging deploy was. A nightly failure of the full suite or the ZAP scan blocks it (TP).

## 4. Back end and infrastructure

| Where | What |
|---|---|
| mms_common | `metrics.py` (definitions and `instrument(app, service)`), the middleware, hooks in `outbox`/`relay`, `consumer`, `jobs`, `cron` (job duration and failure; the cron's last success), a `Clock`-friendly lag calculation; tests for names, labels and values |
| auth | `revoke-all-sessions` CLI and the `auth.sessions_revoked` event (audit mapping, PRD AUD-1) |
| operations, media, report, platform | The metrics each owns: `sync_ops_total` (operations), `job_duration_seconds` for derive and scan (media), `report_render_seconds` and `reports_finalizing_oldest_seconds` (report), `clamav_signature_age_seconds` (media, from `clamd VERSION`), consumer lag and DLQ size (platform and operations consumers, from the library) |
| infra/monitoring | `compose.monitoring.yml` (Prometheus, Alertmanager, Grafana, Loki, Alloy, node-exporter, kafka-exporter, mongodb-exporter, redis-exporter, nginx-prometheus-exporter), `prometheus.yml`, `rules/*.yml` and `tests/*.yml`, `alertmanager.yml.template`, `grafana/provisioning` (datasources and five dashboards: API latency and errors per service, consumer lag per group, media queue, sync results, disk usage), `loki.yml`, `alloy.river` |
| infra/backup | `Dockerfile`, `backup.sh`, `prune.sh`, `restore.sh`, `config-archive.sh`, `filer-sync` entry, the drill (`infra/tests/restore_drill.py`), the runbook in the docs site |
| infra/nginx | `stub_status` server block on an internal port; `location = /metrics { return 404; }` explicit; `limit_req` zones for the audit export and summary route (W19-3 left a note) are checked in place |
| infra/loadtest | `locustfile.py`, `seed_volume.py` (a test-only command that refuses production), thresholds file, README |
| .github | `monitoring`, `backup` jobs in `backend.yml`; `security.yml` (audits on PRs, ZAP nightly against staging); `restore-drill.yml` (weekly); `production.yml`; `loadtest.yml` (manual, plus the smoke in `backend.yml`); `dependabot.yml` |

## 5. The alerts (slice 2)

Every row of TRD §16.5, as a rule with its `for:`; each has one `promtool` test that makes it fire and one that keeps it quiet, and the drill fires each once into Mailpit.

| Alert | Expression (summary) | For |
|---|---|---|
| ServiceDown | `up{job=~"auth\|operations\|media\|report\|platform"} == 0` | 2 m |
| High5xxRate | 5xx share of `http_requests_total` > 2% per service | 5 m |
| DeadLetterNotEmpty | `increase(dlq_messages_total[5m]) > 0` or `kafka_consumergroup_lag` on any `mms.dlq.*` topic | 1 m |
| OutboxStuck | `outbox_oldest_unpublished_seconds > 300` | 1 m |
| ConsumerLag | `consumer_lag_seconds > 300` | 5 m |
| ReportFinalizingLong | `reports_finalizing_oldest_seconds > 1800` | 1 m |
| DiskAlmostFull | node filesystem use above 80% on the data mounts | 10 m |
| BackupMissing | `time() - backup_last_success_timestamp_seconds > 93600` (26 h), any kind | 10 m |
| AuditChainBroken | `audit_chain_ok == 0` | 0 m |
| ClamAvSignaturesOld | `clamav_signature_age_seconds > 259200` (3 days) | 1 h |

Two more that the weekly drill needs: **RestoreDrillOld** (no success in 8 days) and **ScrapeMissing** (a service present in `compose` but not scraped). The production stack runs ClamAV; on staging (`MEDIA_SCAN_MODE=off`, T8) the ClamAV rule is not loaded.

## 6. PWA pre-flight (answers)

1. **Device.** Nothing in W20 runs on a phone. The Nginx change adds a `/metrics` 404 and an internal listener; it must not touch the `no-cache` headers of `sw.js`, `index.html`, `theme-init.js` and the manifest, the CSP, or the `files.` host. `infra/tests` already asserts them and runs after every Nginx change.
2. **Network.** An alert about the sync path is only useful if it sees what phones see: `sync_ops_total{result="conflict"|"error"}` by reason is the first number the hypercare triage (W26) will read. It counts results, never op ids.
3. **Lifecycle.** A deploy replaces the service worker's `sw.js`; production deploys are by hand and outside field hours where possible, and the update prompt (never a silent reload) already covers a phone that is mid-visit. A rollback to the previous tag serves the previous `sw.js`: the worker file name stays `sw.js` and the precache is revisioned, so a phone on the newer build sees "a new version" and takes the older one; the `no-cache` header is what makes this safe. A test in slice 4 serves two builds in turn and checks the prompt both ways (the release-0.1 test already does it one way).
4. **Data and loss.** **Restore is the one operation that can erase work a phone has already handed over (F18).** A phone deletes its local copy once the server confirms (OFF-8). A restore to last night's dump loses what was confirmed after it, and the phone has nothing left to send. Mitigations in this plan: the RPO is stated in the runbook; the media objects are replicated within minutes, so photos and files of a lost visit are still in the store, and media's `reconcile` is checked to report objects with no record; the restore runbook asks the admin to list visits ended after the dump time from the outbox topic if Kafka survived. Ops queued but not yet confirmed are unaffected: the queue on the phone is untouched and `op_id` idempotency applies them to the restored server. The drill proves this: it syncs a visit, takes a dump, syncs a second visit, restores and checks the second visit's phone-side record is gone and the first intact, and a third visit queued on the "phone" applies.
5. **Storage.** Server side: sizing in slice 4 (dumps at about the size of the databases, compressed; objects doubled on the backup host); disk alert at 80%. Nothing on devices.
6. **Caching.** Not touched. Monitoring and Grafana are never behind Nginx, so no cacheable response comes from them.
7. **Security.** Exporters have least-privilege users; backups are encrypted with a key that is not on the host; the backup host receives ciphertext and replicated objects only; `restore.sh` and `revoke-all-sessions` are operator commands run in a container, not routes; alerts carry no personal data (labels are service and job names); the ASVS review and the cross-organization run are the check of rules 3, 4 and 6 from outside; production refuses `MEDIA_SCAN_MODE=off` (exists) and a test adds "docs disabled, no dev ports, no Mailpit".
8. **Proof.** Python: metric names and labels, the lag math under `ManualClock`, the cron success gauge, `revoke-all-sessions` (a client, a disabled user, a refresh in flight, then login works). `promtool test rules` for the ten alerts. A compose job brings the monitoring stack up, kills a service, breaks a dump timestamp and an audit record, and checks each alert reaches Mailpit. The restore drill (CI weekly, and each time `infra/backup` changes) ends in the chain check. Locust smoke in CI. The real-device row of the exit checks is unchanged: W15's iPhone and Android checks are still the PWA launch proof and are not part of W20.

## 7. Tests and exit checks

- **Exit (IP):** production runs with monitoring and test alerts delivered (needs the host, [Question 1]); a restore into staging passes the audit chain check; no open high or critical security findings; the load test meets NFR-2.
- **What can be proved before the hosts exist:** every metric and rule, the alert path into Mailpit, the backup and restore scripts on the local and CI stacks, the weekly CI drill, the ASVS checklist, `pip-audit`/`npm audit`/ZAP, the Locust smoke and a local full run at a smaller scale. These are written down as lower bounds, as W11's timings were.
- **Staging release 0.7 (IP):** with W19: admins and a Viewer run summaries; plus the W20 items above. The release is version `0.7.0` in `frontend/package.json` (decision W4-17).
- **Docs site:** Build status and badges (P7), the monitoring, backup and production sections in Infrastructure, the new settings (`MMS_ALERT_EMAILS`, `BACKUP_*`, `REPORT_*` none), decisions W20-1 to W20-12, the metric catalogue, the alert table, the runbook, the changelog and the charts below. Documents: TRD §14, §15, §16.1, §16.4, §16.5, §18, R-table (a new restore risk); TP (the continuous checks as built); IP (W20 status); BSD (`audit_checks` unchanged; backup retention row); `.claude/skills/pwa/references/findings.md` (F18).

## 8. Findings raised by this plan

| # | Finding | Proposed answer |
|---|---|---|
| F18 | **A restore can erase work a phone already handed over.** OFF-8 deletes the local copy after the server confirms, so a restore to an older dump loses visits confirmed since, with nothing on any phone to resend. Sessions and disabled users also come back as they were in the dump | State the RPO in the runbook and in AFD; keep the objects' replica close to real time; list visits ended since the dump from Kafka if it survived; `revoke-all-sessions` at restore (decision 9); the drill proves which cases are safe. A longer-lived answer (keep the local copy for N days after confirmation) is a W20+ decision for you: it costs storage (200 MB videos) and is not proposed here |

## 9. Questions for you

1. **Hosts.** Do the production host and the backup host exist now (B1, T6, T8)? Default: **no, or not yet reachable**: W20 builds and tests everything on the local stack and in CI, the full load run and the first production deploy wait for the host (they use the buffer, W21 to W22, if the host arrives late), and the exit "production runs with monitoring" stays open until then.
2. **Alerting engine.** Default: Prometheus rules and Alertmanager (testable with `promtool`, in code). Or Grafana-managed alerts, which are one container fewer but live in provisioning files that cannot be unit-tested the same way.
3. **Where the full load test runs.** Default: on the production host before go-live, with data wiped after; CI runs a small smoke. Or a rented, same-size VM for one day (cost), or the shared staging server at night with half the load (risk to the other sites on it).
4. **What runs on staging.** Default: Prometheus, Alertmanager and exporters (about 350 MB) if the free memory is at least 1 GB when measured, to fire the alerts for real; Grafana and Loki only locally. Or nothing on staging, with the alert drill in CI only.
5. **Who holds the backup private key.** Default: organization IT, offline (sealed copy plus a second holder), with the public key in the host's `.env`. Needs a name and a date before the first production backup. A backup nobody can decrypt is worth nothing, so the drill decrypts with a test key only; the real key's restore is tested once by its holder.
6. **Backup transport.** Default: SFTP with `rclone` to the backup host for dumps, `weed filer.sync` for objects. Or an S3 bucket on the backup host's SeaweedFS for the dumps as well (one less credential).
7. **ZAP target.** Default: a nightly **baseline** (passive) scan of staging from a GitHub runner, with the runner's address allowed past the rate limit through the office allow-list pattern. The staging edge is shared, so no active scan.
8. **Security results in a public repository.** Default: the ASVS checklist with results is committed; any open finding stays a private issue until fixed and is then noted as fixed.
9. **Alert recipients.** Default: the admin addresses in `MMS_ALERT_EMAILS`, plus a second address outside the system's own mail domain for the "mail is down" case. Needs the addresses.
10. **Keep a phone's copy longer after confirmation (F18).** Default: **no**, as OFF-8 says; the RPO is the answer. Say if you want it designed (a retention of N days for ended visits' blobs on the phone) as a W20+ item.

## 10. Charts proposed for this phase

At the start of each phase the charts are suggested and you choose (CLAUDE.md). Proposed for W20, from the catalogue and the P7 row of the Diagram guide (backup and restore data flow, monitoring system flowchart, production architecture):

| Chart | Type | Shows |
|---|---|---|
| Backup and restore | Data flow | What is copied where (Mongo dumps, objects, config), what encrypts it, where the key is, and what a restore needs |
| Metrics, logs and alerts | System flowchart | Services and exporters to Prometheus and Loki, rules to Alertmanager to email, dashboards in Grafana |
| Production architecture | Architecture (draw.io, with a Mermaid tab) | The production host, the backup host, the edge, networks, ports and what is published |
| Restore drill | Sequence | Dump, restore, group reset, backfill, session revoke, chain check, and which phone-side cases survive (F18) |
| Which restore | Decision tree | Mongo lost, objects lost, host lost, a bad deploy: the path for each |
| Production deploy and rollback | Workflow | Tag, approval, deploy, smoke, nightly gate, rollback |
| Security checks by trigger | Process flow | What runs on a PR, nightly, weekly and by hand: audits, Trivy, ZAP, drill, load |

Each is drawn from what its slice built, never from the design, in the slice's own pull request, as in W17 to W19. The docs site's Diagram guide lists them under P7.
