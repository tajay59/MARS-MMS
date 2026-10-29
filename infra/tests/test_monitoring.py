"""Checks against the running monitoring stack (W20-2 to W20-4; TRD §16.5, TP "alert firing"):
every target is scraped, every rule is loaded, the dashboards' queries return data, Grafana has
its five dashboards, container logs reach Loki, and each alert reaches the admins' mailbox.

    cd infra && docker compose -f compose.yml -f compose.dev.yml -f compose.monitoring.yml up -d
    ../.venv/Scripts/python -m pytest tests/test_monitoring.py -q

Skipped when Prometheus is not answering on 127.0.0.1.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

INFRA = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    values: dict[str, str] = {}
    path = INFRA / ".env"
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


ENV = _env()
PROMETHEUS = f"http://127.0.0.1:{ENV.get('PROMETHEUS_PORT', '9090')}"
ALERTMANAGER = f"http://127.0.0.1:{ENV.get('ALERTMANAGER_PORT', '9093')}"
GRAFANA = f"http://127.0.0.1:{ENV.get('GRAFANA_PORT', '3001')}"
MAILPIT = "http://127.0.0.1:8025"
GRAFANA_AUTH = ("admin", ENV.get("GRAFANA_ADMIN_PASSWORD", "dev-grafana-password"))


def _up() -> bool:
    try:
        return httpx.get(f"{PROMETHEUS}/-/ready", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="the monitoring stack is not running")


def wait_for(check: Callable[[], Any], seconds: float = 90, step: float = 3) -> Any:
    deadline = time.monotonic() + seconds
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = check()
            if last:
                return last
        except httpx.HTTPError:
            pass
        time.sleep(step)
    raise AssertionError(f"not true after {seconds} s (last: {last!r})")


def query(expr: str) -> list[dict[str, Any]]:
    r = httpx.get(f"{PROMETHEUS}/api/v1/query", params={"query": expr}, timeout=10)
    r.raise_for_status()
    result: list[dict[str, Any]] = r.json()["data"]["result"]
    return result


def test_every_target_is_scraped_and_up():
    def all_up() -> bool:
        targets = httpx.get(f"{PROMETHEUS}/api/v1/targets", timeout=10).json()["data"]["activeTargets"]
        return len(targets) >= 13 and all(t["health"] == "up" for t in targets)

    wait_for(all_up)


def test_every_rule_of_the_repository_is_loaded():
    expected = {
        r["alert"]
        for g in yaml.safe_load((INFRA / "monitoring/rules/mms.yml").read_text(encoding="utf-8"))["groups"]
        for r in g["rules"]
    }
    groups = httpx.get(f"{PROMETHEUS}/api/v1/rules", timeout=10).json()["data"]["groups"]
    loaded = {r["name"] for g in groups for r in g["rules"]}
    assert loaded == expected
    health = {r["health"] for g in groups for r in g["rules"]}
    assert health == {"ok"}  # none fails to evaluate


def test_prometheus_sends_to_alertmanager():
    found = httpx.get(f"{PROMETHEUS}/api/v1/alertmanagers", timeout=10).json()["data"]["activeAlertmanagers"]
    assert len(found) == 1


@pytest.mark.parametrize("expr", [
    "http_requests_total",                          # every service
    "outbox_leader == 1",                            # a relay holds its lease
    "outbox_oldest_unpublished_seconds",
    "consumer_backlog_messages",
    "job_queue_depth",
    "kafka_topic_partition_current_offset{topic=~'mms\\\\.dlq\\\\..+'}",  # DeadLetterNotEmpty
    "mongodb_ss_connections{conn_type='current'}",
    "redis_memory_used_bytes",
    "nginx_http_requests_total",
    "node_filesystem_size_bytes",                   # DiskAlmostFull
])
def test_the_queries_of_the_rules_and_dashboards_return_data(expr):
    wait_for(lambda: query(expr), seconds=60)


def test_the_dead_letter_topics_are_all_visible_and_the_alert_agrees_with_them():
    series = wait_for(lambda: query(
        "kafka_topic_partition_current_offset{topic=~'mms\\\\.dlq\\\\..+'}"
    ))
    topics = {s["metric"]["topic"] for s in series}
    assert {"mms.dlq.audit", "mms.dlq.notification", "mms.dlq.operations", "mms.dlq.media",
            "mms.dlq.report"} <= topics

    # The alert is firing for exactly the topics that hold something (a fresh stack: none).
    def agrees() -> bool:
        holding = {
            s["metric"]["topic"]
            for s in query(
                "sum by (topic) (kafka_topic_partition_current_offset{topic=~'mms\\\\.dlq\\\\..+'}"
                " - kafka_topic_partition_oldest_offset{topic=~'mms\\\\.dlq\\\\..+'}) > 0"
            )
        }
        firing = {
            s["metric"]["topic"]
            for s in query("ALERTS{alertname='DeadLetterNotEmpty', alertstate='firing'}")
        }
        return holding == firing

    wait_for(agrees, seconds=150)


def test_grafana_has_its_dashboards_and_both_data_sources():
    found = httpx.get(f"{GRAFANA}/api/search", params={"tag": "mms"}, auth=GRAFANA_AUTH, timeout=10).json()
    assert {d["uid"] for d in found} == {"mms-api", "mms-events", "mms-jobs", "mms-sync", "mms-host"}
    for uid in ("prometheus", "loki"):
        r = httpx.get(f"{GRAFANA}/api/datasources/uid/{uid}/health", auth=GRAFANA_AUTH, timeout=15)
        assert r.status_code == 200, (uid, r.text)


def test_grafana_wants_a_login():
    assert httpx.get(f"{GRAFANA}/api/search", timeout=10).status_code == 401


def test_container_logs_reach_loki_with_service_and_level_labels():
    def lines() -> bool:
        r = httpx.get(
            f"{GRAFANA}/api/datasources/proxy/uid/loki/loki/api/v1/labels", auth=GRAFANA_AUTH, timeout=15
        )
        labels = set(r.json().get("data") or [])
        return {"service", "environment"} <= labels

    wait_for(lines, seconds=90)
    r = httpx.get(
        f"{GRAFANA}/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
        params={"query": '{service="operations"}', "limit": 1}, auth=GRAFANA_AUTH, timeout=15,
    )
    assert r.json()["data"]["result"], "no log line from operations"


def test_every_alert_reaches_the_admins_mailbox():
    """The email half of the drill: each rule's alert, posted as Prometheus would send it, is
    grouped, rendered and delivered (promtool tests cover when each one fires)."""
    names = [
        r["alert"]
        for g in yaml.safe_load((INFRA / "monitoring/rules/mms.yml").read_text(encoding="utf-8"))["groups"]
        for r in g["rules"]
    ]
    # A new group each run: Alertmanager sends a given alert once in its repeat interval (4 hours)
    marker = uuid.uuid4().hex
    service = f"drill-{marker[:8]}"
    alerts = [
        {
            "labels": {"alertname": name, "service": service, "severity": "warning"},
            "annotations": {"summary": f"Drill {marker} for {name}", "description": "Not a real incident."},
        }
        for name in names
    ]
    r = httpx.post(f"{ALERTMANAGER}/api/v2/alerts", json=alerts, timeout=10)
    assert r.status_code == 200, r.text

    def delivered() -> bool:
        found = httpx.get(f"{MAILPIT}/api/v1/search", params={"query": marker, "limit": 50}, timeout=10).json()
        subjects = [m["Subject"] for m in found.get("messages", [])]
        return all(any(f"FIRING {n} ({service})" in s for s in subjects) for n in names)

    try:
        wait_for(delivered, seconds=60, step=2)
    finally:  # end the drill's alerts so the page is clean
        ended = datetime.now(UTC).isoformat()
        httpx.post(f"{ALERTMANAGER}/api/v2/alerts", json=[{**a, "endsAt": ended} for a in alerts], timeout=10)
    mail = httpx.get(f"{MAILPIT}/api/v1/search", params={"query": marker, "limit": 1}, timeout=10).json()["messages"][0]
    assert mail["Subject"].startswith("[MMS ")
    assert [a["Address"] for a in mail["To"]] == [ENV.get("MMS_ALERT_EMAILS", "admin@example.org")]
