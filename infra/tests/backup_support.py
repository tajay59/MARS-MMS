"""Helpers for the backup and restore tests (W20-6 to W20-8): run commands in the backup container,
make an age key pair, take a backup. Needs the local stack and compose.backup.yml
(+ compose.backup-host.yml for the replica):

    docker compose -f compose.yml -f compose.dev.yml -f compose.backup.yml -f compose.backup-host.yml up -d
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
FILES = ["-f", "compose.yml", "-f", "compose.dev.yml", "-f", "compose.backup.yml",
         "-f", "compose.backup-host.yml"]


def docker() -> str:
    local = os.environ.get("LOCALAPPDATA", "")
    return shutil.which("docker") or os.path.join(
        local, "Programs", "DockerDesktop", "resources", "bin", "docker.exe"
    )


def compose(*args: str, timeout: int = 600, extra_env: dict[str, str] | None = None
            ) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "MSYS_NO_PATHCONV": "1", **(extra_env or {})}
    return subprocess.run(
        [docker(), "compose", *FILES, *args], cwd=INFRA, capture_output=True, text=True,
        check=False, timeout=timeout, env=env,
    )


def in_backup(script: str, *, env: dict[str, str] | None = None, volumes: tuple[str, ...] = (),
              timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """A one-off container of the backup image running `script` with bash."""
    args = ["run", "--rm", "--no-deps", "-T"]
    for volume in volumes:
        args += ["-v", volume]
    for key, value in (env or {}).items():
        args += ["-e", f"{key}={value}"]
    return compose(*args, "--entrypoint", "bash", "backup", "-c", script, timeout=timeout)


def available() -> bool:
    return compose("ps", "--status", "running", "-q", "mongo", timeout=60).stdout.strip() != ""


def make_key(directory: Path) -> tuple[str, Path]:
    """(public key, private key file) from age-keygen inside the backup image."""
    result = compose("run", "--rm", "--no-deps", "-T", "--entrypoint", "age-keygen", "backup")
    assert result.returncode == 0, result.stderr[-400:]
    path = directory / "age-key.txt"
    path.write_text(result.stdout, encoding="utf-8")
    public = next(line.split()[-1] for line in result.stdout.splitlines()
                  if line.lower().startswith("# public key"))
    return public, path


def take_backup(public_key: str) -> str:
    """Runs `backup.sh mongo`; returns the new file's name."""
    before = set(list_backups())
    result = in_backup("/opt/backup/backup.sh mongo", env={"BACKUP_AGE_RECIPIENT": public_key})
    assert result.returncode == 0, result.stdout[-400:] + result.stderr[-400:]
    [new] = sorted(set(list_backups()) - before)
    return new


def list_backups() -> list[str]:
    out = in_backup("ls /backups/mongo 2>/dev/null | grep archive.age || true").stdout
    return [line.strip() for line in out.splitlines() if line.strip().startswith("mms-")]
