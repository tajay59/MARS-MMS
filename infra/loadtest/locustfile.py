"""The load mix (PRD NFR-1, NFR-2; TRD §17; W20 slice 6): what 50 people do in an ordinary hour,
through the gateway, as the seed users.

    cd infra/loadtest
    LOAD_CONNECT=127.0.0.1 locust -f locustfile.py --headless -u 50 -r 2 -t 1h --csv out/soak

    clients    (half the users)  browse stations, open requests, read and write comments
    staff      (a fifth)         dashboards, the queue, filters, and now and then a summary report
    technicians (the rest)       their visits, and every minute a sync of 20 operations

Each virtual user signs in once, refreshes its own token before it expires, and keeps going. The
gateway allows ten sign-ins a minute per address, so the ramp is slow on purpose: 50 users take
about five minutes to arrive. See README.md for the thresholds and how the numbers are judged.
"""

from __future__ import annotations

import random
import time
from typing import Any, ClassVar

import gevent
from base import Site, record
from common import uuid7
from locust import between, task


class Client(Site):
    """A client organization's staff member: browse and follow."""

    weight = 5

    def pick(self) -> str:
        return random.choice(["client_a1", "client_a2", "client_b1"])

    def setup(self) -> None:
        self.station_ids: list[str] = []
        self.request_ids: list[str] = []

    @task(5)
    def stations(self) -> None:
        page = self.get("/api/v1/stations", name="GET /stations", params={"limit": 50})
        if page:
            self.station_ids = [s["id"] for s in page["items"]]

    @task(3)
    def a_station(self) -> None:
        if self.station_ids:
            self.get(
                f"/api/v1/stations/{random.choice(self.station_ids)}",
                name="GET /stations/{id}",
            )

    @task(4)
    def requests(self) -> None:
        page = self.get("/api/v1/requests", name="GET /requests", params={"limit": 50})
        if page:
            self.request_ids = [r["id"] for r in page["items"]]

    @task(4)
    def a_request(self) -> None:
        if not self.request_ids:
            return
        rid = random.choice(self.request_ids)
        self.get(f"/api/v1/requests/{rid}", name="GET /requests/{id}")
        self.get(f"/api/v1/requests/{rid}/comments", name="GET /requests/{id}/comments")

    @task(2)
    def dashboard(self) -> None:
        self.get("/api/v1/dashboard", name="GET /dashboard")

    @task(1)
    def comment(self) -> None:
        if self.request_ids:
            rid = random.choice(self.request_ids)
            self.post(
                f"/api/v1/requests/{rid}/comments",
                {"id": uuid7(), "body": "Load test note."},
                name="POST /requests/{id}/comments",
            )


class Staff(Site):
    """An administrator or a viewer: dashboards, queues and the odd report."""

    weight = 2

    def pick(self) -> str:
        return random.choice(["admin", "admin", "viewer"])

    def setup(self) -> None:
        self.request_ids: list[str] = []
        self.summary_type = None
        if self.who == "admin":
            types = (
                self.get(
                    "/api/v1/reports/summary/types", name="GET /reports/summary/types"
                )
                or []
            )
            names = [t["type"] for t in types]
            # network_status needs no period, so every run asks for the same work
            self.summary_type = (
                "network_status"
                if "network_status" in names
                else (names[0] if names else None)
            )

    @task(4)
    def dashboard(self) -> None:
        self.get("/api/v1/dashboard", name="GET /dashboard")

    @task(4)
    def requests(self) -> None:
        page = self.get("/api/v1/requests", name="GET /requests", params={"limit": 50})
        if page:
            self.request_ids = [r["id"] for r in page["items"]]

    @task(3)
    def queue(self) -> None:
        self.get("/api/v1/queue", name="GET /queue")

    @task(3)
    def stations(self) -> None:
        self.get(
            "/api/v1/stations", name="GET /stations", params={"limit": 50, "q": "LT-0"}
        )
        self.get("/api/v1/stations/facets", name="GET /stations/facets")

    @task(3)
    def a_request(self) -> None:
        if self.request_ids:
            self.get(
                f"/api/v1/requests/{random.choice(self.request_ids)}",
                name="GET /requests/{id}",
            )

    @task(1)
    def summary_report(self) -> None:
        """Ask for a report and wait for it: ready within two minutes (plan decision 11)."""
        if self.who != "admin" or not self.summary_type:
            return
        started = time.time()
        job = self.post(
            "/api/v1/reports/summary",
            {"type": self.summary_type, "format": "csv"},
            name="POST /reports/summary",
        )
        if not job or "id" not in job:
            record("summary ready", started, "no job", "REPORT")
            return
        while time.time() - started < 150:
            gevent.sleep(3)
            state = self.get(
                f"/api/v1/reports/summary/jobs/{job['id']}",
                name="GET /reports/summary/jobs/{id}",
            )
            if state and state.get("status") in ("ready", "done", "complete"):
                record("summary ready", started, request_type="REPORT")
                return
            if state and state.get("status") in ("failed", "error"):
                record("summary ready", started, "failed", "REPORT")
                return
        record("summary ready", started, "not ready in 150 s", "REPORT")


class Technician(Site):
    """A technician on a visit: a sync of 20 operations about every minute."""

    weight = 3
    wait_time = between(20, 60)
    taken: ClassVar[dict[str, int]] = {}  # visits handed out so far, by seed user

    def pick(self) -> str:
        return random.choice(["tech1", "tech2"])

    def setup(self) -> None:
        self.visit: dict[str, Any] | None = None
        self.created: list[str] = []
        self.device = f"load-{uuid7()[:13]}"
        mine = self.get(
            "/api/v1/visits/mine", name="GET /visits/mine", params={"limit": 100}
        )
        items = (mine or {}).get("items", [])
        me = (self.get("/api/v1/auth/me", name="GET /auth/me") or {}).get("id")
        # Planned, and the first station is this technician's to write (an owner is one person)
        planned = sorted(
            (
                v
                for v in items
                if v.get("status") == "planned"
                and v["stations"][0]["owner"]["id"] == me
            ),
            key=lambda v: v["id"],
        )
        # Each virtual technician takes a visit of its own (the next one not taken by another)
        index = Technician.taken.get(self.who, 0)
        Technician.taken[self.who] = index + 1
        if index < len(planned):
            self.visit = planned[index]
            self.sync([self.op("visit.start", {"at": self.now()})])
            self.sync(
                [
                    self.op(
                        "station.arrive",
                        {"station_id": self.station(), "at": self.now()},
                    )
                ]
            )

    @staticmethod
    def now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def station(self) -> str:
        assert self.visit
        return self.visit["stations"][0]["station_id"]

    def op(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.visit
        return {
            "op_id": uuid7(),
            "v": 1,
            "type": kind,
            "visit_id": self.visit["id"],
            "payload": payload,
        }

    def sync(self, ops: list[dict[str, Any]]) -> Any:
        with self.client.post(
            "/api/v1/sync",
            json={"device_id": self.device, "ops": ops},
            headers=self.fresh(),
            name="POST /sync (ops)",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")
                return None
            results = r.json().get("answers", [])
            bad = [
                x
                for x in results
                if x.get("status") not in ("applied", "duplicate", "skipped")
            ]
            if bad:
                r.failure(
                    f"{len(bad)} of {len(ops)} ops: {bad[0].get('status')} {bad[0].get('code') or ''}"
                )
            return results

    @task(6)
    def sync_twenty(self) -> None:
        """Ten notes created and the ten from last time deleted: twenty ops, a steady board."""
        if not self.visit:
            return
        ops = []
        for old in self.created:
            ops.append(
                self.op(
                    "element.delete",
                    {
                        "station_id": self.station(),
                        "element_id": old,
                        "base_version": 1,
                    },
                )
            )
        self.created = []
        while len(ops) < 20:
            eid = uuid7()
            self.created.append(eid)
            ops.append(
                self.op(
                    "element.create",
                    {
                        "station_id": self.station(),
                        "id": eid,
                        "kind": "note",
                        "title": "Load test note",
                        "description": "Written by the load test.",
                        "items": [],
                        "shared": False,
                    },
                )
            )
        self.sync(ops)

    @task(3)
    def my_visits(self) -> None:
        self.get("/api/v1/visits/mine", name="GET /visits/mine", params={"limit": 100})

    @task(2)
    def a_visit(self) -> None:
        if self.visit:
            self.get(f"/api/v1/visits/{self.visit['id']}", name="GET /visits/{id}")

    @task(2)
    def dashboard(self) -> None:
        self.get("/api/v1/dashboard", name="GET /dashboard")
