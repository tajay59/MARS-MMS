"""The S3 store behind the files host (TRD §10). boto3 is synchronous, so calls run in threads.

Two clients: `internal` talks to SeaweedFS on the container network; `signing` only makes
presigned URLs, which carry the public files host the browser uses because the signature
covers the host (TRD §2.1).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError


class StorageError(Exception):
    """The store failed or refused. The message never leaves the server."""


class UploadGone(StorageError):
    """The multipart upload no longer exists (completed or aborted)."""


@dataclass(frozen=True)
class Part:
    number: int
    size: int
    etag: str


def make_client(endpoint: str, access_key: str, secret_key: str) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=60,
            # SeaweedFS accepts boto3's default checksums (spike, 2026-10-16); presigned
            # browser uploads send none, so only add them where an operation requires them.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


class Storage:
    def __init__(self, internal: BaseClient, signing: BaseClient) -> None:
        self._s3 = internal
        self._sign = signing

    # --- multipart ---------------------------------------------------------------------------

    async def create_multipart(self, bucket: str, key: str, content_type: str) -> str:
        try:
            out = await asyncio.to_thread(
                self._s3.create_multipart_upload, Bucket=bucket, Key=key, ContentType=content_type
            )
        except ClientError as e:
            raise StorageError(_code(e)) from e
        return str(out["UploadId"])

    async def list_parts(self, bucket: str, key: str, upload_id: str) -> dict[int, Part]:
        """The parts the store holds for this upload: the truth about what has arrived."""
        found: dict[int, Part] = {}
        marker = 0
        while True:
            try:
                out: dict[str, Any] = await asyncio.to_thread(
                    self._s3.list_parts, Bucket=bucket, Key=key, UploadId=upload_id,
                    PartNumberMarker=marker, MaxParts=1000,
                )
            except ClientError as e:
                if _code(e) == "NoSuchUpload":
                    raise UploadGone() from e
                raise StorageError(_code(e)) from e
            for p in out.get("Parts", []):
                found[int(p["PartNumber"])] = Part(
                    int(p["PartNumber"]), int(p["Size"]), str(p["ETag"])
                )
            if not out.get("IsTruncated"):
                return found
            marker = int(out["NextPartNumberMarker"])

    async def complete(self, bucket: str, key: str, upload_id: str, parts: list[Part]) -> None:
        try:
            await asyncio.to_thread(
                self._s3.complete_multipart_upload, Bucket=bucket, Key=key, UploadId=upload_id,
                MultipartUpload={"Parts": [
                    {"PartNumber": p.number, "ETag": p.etag}
                    for p in sorted(parts, key=lambda p: p.number)
                ]},
            )
        except ClientError as e:
            if _code(e) == "NoSuchUpload":
                raise UploadGone() from e
            raise StorageError(_code(e)) from e

    async def abort(self, bucket: str, key: str, upload_id: str) -> None:
        try:
            await asyncio.to_thread(
                self._s3.abort_multipart_upload, Bucket=bucket, Key=key, UploadId=upload_id
            )
        except ClientError as e:
            if _code(e) != "NoSuchUpload":
                raise StorageError(_code(e)) from e

    # --- objects -----------------------------------------------------------------------------

    async def size(self, bucket: str, key: str) -> int | None:
        """The stored object's size, or None when there is no such object."""
        try:
            out = await asyncio.to_thread(self._s3.head_object, Bucket=bucket, Key=key)
        except ClientError as e:
            if _code(e) in ("404", "NoSuchKey", "NotFound"):
                return None
            raise StorageError(_code(e)) from e
        return int(out["ContentLength"])

    async def read(self, bucket: str, key: str, chunk: int = 1024 * 1024) -> AsyncIterator[bytes]:
        """The object in chunks, so a 200 MB file never sits in memory."""
        try:
            out = await asyncio.to_thread(self._s3.get_object, Bucket=bucket, Key=key)
        except ClientError as e:
            raise StorageError(_code(e)) from e
        body = out["Body"]
        try:
            while data := await asyncio.to_thread(body.read, chunk):
                yield bytes(data)
        finally:
            body.close()

    async def download_to(self, bucket: str, key: str, path: Path) -> None:
        """The object saved to a file, for a tool that needs one (ffmpeg, Pillow)."""
        try:
            await asyncio.to_thread(self._s3.download_file, bucket, key, str(path))
        except ClientError as e:
            raise StorageError(_code(e)) from e

    async def upload_file(self, bucket: str, key: str, path: Path, content_type: str) -> int:
        """A file stored under `key` (multipart for a large one, handled by boto3); returns its
        size."""
        def send() -> int:
            self._s3.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type})
            return path.stat().st_size

        try:
            return await asyncio.to_thread(send)
        except (ClientError, boto3.exceptions.S3UploadFailedError) as e:
            raise StorageError(type(e).__name__) from e

    async def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._s3.put_object, Bucket=bucket, Key=key, Body=data, ContentType=content_type
            )
        except ClientError as e:
            raise StorageError(_code(e)) from e

    async def delete(self, bucket: str, key: str) -> None:
        try:
            await asyncio.to_thread(self._s3.delete_object, Bucket=bucket, Key=key)
        except ClientError as e:
            raise StorageError(_code(e)) from e

    # --- presigned URLs (local computation, no network) ------------------------------------

    def part_url(self, bucket: str, key: str, upload_id: str, number: int, ttl_s: int) -> str:
        return str(self._sign.generate_presigned_url(
            "upload_part",
            Params={"Bucket": bucket, "Key": key, "UploadId": upload_id, "PartNumber": number},
            ExpiresIn=ttl_s,
        ))

    def get_url(
        self, bucket: str, key: str, ttl_s: int, *, content_type: str, disposition: str
    ) -> str:
        return str(self._sign.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket, "Key": key, "ResponseContentType": content_type,
                "ResponseContentDisposition": disposition,
            },
            ExpiresIn=ttl_s,
        ))
