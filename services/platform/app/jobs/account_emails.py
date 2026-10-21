"""Send queued emails: account emails (NOT-3), the email that follows a notification (NOT-4)
and the weekly calibration digest (CAL-5).

Every platform instance runs the loop; claims in `email_queue` keep two senders off the same
row. For a reset or invitation the link is minted by auth at send time (TRD §6.2). A link auth
no longer issues (410: already used, user disabled, invitation accepted) skips the email.
Other failures retry with backoff, then give up with `status: failed` and an error log.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Literal, Protocol

import httpx
from mms_common.auth.service_client import ServiceTokens
from mms_common.logging import get_logger
from mms_common.time import Clock
from pymongo.asynchronous.database import AsyncDatabase

from app.domain import notification_emails, preferences
from app.domain.account_emails import LINK_KIND, EmailJob, Kind, Rendered, render, retry_at
from app.repo import digests, directory, emails
from app.repo import notifications as notification_repo
from app.repo import preferences as preference_repo

log = get_logger(__name__)

Security = Literal["none", "starttls", "ssl"]


class Mailer(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


@dataclass(frozen=True)
class SmtpMailer:
    """The organization's relay (T3) on staging and production, Mailpit locally."""

    host: str
    port: int
    security: Security = "none"
    username: str | None = None
    password: str | None = None
    timeout_s: float = 30.0

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send, message)

    def _send(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if self.security == "ssl":
            smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout_s, context=context)
        else:
            smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout_s)
        with smtp:
            if self.security == "starttls":
                smtp.starttls(context=context)
            if self.username:
                smtp.login(self.username, self.password or "")
            smtp.send_message(message)


class LinkGone(Exception):
    """auth answered 410: the reset or invitation can no longer be used."""


class Skipped(Exception):
    """An email that is no longer wanted: the person turned it off, left, or the notification
    it follows has expired. Recorded as skipped, never retried."""


@dataclass(frozen=True)
class Link:
    url: str
    email: str
    name: str


class LinkMinter(Protocol):
    async def mint(self, kind: str, link_id: str) -> Link: ...


class AuthLinks:
    """`POST /internal/account-links` on auth, with platform's service token (TRD §6.4)."""

    def __init__(self, auth_url: str, tokens: ServiceTokens, http: httpx.AsyncClient) -> None:
        self._url = auth_url.rstrip("/") + "/internal/account-links"
        self._tokens = tokens
        self._http = http

    async def mint(self, kind: str, link_id: str) -> Link:
        response = await self._http.post(
            self._url, json={"kind": kind, "id": link_id}, headers=await self._tokens.headers(),
            timeout=10,
        )
        if response.status_code == 410:
            raise LinkGone(kind)
        response.raise_for_status()
        body = response.json()
        return Link(url=str(body["url"]), email=str(body["email"]), name=str(body["name"]))


@dataclass(frozen=True)
class Sender:
    db: AsyncDatabase[dict[str, Any]]
    mailer: Mailer
    links: LinkMinter
    clock: Clock
    mail_from: str
    app_url: str

    async def send_due(self) -> int:
        """Send every due email; returns how many rows were handled."""
        handled = 0
        while (row := await emails.claim(self.db, self.clock.now())) is not None:
            await self._one(row)
            handled += 1
        return handled

    async def _one(self, row: dict[str, Any]) -> None:
        job = emails.to_job(row)
        now = self.clock.now
        try:
            message = await self._message(job, row["_id"])
            await self.mailer.send(message)
        except LinkGone:
            await emails.mark_skipped(self.db, row["_id"], now(), "link no longer valid")
            log.info("account_email_skipped", email_id=row["_id"], kind=job.kind)
            return
        except Skipped as skip:
            await emails.mark_skipped(self.db, row["_id"], now(), str(skip))
            log.info("email_skipped", email_id=row["_id"], kind=job.kind, why=str(skip))
            return
        except Exception as exc:  # noqa: BLE001 - SMTP, network or auth failure: retry later
            error = f"{type(exc).__name__}: {exc}"
            at = retry_at(int(row["attempts"]), now())
            if at is None:
                await emails.mark_failed(self.db, row["_id"], now(), error)
                log.error("account_email_failed", email_id=row["_id"], kind=job.kind, error=error)
            else:
                await emails.retry_later(self.db, row["_id"], at, error)
                log.warning("account_email_retry", email_id=row["_id"], kind=job.kind, error=error)
            return
        await emails.mark_sent(self.db, row["_id"], now())
        log.info("account_email_sent", email_id=row["_id"], kind=job.kind)

    async def _follow_up(self, job: EmailJob, email_id: str) -> EmailMessage:
        """The email for a notification or the digest, if the person still wants it (NOT-4)."""
        user = await directory.get(self.db, job.user_id)
        if user is None or user["status"] != "active":
            raise Skipped("not an active person")
        note = await notification_repo.col(self.db).find_one({"_id": job.notification_id})
        if note is None:
            raise Skipped("the notification has expired")
        choices = await preference_repo.email_choices(self.db, user["_id"])
        if not preferences.is_on(choices, note["type"], set(user["roles"])):
            raise Skipped("turned off")
        url = self.app_url.rstrip("/") + note["link"]
        rendered: Rendered
        if job.kind is Kind.DIGEST:
            run = await digests.get(self.db, job.digest_id or "")
            if run is None:
                raise Skipped("the digest is gone")
            local = self.clock.now()
            rendered = notification_emails.render_digest(
                name=user["name"], items=run["items"], within_days=run["within_days"], url=url,
                when=f"{local.day} {local:%b}",
            )
        else:
            rendered = notification_emails.render_notification(
                title=note["title"], body=note["body"], name=user["name"], url=url,
                button={"request": "Open the request", "visit": "View the visit"}.get(
                    note["entity"]["type"], "Open"),
            )
        return self._compose(rendered, user["email"], user["name"], email_id)

    def _compose(self, rendered: Rendered, to: str, name: str, email_id: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = rendered.subject
        message["From"] = self.mail_from
        message["To"] = formataddr((name, to))
        message["Message-ID"] = make_msgid(idstring=email_id.replace("-", ""))
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(rendered.text)
        message.add_alternative(rendered.html, subtype="html")
        return message

    async def _message(self, job: EmailJob, email_id: str) -> EmailMessage:
        if job.kind in (Kind.NOTIFICATION, Kind.DIGEST):
            return await self._follow_up(job, email_id)
        if job.kind in LINK_KIND:
            if job.link_id is None:
                raise LinkGone("no link id")
            link = await self.links.mint(LINK_KIND[job.kind], job.link_id)
            to, name, url = link.email, link.name, link.url
        else:
            to, name = job.to or "", job.name or ""
            url = self.app_url.rstrip("/") + "/login" if job.kind is Kind.APPROVED else ""
        rendered = render(job.kind, name=name, url=url or None, reason=job.reason)
        return self._compose(rendered, to, name, email_id)


async def run(sender: Sender, stop: asyncio.Event, every_s: float = 5.0) -> None:
    """Poll for due emails until `stop`."""
    while not stop.is_set():
        try:
            await sender.send_due()
        except Exception:  # noqa: BLE001 - Mongo unreachable: try again next round
            log.exception("account_email_loop_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=every_s)
        except TimeoutError:
            pass
