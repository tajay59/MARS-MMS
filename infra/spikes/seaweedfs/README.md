# SeaweedFS spike (Phase 0)

Half a day, in W1. It confirms that SeaweedFS has the S3 features the app relies on (TRD §10, ADR-6, decision T7, risk R6) before anything is built on it. If a **MUST** check fails, switch to Garage (the app uses only the S3 API).

This is throwaway code. It isn't part of the app stack, and its credentials are for local use only.

## What runs

| Container | Role |
|---|---|
| `seaweedfs` | `chrislusf/seaweedfs:4.48`: master, volume, filer and S3 gateway in one process. `-s3.allowedOrigins` limits CORS to the app origin |
| `nginx` | Two hosts on port 8080, as in production: the app at `localhost` and the files host at `files.localhost`, passed straight to the S3 gateway with the `Host` header intact and the production 16 MB body limit |
| `spike` | Python 3.13 + boto3: the presign API and upload page (`server.py`) and the server-side checks (`check.py`) |

Buckets, part size and URL lifetimes follow TRD §10: `mms-originals`, `mms-media`, `mms-documents`, `mms-reports` (the last two with object lock enabled), 8 MiB parts, presigned GET 10 minutes, upload parts 1 hour.

## Run it

You need Docker Desktop (WSL 2 backend on Windows). Run these in this folder:

```sh
docker compose up -d --build
docker compose run --rm spike python check.py
```

Then open <http://localhost:8080> in Chrome or Edge, and in Firefox:

1. **Upload a generated 20 MiB file** (3 parts). All four lines must say PASS.
2. Upload a real phone video of 100 MB or more.
3. **Start an upload and abandon it**, then **List open uploads**. It shows with its start time; **Abort** removes it.

`files.localhost` resolves to your own machine in Chrome, Edge and Firefox without any hosts-file change.

### From a phone (phone mode)

A phone can't use the normal mode: `files.localhost` means the phone itself, and its page origin (`http://<PC address>:8080`) isn't allowed by CORS, so every part fails with "Failed to fetch". Phone mode allows that page origin and signs part URLs for `http://<PC address>.sslip.io:8080`, a public DNS name that resolves to the PC. It stays on port 8080 (a different host is still a different origin), because this PC's firewall lets 8080 in from the Wi-Fi but silently drops other ports such as 8081:

```sh
LAN_IP=192.168.1.20 docker compose -f compose.yml -f compose.phone.yml up -d --build   # your PC's Wi-Fi address
```

Then open `http://<LAN_IP>:8080` on a phone on the same Wi-Fi. Keep the screen on while it uploads: mobile browsers pause background tabs. Run `check.py` in normal mode, not in phone mode; go back with `docker compose up -d`.

The app's limit is 200 MB per video (MED-6). A larger file still tests multipart, but the app would refuse it.

Clean up with `docker compose down -v`. That deletes the stored data, including objects under 1-day object-lock retention.

## Checks

| Level | Check | Why the app needs it |
|---|---|---|
| MUST | Presigned PUT and GET through the files host | Every upload and download (ADR-6) |
| MUST | Expired or edited presigned URLs are refused | Private buckets; links can't be reused or redirected |
| MUST | Multipart upload with presigned part URLs; ListParts | Resumable uploads of 200 MB videos (`/uploads/{id}/parts`) |
| MUST | ListMultipartUploads with start time; AbortMultipartUpload | The `abort_stale_uploads` cron (48 hours) |
| MUST | Bucket CORS: app origin allowed, other origins refused, `ETag` exposed | The browser must read each part's ETag to complete the upload (TRD §2.1) |
| MUST | Browser upload on the page passes | The real cross-origin behaviour, which a script can't prove |
| NICE | Versioning keeps old versions | Extra protection for config files |
| NICE | COMPLIANCE retention blocks deleting a final report | Extra layer; immutability is enforced by the app anyway (TRD §10.1) |
| INFO | Global `-s3.allowedOrigins` behaviour without bucket rules | Decides whether bucket CORS rules are needed at all |
| INFO | Bucket default retention | Whether lock could be set per bucket instead of per object |
| INFO | boto3's default checksum settings | Whether the media service needs `request_checksum_calculation="when_required"` |

## Record the result

When it's done, record the outcome in the IP Phase 0 deliverables and TRD T7 / R6: SeaweedFS version, pass or fail per check, browser versions, upload time for the large video, and anything to carry into the media service (CORS setup, checksum settings).

## Result, 2026-10-16: passed

Run on Windows 11 with Docker Desktop 29.8.2 (Compose v5.6.0, WSL 2). SeaweedFS `chrislusf/seaweedfs:4.48`, Nginx `1.31.7-alpine`.

**Server-side (`check.py`): 15 of 15 passed.**

| Level | Check | Result |
|---|---|---|
| MUST | Four buckets; object lock on `mms-documents` and `mms-reports` | PASS |
| MUST | Presigned PUT through the files host | PASS |
| MUST | Presigned GET returns the same bytes | PASS |
| MUST | Expired presigned URL refused | PASS |
| MUST | Presigned URL edited to another key refused | PASS |
| MUST | Multipart with presigned part URLs (8 MiB + 1 MiB) | PASS |
| MUST | ListMultipartUploads with start time; AbortMultipartUpload | PASS |
| MUST | Bucket CORS rule round-trips | PASS |
| MUST | Preflight from the app origin allowed; PUT exposes `ETag` | PASS |
| MUST | Preflight from another origin refused | PASS |
| NICE | Versioning keeps both versions | PASS |
| NICE | COMPLIANCE retention blocks deleting a final report | PASS (`AccessDenied`) |
| INFO | Global `-s3.allowedOrigins` only | Allows the app origin, refuses others, exposes `ETag, Content-Length, Content-Type, Last-Modified, x-amz-request-id, x-amz-version-id` |
| INFO | Bucket default retention | Applies to new objects (COMPLIANCE, 1 day) |
| INFO | boto3 default checksum settings | PutObject and presigned PUT both accepted |

**Browser (Chrome 155.0.8059.80): passed.**

| Test | Result |
|---|---|
| Generated 20 MiB file | 3 parts, readable ETags, size matches, read back: PASS. 0.8 s |
| Video, 50.9 MiB (a screen recording) | 7 parts, readable ETags, size 53,376,658 bytes matches, read back: PASS. 2.0 s |
| Abandon an upload, list, abort | Listed as 1 open upload, aborted, 0 left: PASS |

**For the media service:** the global `-s3.allowedOrigins` flag already restricts CORS and exposes `ETag`, so bucket CORS rules are optional (keep them as a second layer if wanted). boto3's default checksums work, so `request_checksum_calculation="when_required"` isn't needed. Object lock can be set as a bucket default.

**First phone attempt (Android, Chrome, 786.7 MiB video, 99 parts):** failed at part 1 with "Failed to fetch". Cause: the spike's setup, not SeaweedFS (presigned URLs pointed at `files.localhost`, and the phone's page origin wasn't allowed). Phone mode was added. A first version on port 8081 failed the same way (152.8 MiB video): the phone's requests never reached Nginx because the PC's firewall (Windows Wi-Fi profile Public, ESET installed) drops inbound 8081. Phone mode now uses `<LAN_IP>.sslip.io:8080`; a simulated phone-origin upload through it passed (preflight allowed for the phone origin and refused for others, ETags exposed, complete 200, read back intact).

**Phone run in phone mode (Android, Chrome, over the office Wi-Fi to `<LAN_IP>:8080`): passed.**

| Test | Result |
|---|---|
| Phone video, 152.8 MiB (160,172,943 bytes) | 20 parts of 8 MiB, every part cross-origin with a readable ETag, stored size matches, presigned GET read back the same size: PASS. 47.5 s (about 3.2 MiB/s, 27 Mbit/s) |
| Abandon an upload, list, abort | Started `abandoned.bin`, uploaded part 1 of 2, listed (6 open), aborted one, 5 left: PASS |

The open-upload list also held four uploads left behind by the earlier failed phone attempts (two 20 MiB files and two videos). That is the case the media service's `abort_stale_uploads` job is for: a phone that loses the connection mid-upload leaves an open multipart upload on the server, and nothing else cleans it up.

Not covered by this run: an iPhone (Safari), the 786.7 MiB video (above the 200 MB media limit, so not needed), a dropped connection resumed from the last confirmed part (that is app logic, tested in Phase 4 and W15), and HTTPS (the page was plain HTTP on the LAN; production is HTTPS only).

**Firefox 158.0 (Windows, `http://localhost:8080`): passed.**

| Test | Result |
|---|---|
| Generated 20 MiB file | 3 parts, readable ETags, size 20,971,520 bytes matches, read back: PASS. 1.0 s |
| Video, 50.9 MiB (the same screen recording as in Chrome) | 7 parts, readable ETags, size 53,376,658 bytes matches, read back: PASS. 2.5 s |
| Abandon an upload, list, abort | Started `abandoned.bin`, uploaded part 1 of 2, listed (6 open), aborted one, 5 left: PASS |

**Every planned check has now passed** (server side, Chrome, Firefox, Android phone). Optional: the same phone-mode run from an iPhone in Safari, if one is at hand, since iOS is the weakest browser the app supports. Clean up with `docker compose down -v`; the five open uploads go with the volumes.
