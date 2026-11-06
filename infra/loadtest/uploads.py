"""Many phones uploading a video at once (PRD NFR-1; TRD §3.3, R7, R8; W20 slice 6).

    infra/loadtest/make_video.sh 100                     # a real MP4 of about 100 MiB at out/video.mp4
    cd infra/loadtest
    LOAD_CONNECT=127.0.0.1 locust -f locustfile.py,uploads.py --headless -u 70 -r 2 -t 30m --csv out/run

Twenty uploaders (LOAD_UPLOADERS) each start a visit of their own, put a task on its board and
send the file the way the app does: a presigned multipart upload straight to the files host in 8 MiB
parts, then `complete`. Each then waits for the media worker's checks and the processed copy, which is
what the worker's memory and time are judged on. Every uploader sends one file and stops, so the
number of uploads in flight is the number of uploaders at the start.

    LOAD_UPLOADERS    how many at once, default 20
    UPLOAD_FILE       the video, default out/video.mp4
"""

from __future__ import annotations

import hashlib
import os
import random
import time
from pathlib import Path
from typing import Any, ClassVar

import gevent
from base import Site, record
from common import files_url, uuid7
from locust import constant, task
from locust.exception import StopUser

UPLOADERS = int(os.environ.get("LOAD_UPLOADERS", "20"))
VIDEO = Path(os.environ.get("UPLOAD_FILE", "out/video.mp4"))
PART_SIZE = 8 * 1024 * 1024
# Videos are processed one at a time (R7, R8), so the last of many waits for all the others: allow
# about two and a half minutes for each uploader (a 96 MiB video took about 2 minutes on a laptop)
PROCESS_LIMIT_S = int(
    os.environ.get("LOAD_PROCESS_LIMIT_S", str(max(900, 150 * UPLOADERS)))
)

_digest: dict[str, str] = {}


def video_sha256() -> str:
    """Hashed once for all uploaders: the file is the same for every one."""
    if "sha" not in _digest:
        h = hashlib.sha256()
        with VIDEO.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        _digest["sha"] = h.hexdigest()
    return _digest["sha"]


class VideoUploader(Site):
    fixed_count = UPLOADERS
    wait_time = constant(1)
    taken: ClassVar[dict[str, int]] = {}  # visits handed out so far, by seed user

    def pick(self) -> str:
        return random.choice(["tech1", "tech2"])

    def setup(self) -> None:
        if not VIDEO.exists():
            raise RuntimeError(
                f"{VIDEO} is missing: run infra/loadtest/make_video.sh first"
            )
        self.visit: dict[str, Any] | None = None
        self.element = uuid7()
        me = (self.get("/api/v1/auth/me", name="GET /auth/me") or {}).get("id")
        mine = (
            self.get(
                "/api/v1/visits/mine", name="GET /visits/mine", params={"limit": 100}
            )
            or {}
        ).get("items", [])
        planned = sorted(
            (
                v
                for v in mine
                if v.get("status") == "planned"
                and v["stations"][0]["owner"]["id"] == me
            ),
            key=lambda v: v["id"],
        )
        # The uploaders take their visits from the other end of the list, so they never meet a technician of locustfile.py
        index = VideoUploader.taken.get(self.who, 0)
        VideoUploader.taken[self.who] = index + 1
        if index >= len(planned):
            return
        self.visit = planned[-1 - index]
        self.station = self.visit["stations"][0]["station_id"]
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.sync(
            [
                self.op("visit.start", {"at": at}),
                self.op("station.arrive", {"station_id": self.station, "at": at}),
                self.op(
                    "element.create",
                    {
                        "station_id": self.station,
                        "id": self.element,
                        "kind": "task",
                        "title": "Video",
                        "items": [],
                        "shared": False,
                    },
                ),
            ]
        )

    def op(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.visit
        return {
            "op_id": uuid7(),
            "v": 1,
            "type": kind,
            "visit_id": self.visit["id"],
            "payload": payload,
        }

    def sync(self, ops: list[dict[str, Any]]) -> None:
        self.post(
            "/api/v1/sync",
            {"device_id": f"load-{self.element[:13]}", "ops": ops},
            name="POST /sync (ops)",
        )

    @task
    def upload_one(self) -> None:
        if not self.visit:
            record(
                "upload: no visit to attach to",
                time.time(),
                "the seed has too few planned visits",
                "UPLOAD",
            )
            raise StopUser
        started = time.time()
        size = VIDEO.stat().st_size
        media_id = uuid7()
        owner = f"visit:{self.visit['id']}:station:{self.station}:element:{self.element}:before"
        upload = self.post(
            "/api/v1/uploads",
            {
                "media_id": media_id,
                "owner_ref": owner,
                "kind": "video",
                "filename": "load.mp4",
                "size_bytes": size,
                "sha256": video_sha256(),
            },
            name="POST /uploads",
        )
        if not upload:
            record("video upload", started, "could not start", "UPLOAD")
            raise StopUser

        with VIDEO.open("rb") as handle:
            for item in sorted(upload["urls"], key=lambda u: u["part_number"]):
                chunk = handle.read(upload["part_size"])
                url, headers = files_url(item["url"])
                with self.client.put(
                    url,
                    data=chunk,
                    headers=headers,
                    name="PUT video part",
                    catch_response=True,
                ) as r:
                    if r.status_code != 200:
                        r.failure(f"{r.status_code}")
                        record(
                            "video upload",
                            started,
                            f"part {item['part_number']} {r.status_code}",
                            "UPLOAD",
                        )
                        raise StopUser
        done = self.post(
            f"/api/v1/uploads/{media_id}/complete",
            {},
            name="POST /uploads/{id}/complete",
        )
        if done is None:
            record("video upload", started, "complete failed", "UPLOAD")
            raise StopUser
        record("video upload", started, request_type="UPLOAD")

        waited = time.time()
        while time.time() - waited < PROCESS_LIMIT_S:
            gevent.sleep(5)
            media = self.get(f"/api/v1/media/{media_id}", name="GET /media/{id}")
            status = (media or {}).get("status")
            if status == "ready":
                record("video processed", waited, request_type="UPLOAD")
                raise StopUser
            if status in ("failed", "deleted"):
                record(
                    "video processed",
                    waited,
                    f"status {status}: {(media or {}).get('error')}",
                    "UPLOAD",
                )
                raise StopUser
        record("video processed", waited, f"not ready in {PROCESS_LIMIT_S} s", "UPLOAD")
        raise StopUser
