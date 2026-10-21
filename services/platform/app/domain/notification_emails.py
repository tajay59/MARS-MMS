"""The emails that follow notifications (PRD NOT-1, NOT-4, CAL-5, Appendix B; W9-13). No I/O.

Two kinds: one for a single notification (an assignment, a decision, a cancellation), and the
weekly calibration digest. Same single 600 px column as the account emails (DBD "PDF reports
and email"), the system font stack, one primary button. Every value that came from an event or
from the data is escaped in the HTML part and appears as plain text in the text part.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.account_emails import PRODUCT_LONG_NAME, PRODUCT_NAME, Rendered

_FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
_MONO = "ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace"
FOOTER = (
    "You can turn emails like this off under Email preferences in My profile. "
    "You will still see them in the app."
)
DIGEST_ROWS = 15  # rows per table in the email; the list in the app has the rest


def first_name(name: str) -> str:
    return name.split()[0] if name.split() else "there"


def _shell(title: str, inner: str) -> str:
    e = html.escape
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(title)}</title></head>"
        f'<body style="margin:0;padding:0;background:#F8FAFC;font-family:{_FONT}">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#F8FAFC"><tr><td align="center" style="padding:32px 16px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="width:100%;max-width:600px;background:#FFFFFF;border:1px solid #E2E8F0;'
        'border-radius:10px">'
        '<tr><td style="padding:24px 32px;border-bottom:1px solid #E2E8F0;font-size:18px;'
        f'line-height:24px;font-weight:600;color:#22569A">{PRODUCT_NAME}</td></tr>'
        f'<tr><td style="padding:32px">{inner}</td></tr>'
        '<tr><td style="padding:16px 32px;border-top:1px solid #E2E8F0;font-size:12px;'
        f'line-height:18px;color:#475569">{e(FOOTER)}<br>{e(PRODUCT_LONG_NAME)}</td></tr>'
        "</table></td></tr></table></body></html>"
    )


def _button(label: str, url: str) -> str:
    e = html.escape
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 8px">'
        '<tr><td style="border-radius:6px;background:#22569A">'
        f'<a href="{e(url, quote=True)}" style="display:inline-block;padding:12px 20px;'
        "font-size:16px;line-height:24px;font-weight:600;color:#FFFFFF;text-decoration:none;"
        f'border-radius:6px">{e(label)}</a></td></tr></table>'
    )


def _subject(title: str, body: str) -> str:
    text = f"{title}: {body}" if body else title
    return text if len(text) <= 120 else text[:117] + "..."


def render_notification(
    *, title: str, body: str, name: str, url: str, button: str = "Open the request"
) -> Rendered:
    """One notification as an email. The text is what the notification says; the button goes
    to what it is about."""
    e = html.escape
    greeting = f"Hello {first_name(name)},"
    text = "\n\n".join([greeting, title + ".", body, f"{button}: {url}", FOOTER,
                        f"{PRODUCT_NAME} · {PRODUCT_LONG_NAME}"]) + "\n"
    inner = (
        f'<p style="margin:0 0 16px;font-size:16px;line-height:24px;color:#0F172A">'
        f"{e(greeting)}</p>"
        f'<h1 style="margin:0 0 16px;font-size:20px;line-height:28px;font-weight:600;'
        f'color:#0F172A">{e(title)}</h1>'
        '<div style="margin:0 0 20px;padding:14px 16px;border-radius:8px;background:#F1F5F9;'
        f'font-size:16px;line-height:24px;color:#0F172A">{e(body)}</div>'
        f"{_button(button, url)}"
    )
    return Rendered(_subject(title, body), text, _shell(title, inner))


@dataclass(frozen=True)
class DigestCounts:
    overdue: int
    soon: int
    stations: int


def digest_counts(items: Sequence[Mapping[str, Any]]) -> DigestCounts:
    overdue = sum(1 for i in items if i["due_state"] == "overdue")
    stations = {i["station_code"] for i in items if i.get("station_code")}
    return DigestCounts(overdue=overdue, soon=len(items) - overdue, stations=len(stations))


def digest_title(counts: DigestCounts) -> str:
    total = counts.overdue + counts.soon
    if total == 1:
        return "1 sensor needs calibration"
    return f"{total} sensors need calibration"


def digest_body(counts: DigestCounts, within_days: int) -> str:
    parts = []
    if counts.overdue:
        parts.append(f"{counts.overdue} overdue")
    if counts.soon:
        parts.append(f"{counts.soon} due in the next {within_days} days")
    return ", ".join(parts)


def _rows(items: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], int]:
    shown = list(items[:DIGEST_ROWS])
    return shown, len(items) - len(shown)


def _table(heading: str, colour: str, items: Sequence[Mapping[str, Any]], date_title: str) -> str:
    if not items:
        return ""
    e = html.escape
    shown, more = _rows(items)
    rows = "".join(
        '<tr>'
        f'<td style="padding:8px 12px;border-top:1px solid #E2E8F0;font-family:{_MONO};'
        f'font-size:13px;color:#0F172A">{e(str(i.get("station_code") or "In stock"))}</td>'
        '<td style="padding:8px 12px;border-top:1px solid #E2E8F0;font-size:14px;'
        f'color:#0F172A">{e(str(i["model"]))} '
        f'<span style="font-family:{_MONO};font-size:12px;color:#475569">{e(str(i["serial"]))}'
        "</span></td>"
        f'<td style="padding:8px 12px;border-top:1px solid #E2E8F0;font-size:14px;'
        f'color:{colour};font-weight:600;white-space:nowrap">{e(str(i["due_label"]))}</td></tr>'
        for i in shown
    )
    tail = (
        f'<tr><td colspan="3" style="padding:8px 12px;border-top:1px solid #E2E8F0;'
        f'font-size:14px;color:#475569">and {more} more</td></tr>' if more else ""
    )
    return (
        f'<p style="margin:20px 0 8px;font-size:14px;font-weight:600;color:{colour}">'
        f"{e(heading)} ({len(items)})</p>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse"><tr>'
        '<th align="left" style="padding:8px 12px;background:#F1F5F9;font-size:12px;'
        'color:#475569">Station</th>'
        '<th align="left" style="padding:8px 12px;background:#F1F5F9;font-size:12px;'
        'color:#475569">Sensor</th>'
        f'<th align="left" style="padding:8px 12px;background:#F1F5F9;font-size:12px;'
        f'color:#475569">{e(date_title)}</th></tr>{rows}{tail}</table>'
    )


def render_digest(
    *, name: str, items: Sequence[Mapping[str, Any]], within_days: int, url: str, when: str
) -> Rendered:
    """The weekly digest (CAL-5): what is overdue, then what falls due soon. `items` carry
    `due_state`, `station_code`, `model`, `serial` and `due_label` (already a date in words)."""
    e = html.escape
    counts = digest_counts(items)
    title = digest_title(counts)
    overdue = [i for i in items if i["due_state"] == "overdue"]
    soon = [i for i in items if i["due_state"] != "overdue"]
    summary = (
        f"{digest_body(counts, within_days).replace(', ', ' and ')}"
        f", across {counts.stations} station{'s' if counts.stations != 1 else ''}."
    )
    lines = [f"Hello {first_name(name)},", title + ".", summary]
    for heading, group in (("Overdue", overdue), (f"Due in the next {within_days} days", soon)):
        if group:
            lines.append(f"{heading} ({len(group)})")
            shown, more = _rows(group)
            lines.extend(
                f"- {i.get('station_code') or 'In stock'}  {i['model']} {i['serial']}  "
                f"{i['due_label']}" for i in shown
            )
            if more:
                lines.append(f"  and {more} more")
    lines += [f"Open the calibration list: {url}", FOOTER, f"{PRODUCT_NAME} · {PRODUCT_LONG_NAME}"]
    inner = (
        f'<p style="margin:0 0 4px;font-size:12px;line-height:16px;color:#475569">'
        f"{e(when)} · Weekly digest</p>"
        f'<h1 style="margin:0 0 8px;font-size:24px;line-height:32px;font-weight:600;'
        f'color:#0F172A">{e(title)}</h1>'
        f'<p style="margin:0 0 8px;font-size:16px;line-height:24px;color:#475569">'
        f"{e(summary)}</p>"
        f"{_table('Overdue', '#991B1B', overdue, 'Was due')}"
        f"{_table(f'Due in the next {within_days} days', '#92400E', soon, 'Due')}"
        f'<div style="margin-top:24px">{_button("Open the calibration list", url)}</div>'
    )
    return Rendered(f"{title} · weekly digest", "\n".join(lines) + "\n", _shell(title, inner))
