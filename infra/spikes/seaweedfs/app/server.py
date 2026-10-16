"""Presign API and upload page for the browser half of the spike.

Stands in for the media service's upload endpoints (TRD §3.3: POST /api/v1/uploads,
/complete), without auth or records. Standard library HTTP server plus boto3.
"""

import json
import math
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from botocore.exceptions import ClientError

import s3client as s3

STATIC = Path(__file__).parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/upload.js": ("upload.js", "text/javascript; charset=utf-8"),
}


def safe_name(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:100] or "file"


def create_upload(body: dict) -> dict:
    size = int(body["size"])
    key = f"spike/{uuid.uuid4()}/{safe_name(body.get('filename', 'file'))}"
    upload = s3.internal.create_multipart_upload(
        Bucket=s3.UPLOAD_BUCKET,
        Key=key,
        ContentType=body.get("content_type") or "application/octet-stream",
    )
    upload_id = upload["UploadId"]
    part_count = max(1, math.ceil(size / s3.PART_SIZE))
    parts = [
        {
            "part_number": n,
            "url": s3.files.generate_presigned_url(
                "upload_part",
                Params={"Bucket": s3.UPLOAD_BUCKET, "Key": key, "UploadId": upload_id, "PartNumber": n},
                ExpiresIn=s3.PART_TTL,
            ),
        }
        for n in range(1, part_count + 1)
    ]
    return {"key": key, "upload_id": upload_id, "part_size": s3.PART_SIZE, "parts": parts}


def complete_upload(body: dict) -> dict:
    parts = sorted(body["parts"], key=lambda p: p["part_number"])
    s3.internal.complete_multipart_upload(
        Bucket=s3.UPLOAD_BUCKET,
        Key=body["key"],
        UploadId=body["upload_id"],
        MultipartUpload={"Parts": [{"PartNumber": p["part_number"], "ETag": p["etag"]} for p in parts]},
    )
    head = s3.internal.head_object(Bucket=s3.UPLOAD_BUCKET, Key=body["key"])
    url = s3.files.generate_presigned_url(
        "get_object", Params={"Bucket": s3.UPLOAD_BUCKET, "Key": body["key"]}, ExpiresIn=s3.GET_TTL
    )
    return {"size": head["ContentLength"], "etag": head["ETag"], "download_url": url}


def abort_upload(body: dict) -> dict:
    s3.internal.abort_multipart_upload(Bucket=s3.UPLOAD_BUCKET, Key=body["key"], UploadId=body["upload_id"])
    return {"aborted": True}


def open_uploads(_: dict) -> dict:
    listing = s3.internal.list_multipart_uploads(Bucket=s3.UPLOAD_BUCKET)
    return {
        "uploads": [
            {"key": u["Key"], "upload_id": u["UploadId"], "initiated": u["Initiated"].isoformat()}
            for u in listing.get("Uploads", [])
        ]
    }


ROUTES = {
    ("POST", "/api/uploads"): create_upload,
    ("POST", "/api/uploads/complete"): complete_upload,
    ("POST", "/api/uploads/abort"): abort_upload,
    ("GET", "/api/uploads/open"): open_uploads,
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data).encode(), "application/json")

    def _dispatch(self, method: str) -> None:
        if method == "GET" and self.path in STATIC_FILES:
            name, content_type = STATIC_FILES[self.path]
            self._send(200, (STATIC / name).read_bytes(), content_type)
            return
        handler = ROUTES.get((method, self.path))
        if handler is None:
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        try:
            self._json(200, handler(body))
        except ClientError as e:
            self._json(502, {"error": str(e)})

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")


def main() -> None:
    s3.wait_ready()
    s3.ensure_buckets()
    for error in s3.apply_cors():
        print(f"bucket CORS not applied: {error}", flush=True)
    print("spike server on :8000 (open http://localhost:8080)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()


if __name__ == "__main__":
    main()
