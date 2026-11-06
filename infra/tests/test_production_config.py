"""What production would run (TRD §15, §16.2, §16.3; W20-12): the compose files for the production
host are rendered together and checked, with no stack running.

    docker compose -f compose.yml -f compose.prod.yml -f compose.production.yml \\
        -f compose.monitoring.yml -f compose.backup.yml -f compose.backup-host.yml config

It fails when production would publish a port to the world other than 80 and 443, run Mailpit or
a dev override, build an image on the host, run without virus scanning, leave a long-running
container without a memory limit or a restart policy.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1]
FILES = [
    "compose.yml", "compose.prod.yml", "compose.production.yml", "compose.monitoring.yml",
    "compose.backup.yml", "compose.backup-host.yml",
]
APP_SERVICES = ["auth", "operations", "media", "media-worker", "report", "report-worker", "platform"]
# What the host's .env adds to .env.example (T3 mail relay, the address, the certificates)
HOST_VALUES = {
    "MMS_ENVIRONMENT": "production", "MMS_REGISTRY": "ghcr.io/example/mms", "MMS_TAG": "abc123",
    "MMS_TLS_DIR": "/opt/mms/tls", "MMS_SECRETS_DIR": "./secrets",
    "PLATFORM_SMTP_HOST": "smtp.example.org", "PLATFORM_SMTP_PORT": "587",
    "PLATFORM_SMTP_SECURITY": "starttls", "PLATFORM_MAIL_FROM": "mms@example.org",
    "PLATFORM_SMTP_USERNAME": "user", "PLATFORM_SMTP_PASSWORD": "not-a-real-password",
    "BACKUP_AGE_RECIPIENT": "age1example",
}


def docker() -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    found = shutil.which("docker")
    if found:
        return found
    candidate = Path(local) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe"
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def production(tmp_path_factory) -> dict:
    binary = docker()
    if binary is None:
        pytest.skip("docker is not installed")
    env_file = tmp_path_factory.mktemp("env") / ".env"
    example = (INFRA / ".env.example").read_text(encoding="utf-8")
    env_file.write_text(
        example + "\n" + "\n".join(f"{k}={v}" for k, v in HOST_VALUES.items()) + "\n", encoding="utf-8"
    )
    command = [binary, "compose", "--env-file", str(env_file)]
    for name in FILES:
        command += ["-f", name]
    result = subprocess.run(
        [*command, "config", "--format", "json"], cwd=INFRA, capture_output=True, text=True,
        check=False, timeout=120, env={**os.environ, "MSYS_NO_PATHCONV": "1"},
    )
    assert result.returncode == 0, result.stderr[-800:]
    return json.loads(result.stdout)


def services(production: dict) -> dict[str, dict]:
    return production["services"]


def test_only_nginx_listens_on_the_network(production):
    for name, service in services(production).items():
        for port in service.get("ports", []):
            if name == "nginx":
                assert str(port["published"]) in ("80", "443"), (name, port)
            else:
                # Grafana, Prometheus and Alertmanager: the host itself, for an SSH tunnel (W20-3)
                assert port.get("host_ip") == "127.0.0.1", (name, port)


def test_no_mailpit_and_no_development_override(production):
    names = set(services(production))
    assert "mailpit" not in names
    assert not {"dev-certs", "dev-secrets"} & names, "the self-signed and generated secrets are dev only"


def test_nothing_is_built_on_the_host_except_the_backup_image(production):
    built = {name for name, service in services(production).items() if "build" in service}
    assert built <= {"backup"}, built


def test_the_application_runs_the_tagged_images_in_production(production):
    for name in APP_SERVICES:
        service = services(production)[name]
        assert re.fullmatch(r"ghcr\.io/example/mms/(auth|operations|media|report|platform):abc123", service["image"]), name
        env = service["environment"]
        prefix = {"auth": "AUTH", "operations": "OPS", "media": "MEDIA", "media-worker": "MEDIA",
                  "report": "REPORT", "report-worker": "REPORT", "platform": "PLATFORM"}[name]
        assert env[f"{prefix}_ENVIRONMENT"] == "production", name
    assert services(production)["nginx"]["image"] == "ghcr.io/example/mms/web:abc123"


def test_virus_scanning_is_on_and_clamav_runs(production):
    for name in ("media", "media-worker"):
        assert services(production)[name]["environment"]["MEDIA_SCAN_MODE"] == "clamd"
    assert "clamav" in services(production)
    assert not services(production)["clamav"].get("profiles"), "ClamAV must not be optional here"


def test_every_long_running_container_has_a_memory_limit_and_restarts(production):
    for name, service in services(production).items():
        if service.get("restart") == "no":
            continue  # the one-shot init containers
        assert service.get("mem_limit"), f"{name} has no memory limit"
        assert service.get("restart") == "unless-stopped", name


def test_the_memory_budget_fits_the_host(production):
    """TRD §16.2: about 18.5 GB on a 32 GB host; leave at least a third for the system and cache."""
    total = sum(
        int(service["mem_limit"]) for service in services(production).values() if service.get("mem_limit")
    )
    assert total <= 21 * 1024**3, f"{total / 1024**3:.1f} GB of limits"


def test_the_mail_is_not_the_development_mailbox(production):
    env = services(production)["platform"]["environment"]
    assert env["PLATFORM_SMTP_HOST"] == "smtp.example.org"

