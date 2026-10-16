"""S3 clients and bucket setup shared by the spike server and check script.

Mirrors TRD §10: four private buckets, 8 MiB parts, presigned URLs on the files host
(10 minutes for GET, 1 hour for upload parts).
"""

import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

INTERNAL_URL = os.environ["S3_INTERNAL_URL"]
FILES_URL = os.environ["S3_FILES_URL"]
APP_ORIGIN = os.environ["APP_ORIGIN"]
# Phone mode (compose.phone.yml) adds the page origin a phone uses, e.g. http://192.168.1.20:8080.
ALLOWED_ORIGINS = [APP_ORIGIN, *(o for o in os.environ.get("EXTRA_ORIGINS", "").split(",") if o)]

BUCKETS = ["mms-originals", "mms-media", "mms-documents", "mms-reports"]
LOCKED_BUCKETS = {"mms-documents", "mms-reports"}
UPLOAD_BUCKET = "mms-originals"

PART_SIZE = 8 * 1024 * 1024
GET_TTL = 600
PART_TTL = 3600

CORS_RULES = {
    "CORSRules": [
        {
            "AllowedOrigins": ALLOWED_ORIGINS,
            "AllowedMethods": ["GET", "PUT", "HEAD"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3000,
        }
    ]
}


def make_client(endpoint: str, *, checksums_when_required: bool = True):
    """An S3 client for SeaweedFS.

    Recent boto3 versions add CRC checksums to every request by default, which
    S3-compatible stores and browser uploads of presigned parts often reject.
    ``when_required`` restores the older behaviour; check.py reports whether the
    default works too.
    """
    options: dict = {
        "signature_version": "s3v4",
        "s3": {"addressing_style": "path"},
        "retries": {"max_attempts": 3, "mode": "standard"},
    }
    if checksums_when_required:
        options["request_checksum_calculation"] = "when_required"
        options["response_checksum_validation"] = "when_required"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(**options),
    )


# Admin and server-side calls go straight to SeaweedFS on the container network.
internal = make_client(INTERNAL_URL)
# Presigning only: the URLs it signs carry the files host the browser uses.
files = make_client(FILES_URL)


def wait_ready(timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            internal.list_buckets()
            return
        except (EndpointConnectionError, ClientError):
            if time.monotonic() > deadline:
                raise
            time.sleep(2)


def create_bucket(name: str, *, object_lock: bool = False) -> None:
    try:
        if object_lock:
            internal.create_bucket(Bucket=name, ObjectLockEnabledForBucket=True)
        else:
            internal.create_bucket(Bucket=name)
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise


def ensure_buckets() -> None:
    for name in BUCKETS:
        create_bucket(name, object_lock=name in LOCKED_BUCKETS)


def apply_cors() -> list[str]:
    """Put the app-origin CORS rule on every bucket. Returns the errors, if any."""
    errors = []
    for name in BUCKETS:
        try:
            internal.put_bucket_cors(Bucket=name, CORSConfiguration=CORS_RULES)
        except ClientError as e:
            errors.append(f"{name}: {e}")
    return errors
