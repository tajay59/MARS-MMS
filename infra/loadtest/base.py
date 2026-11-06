"""What both Locust files share: a virtual user that signs in once, keeps its token fresh and
measures every call (W20 slice 6). Not a scenario by itself (`abstract`)."""

from __future__ import annotations

import time
from typing import Any

import gevent
from common import EMAILS, PASSWORD, base_url, host_header
from locust import HttpUser, between, events

TOKEN_LIFETIME_S = 12 * 60  # access tokens last 15 minutes; refresh a little early


def record(
    name: str, started: float, error: str | None = None, request_type: str = "STEP"
) -> None:
    """A measurement of our own (a summary report ready) in the same statistics."""
    events.request.fire(
        request_type=request_type,
        name=name,
        response_time=(time.time() - started) * 1000,
        response_length=0,
        exception=Exception(error) if error else None,
        context={},
    )


class Site(HttpUser):
    abstract = True
    host = base_url()
    who = "client_a1"
    wait_time = between(5, 15)  # a click every ten seconds or so

    def pick(self) -> str:
        """Which seed user this virtual user is. Chosen before it signs in."""
        return self.who

    def on_start(self) -> None:
        self.client.verify = False
        self.client.headers.update(host_header())
        self.token = ""
        self.token_at = 0.0
        self.who = self.pick()
        self.login()
        self.setup()

    def setup(self) -> None:
        """What a user knows before it starts: ids to open."""

    # --- signing in -----------------------------------------------------------------------

    def login(self) -> None:
        for attempt in range(60):
            with self.client.post(
                "/api/v1/auth/login",
                json={"email": EMAILS[self.who], "password": PASSWORD},
                name="POST /auth/login",
                catch_response=True,
            ) as r:
                if r.status_code == 429:  # ten a minute per address: wait and try again
                    r.success()
                    gevent.sleep(6 + attempt % 4)
                    continue
                if r.status_code != 200:
                    r.failure(f"login {r.status_code}")
                    gevent.sleep(5)
                    continue
                self.token = r.json()["access_token"]
                self.token_at = time.time()
                return
        raise RuntimeError(f"{self.who} could not sign in")

    def fresh(self) -> dict[str, str]:
        if time.time() - self.token_at > TOKEN_LIFETIME_S:
            with self.client.post(
                "/api/v1/auth/refresh", name="POST /auth/refresh", catch_response=True
            ) as r:
                if r.status_code == 200:
                    self.token = r.json()["access_token"]
                    self.token_at = time.time()
                else:
                    r.success()  # the cookie was lost: sign in again
                    self.login()
        return {"Authorization": f"Bearer {self.token}"}

    # --- calls ----------------------------------------------------------------------------

    def get(self, path: str, name: str | None = None, **kw: Any) -> Any:
        with self.client.get(
            path,
            headers=self.fresh(),
            name=name or f"GET {path}",
            catch_response=True,
            **kw,
        ) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")
                return None
            return r.json()

    def post(self, path: str, body: dict[str, Any], name: str | None = None) -> Any:
        with self.client.post(
            path,
            json=body,
            headers=self.fresh(),
            name=name or f"POST {path}",
            catch_response=True,
        ) as r:
            if r.status_code not in (200, 201, 202):
                r.failure(f"{r.status_code}")
                return None
            return r.json() if r.content else {}
