"""The rollback guard (W20-12): going back over a migration or an event change is refused, a plain
rollback and a new release are allowed. Runs in a throwaway git repository; needs only git and bash."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rollback-guard.sh"
BASH = shutil.which("bash")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(not (BASH and GIT), reason="needs git and bash")


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def commit(repo: Path, name: str, files: dict[str, str]) -> str:
    for path, text in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")
    run(repo, GIT, "add", "-A")
    done = run(repo, GIT, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", name)
    assert done.returncode == 0, done.stderr
    return run(repo, GIT, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def history(tmp_path):
    run(tmp_path, GIT, "init", "-q", "-b", "main")
    a = commit(tmp_path, "a", {"README": "1"})
    b = commit(tmp_path, "b: code only", {"services/auth/app/main.py": "x = 1"})
    c = commit(tmp_path, "c: a migration", {"services/auth/app/migrations/0009_x.py": "pass"})
    d = commit(tmp_path, "d: an event field", {"libs/mms_common/mms_common/events/auth.py": "y = 1"})
    e = commit(tmp_path, "e: docs only", {"docs/x.md": "z"})
    run(tmp_path, GIT, "checkout", "-q", "-b", "other", a)
    other = commit(tmp_path, "other line", {"other.txt": "1"})
    return {"repo": tmp_path, "a": a, "b": b, "c": c, "d": d, "e": e, "other": other}


def guard(history: dict, target: str, deployed: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return run(history["repo"], BASH, str(SCRIPT), history[target], history[deployed], *extra)


def test_a_new_release_is_allowed(history):
    result = guard(history, "e", "a")
    assert result.returncode == 0 and "newer release" in result.stdout


def test_the_same_release_is_allowed(history):
    assert guard(history, "b", "b").returncode == 0


def test_a_rollback_over_code_only_is_allowed(history):
    result = guard(history, "a", "b")
    assert result.returncode == 0 and "safe to go back" in result.stdout


def test_a_rollback_over_a_migration_is_refused(history):
    result = guard(history, "b", "c")
    assert result.returncode == 1
    assert "0009_x.py" in result.stderr and "--allow-older-schema" in result.stderr


def test_a_rollback_over_an_event_schema_change_is_refused(history):
    result = guard(history, "c", "d")
    assert result.returncode == 1 and "events/auth.py" in result.stderr


def test_a_rollback_over_docs_after_a_migration_still_notices_the_migration(history):
    assert guard(history, "b", "e").returncode == 1


def test_the_operator_can_allow_it_after_checking(history):
    result = guard(history, "b", "c", "--allow-older-schema")
    assert result.returncode == 0 and "going back anyway" in result.stdout


def test_another_line_of_history_is_refused(history):
    assert guard(history, "other", "e").returncode == 1


@pytest.fixture
def mongo_history(tmp_path):
    run(tmp_path, GIT, "init", "-q", "-b", "main")
    old = commit(tmp_path, "old image", {"infra/compose.yml": "  mongo:\n    image: mongo:8.0.34\n"})
    code = commit(tmp_path, "code only", {"services/auth/app/main.py": "x = 1"})
    new = commit(tmp_path, "new image", {"infra/compose.yml": "  mongo:\n    image: mongo:9.0.8\n"})
    later = commit(tmp_path, "docs only", {"docs/x.md": "z"})
    return {"repo": tmp_path, "old": old, "code": code, "new": new, "later": later}


def test_a_rollback_over_a_mongodb_image_change_is_refused(mongo_history):
    result = guard(mongo_history, "code", "later")
    assert result.returncode == 1
    assert "MongoDB image" in result.stderr and "--allow-older-schema" in result.stderr


def test_a_rollback_that_keeps_the_mongodb_image_is_allowed(mongo_history):
    result = guard(mongo_history, "new", "later")
    assert result.returncode == 0 and "safe to go back" in result.stdout


def test_the_operator_can_go_back_over_a_mongodb_image_change(mongo_history):
    result = guard(mongo_history, "code", "later", "--allow-older-schema")
    assert result.returncode == 0 and "going back anyway" in result.stdout


def test_an_unknown_commit_is_a_usage_error(history):
    result = run(history["repo"], BASH, str(SCRIPT), "0" * 40, history["a"])
    assert result.returncode == 2
