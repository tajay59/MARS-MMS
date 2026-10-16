"""Server-side checks for the SeaweedFS spike (IP Phase 0, TRD §10, risk R6).

    docker compose run --rm spike python check.py

MUST checks are features the app relies on; one failure means switching to Garage.
NICE checks are versioning and object lock, an extra layer the app doesn't depend on
(TRD §10.1). INFO checks record behaviour worth knowing when building the media service.
Exits 1 if any MUST check fails.
"""

import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from email.message import Message
from urllib.parse import urlsplit, urlunsplit

from botocore.exceptions import ClientError

import s3client as s3

OTHER_ORIGIN = "http://evil.localhost:8080"
MiB = 1024 * 1024

results: list[tuple[str, str, str, str]] = []


def http(method: str, url: str, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def check(level: str, name: str):
    def decorator(fn):
        try:
            detail = fn() or ""
            results.append((level, "PASS", name, detail))
        except Exception as e:  # noqa: BLE001 - every failure is a result, not a crash
            results.append((level, "FAIL", name, f"{type(e).__name__}: {e}"))
        return fn

    return decorator


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def new_key(prefix: str = "check") -> str:
    return f"spike/{prefix}/{uuid.uuid4()}"


def preflight(url: str, origin: str) -> Message:
    path_only = urlunsplit(urlsplit(url)._replace(query=""))
    _, headers, _ = http(
        "OPTIONS",
        path_only,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    return headers


def exposes_etag(headers: Message) -> bool:
    exposed = [h.strip().lower() for h in (headers.get("Access-Control-Expose-Headers") or "").split(",")]
    return "etag" in exposed or "*" in exposed


s3.wait_ready()


@check("MUST", "Four buckets exist; mms-documents and mms-reports have object lock enabled")
def _():
    s3.ensure_buckets()
    for name in s3.BUCKETS:
        s3.internal.head_bucket(Bucket=name)
    return ", ".join(s3.BUCKETS)


@check("MUST", "Presigned PUT through the files host")
def _():
    key = new_key()
    url = s3.files.generate_presigned_url(
        "put_object", Params={"Bucket": s3.UPLOAD_BUCKET, "Key": key, "ContentType": "text/plain"}, ExpiresIn=s3.PART_TTL
    )
    status, headers, body = http("PUT", url, b"hello", {"Content-Type": "text/plain"})
    expect(status == 200, f"HTTP {status}: {body[:200]!r}")
    expect(bool(headers.get("ETag")), "no ETag header in the response")
    return f"ETag {headers.get('ETag')}"


@check("MUST", "Presigned GET through the files host returns the same bytes")
def _():
    key = new_key()
    s3.internal.put_object(Bucket=s3.UPLOAD_BUCKET, Key=key, Body=b"round trip")
    url = s3.files.generate_presigned_url(
        "get_object", Params={"Bucket": s3.UPLOAD_BUCKET, "Key": key}, ExpiresIn=s3.GET_TTL
    )
    status, _, body = http("GET", url)
    expect(status == 200 and body == b"round trip", f"HTTP {status}, body {body[:60]!r}")


@check("MUST", "An expired presigned URL is refused")
def _():
    key = new_key()
    s3.internal.put_object(Bucket=s3.UPLOAD_BUCKET, Key=key, Body=b"x")
    url = s3.files.generate_presigned_url("get_object", Params={"Bucket": s3.UPLOAD_BUCKET, "Key": key}, ExpiresIn=1)
    time.sleep(3)
    status, _, _ = http("GET", url)
    expect(status == 403, f"expected 403, got {status}")


@check("MUST", "A presigned URL edited to point at another key is refused")
def _():
    key, other = new_key(), new_key()
    s3.internal.put_object(Bucket=s3.UPLOAD_BUCKET, Key=other, Body=b"secret")
    url = s3.files.generate_presigned_url(
        "get_object", Params={"Bucket": s3.UPLOAD_BUCKET, "Key": key}, ExpiresIn=s3.GET_TTL
    )
    status, _, _ = http("GET", url.replace(key, other))
    expect(status == 403, f"expected 403, got {status}")


@check("MUST", "Multipart upload with presigned part URLs (8 MiB + 1 MiB) through the files host")
def _():
    key = new_key("multipart")
    upload_id = s3.internal.create_multipart_upload(Bucket=s3.UPLOAD_BUCKET, Key=key)["UploadId"]
    parts = []
    for number, size in ((1, 8 * MiB), (2, 1 * MiB)):
        url = s3.files.generate_presigned_url(
            "upload_part",
            Params={"Bucket": s3.UPLOAD_BUCKET, "Key": key, "UploadId": upload_id, "PartNumber": number},
            ExpiresIn=s3.PART_TTL,
        )
        status, headers, body = http("PUT", url, bytes([number]) * size)
        expect(status == 200, f"part {number}: HTTP {status}: {body[:200]!r}")
        expect(bool(headers.get("ETag")), f"part {number}: no ETag")
        parts.append({"PartNumber": number, "ETag": headers["ETag"]})
    listed = s3.internal.list_parts(Bucket=s3.UPLOAD_BUCKET, Key=key, UploadId=upload_id)
    expect(len(listed.get("Parts", [])) == 2, "ListParts did not return both parts (needed to resume)")
    s3.internal.complete_multipart_upload(
        Bucket=s3.UPLOAD_BUCKET, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
    )
    head = s3.internal.head_object(Bucket=s3.UPLOAD_BUCKET, Key=key)
    expect(head["ContentLength"] == 9 * MiB, f"size {head['ContentLength']}, expected {9 * MiB}")
    return f"final ETag {head['ETag']}"


@check("MUST", "ListMultipartUploads shows an open upload with its start time; AbortMultipartUpload removes it")
def _():
    key = new_key("abandoned")
    upload_id = s3.internal.create_multipart_upload(Bucket=s3.UPLOAD_BUCKET, Key=key)["UploadId"]
    s3.internal.upload_part(Bucket=s3.UPLOAD_BUCKET, Key=key, UploadId=upload_id, PartNumber=1, Body=b"a" * 5 * MiB)
    listing = s3.internal.list_multipart_uploads(Bucket=s3.UPLOAD_BUCKET, Prefix=key)
    found = [u for u in listing.get("Uploads", []) if u["UploadId"] == upload_id]
    expect(len(found) == 1, "the open upload is not listed (abort_stale_uploads can't find it)")
    expect(isinstance(found[0].get("Initiated"), datetime), "no Initiated time (needed for the 48-hour rule)")
    s3.internal.abort_multipart_upload(Bucket=s3.UPLOAD_BUCKET, Key=key, UploadId=upload_id)
    listing = s3.internal.list_multipart_uploads(Bucket=s3.UPLOAD_BUCKET, Prefix=key)
    expect(not any(u["UploadId"] == upload_id for u in listing.get("Uploads", [])), "still listed after abort")
    url = s3.files.generate_presigned_url(
        "upload_part",
        Params={"Bucket": s3.UPLOAD_BUCKET, "Key": key, "UploadId": upload_id, "PartNumber": 2},
        ExpiresIn=s3.PART_TTL,
    )
    status, _, _ = http("PUT", url, b"b" * 1024)
    expect(status >= 400, f"a part was accepted after abort (HTTP {status})")
    return f"Initiated {found[0]['Initiated'].isoformat()}"


@check("INFO", "CORS from the global -s3.allowedOrigins flag only (bucket without CORS rules)")
def _():
    bucket = f"spike-cors-{uuid.uuid4().hex[:8]}"
    s3.create_bucket(bucket)
    url = f"{s3.FILES_URL}/{bucket}/probe"
    allowed = preflight(url, s3.APP_ORIGIN)
    other = preflight(url, OTHER_ORIGIN)
    return (
        f"app origin -> Allow-Origin={allowed.get('Access-Control-Allow-Origin')!r}, "
        f"Expose={allowed.get('Access-Control-Expose-Headers')!r}; "
        f"other origin -> Allow-Origin={other.get('Access-Control-Allow-Origin')!r}"
    )


@check("MUST", "Bucket CORS rule round-trips (PutBucketCors / GetBucketCors)")
def _():
    s3.internal.put_bucket_cors(Bucket=s3.UPLOAD_BUCKET, CORSConfiguration=s3.CORS_RULES)
    rules = s3.internal.get_bucket_cors(Bucket=s3.UPLOAD_BUCKET)["CORSRules"]
    expect(rules[0]["AllowedOrigins"] == s3.ALLOWED_ORIGINS, f"stored rules: {rules}")


@check("MUST", "Preflight from the app origin is allowed, and a PUT exposes ETag")
def _():
    key = new_key("cors")
    url = s3.files.generate_presigned_url(
        "put_object", Params={"Bucket": s3.UPLOAD_BUCKET, "Key": key}, ExpiresIn=s3.PART_TTL
    )
    headers = preflight(url, s3.APP_ORIGIN)
    allow = headers.get("Access-Control-Allow-Origin")
    expect(allow in (s3.APP_ORIGIN, "*"), f"preflight Allow-Origin={allow!r}")
    status, put_headers, _ = http("PUT", url, b"cors", {"Origin": s3.APP_ORIGIN})
    expect(status == 200, f"PUT HTTP {status}")
    expect(exposes_etag(put_headers), f"Expose-Headers={put_headers.get('Access-Control-Expose-Headers')!r}")
    note = " (wildcard origin: tighten before production)" if allow == "*" else ""
    return f"Allow-Origin={allow!r}, Expose={put_headers.get('Access-Control-Expose-Headers')!r}{note}"


@check("MUST", "Preflight from another origin is refused")
def _():
    url = f"{s3.FILES_URL}/{s3.UPLOAD_BUCKET}/{new_key('cors')}"
    allow = preflight(url, OTHER_ORIGIN).get("Access-Control-Allow-Origin")
    expect(allow not in (OTHER_ORIGIN, "*"), f"other origin allowed: Allow-Origin={allow!r}")


@check("NICE", "Versioning keeps both versions of an overwritten object")
def _():
    bucket, key = "mms-documents", new_key("versioned")
    s3.internal.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    expect(s3.internal.get_bucket_versioning(Bucket=bucket).get("Status") == "Enabled", "status not Enabled")
    first = s3.internal.put_object(Bucket=bucket, Key=key, Body=b"v1")["VersionId"]
    s3.internal.put_object(Bucket=bucket, Key=key, Body=b"v2")
    versions = s3.internal.list_object_versions(Bucket=bucket, Prefix=key).get("Versions", [])
    expect(len(versions) == 2, f"{len(versions)} versions listed")
    old = s3.internal.get_object(Bucket=bucket, Key=key, VersionId=first)["Body"].read()
    expect(old == b"v1", f"old version reads {old!r}")


@check("NICE", "Object lock: COMPLIANCE retention on a final report blocks deleting that version")
def _():
    bucket, key = "mms-reports", new_key("final")
    version = s3.internal.put_object(
        Bucket=bucket,
        Key=key,
        Body=b"%PDF-final",
        ObjectLockMode="COMPLIANCE",
        ObjectLockRetainUntilDate=datetime.now(UTC) + timedelta(days=1),
    )["VersionId"]
    mode = s3.internal.get_object_retention(Bucket=bucket, Key=key, VersionId=version)["Retention"]["Mode"]
    expect(mode == "COMPLIANCE", f"retention mode {mode!r}")
    try:
        s3.internal.delete_object(Bucket=bucket, Key=key, VersionId=version)
    except ClientError as e:
        return f"delete refused: {e.response['Error']['Code']}"
    raise AssertionError("a locked version was deleted")


@check("INFO", "Object lock: bucket default retention applies to new objects")
def _():
    bucket, key = f"spike-lock-{uuid.uuid4().hex[:8]}", new_key("default")
    s3.create_bucket(bucket, object_lock=True)
    s3.internal.put_object_lock_configuration(
        Bucket=bucket,
        ObjectLockConfiguration={
            "ObjectLockEnabled": "Enabled",
            "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 1}},
        },
    )
    version = s3.internal.put_object(Bucket=bucket, Key=key, Body=b"x")["VersionId"]
    retention = s3.internal.get_object_retention(Bucket=bucket, Key=key, VersionId=version)["Retention"]
    return f"{retention['Mode']} until {retention['RetainUntilDate']}"


@check("INFO", "boto3 default checksum settings (without when_required) still work")
def _():
    default = s3.make_client(s3.INTERNAL_URL, checksums_when_required=False)
    default.put_object(Bucket=s3.UPLOAD_BUCKET, Key=new_key("crc"), Body=b"checksum")
    presigning = s3.make_client(s3.FILES_URL, checksums_when_required=False)
    url = presigning.generate_presigned_url(
        "put_object", Params={"Bucket": s3.UPLOAD_BUCKET, "Key": new_key("crc")}, ExpiresIn=s3.PART_TTL
    )
    status, _, body = http("PUT", url, b"checksum")
    expect(status == 200, f"presigned PUT with default settings: HTTP {status}: {body[:200]!r}")
    return "PutObject and presigned PUT both accepted"


def report() -> int:
    width = max(len(name) for _, _, name, _ in results)
    print()
    for level, outcome, name, detail in results:
        print(f"{outcome:4}  {level:4}  {name:<{width}}  {detail}")
    must_failed = [r for r in results if r[0] == "MUST" and r[1] == "FAIL"]
    nice_failed = [r for r in results if r[0] == "NICE" and r[1] == "FAIL"]
    print()
    if must_failed:
        print(f"SPIKE FAILED: {len(must_failed)} must-have check(s) failed. Fall back to Garage (IP R6).")
        return 1
    if nice_failed:
        print("SPIKE PASSED for must-haves. Versioning or object lock is missing: rely on app-level immutability.")
    else:
        print("SPIKE PASSED: every check passed. Now run the browser test at http://localhost:8080.")
    return 0


sys.exit(report())
