"""The S3 store behind the files host (TRD §10). boto3 is synchronous, so calls run in threads.

`internal` talks to SeaweedFS on the container network; `signing` only makes presigned URLs,
which carry the public files host the browser uses because the signature covers the host.
"""

from __future__ import annotations

import asyncio

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageError(Exception):
    """The store failed or refused. The message never leaves the server."""


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
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


class Storage:
    def __init__(self, internal: BaseClient, signing: BaseClient) -> None:
        self._s3 = internal
        self._sign = signing

    async def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        """Store an object. The same key again replaces it, so a repeated job is harmless."""
        try:
            await asyncio.to_thread(
                self._s3.put_object, Bucket=bucket, Key=key, Body=data, ContentType=content_type
            )
        except (ClientError, BotoCoreError) as e:
            raise StorageError(str(e)) from e

    def get_url(
        self, bucket: str, key: str, ttl_s: int, *, content_type: str, filename: str
    ) -> str:
        """A time-limited download link on the files host (10 minutes, TRD §10.1)."""
        url: str = self._sign.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket, "Key": key, "ResponseContentType": content_type,
                "ResponseContentDisposition": f'inline; filename="{filename}"',
            },
            ExpiresIn=ttl_s,
        )
        return url
