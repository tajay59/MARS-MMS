"""Earlier releases' assets stay in the web image for 7 days after they are replaced (PWA
finding F9). Runs without the stack."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "carry_assets.py"
spec = importlib.util.spec_from_file_location("carry_assets", SCRIPT)
assert spec and spec.loader
carry_assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(carry_assets)

KEEP = timedelta(days=7)
T0 = datetime(2026, 10, 1, 12, tzinfo=UTC)


def build(root: Path, name: str, chunk: str) -> Path:
    dist = root / name
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / chunk).write_text(name, encoding="utf-8")
    (dist / "index.html").write_text(name, encoding="utf-8")
    return dist


def image(dist: Path, out: Path) -> Path:
    """What the Dockerfile does: the carried files, then dist over them."""
    html = dist.parent / f"{dist.name}-image"
    import shutil

    shutil.copytree(out, html)
    shutil.copytree(dist, html, dirs_exist_ok=True)
    return html


def test_first_release_carries_nothing(tmp_path):
    dist = build(tmp_path, "r1", "app-1.js")
    assert carry_assets.carry(None, dist, tmp_path / "out", "r1", KEEP, T0) == []
    manifest = json.loads((dist / ".releases" / "r1.json").read_text())
    assert manifest["files"] == ["assets/app-1.js"] and manifest["replaced_at"] is None


def test_previous_release_is_kept_then_dropped_a_week_after_it_was_replaced(tmp_path):
    r1 = build(tmp_path, "r1", "app-1.js")
    carry_assets.carry(None, r1, tmp_path / "o1", "r1", KEEP, T0)
    img1 = image(r1, tmp_path / "o1")

    # r2, ten days after r1 was built: r1 is replaced now, so it stays.
    r2 = build(tmp_path, "r2", "app-2.js")
    t2 = T0 + timedelta(days=10)
    assert carry_assets.carry(img1, r2, tmp_path / "o2", "r2", KEEP, t2) == ["r1"]
    img2 = image(r2, tmp_path / "o2")
    assert (img2 / "assets" / "app-1.js").is_file() and (img2 / "assets" / "app-2.js").is_file()
    r1_manifest = json.loads((img2 / ".releases" / "r1.json").read_text())
    assert r1_manifest["replaced_at"] == t2.isoformat(timespec="seconds")

    # r3 three days later: r1 (replaced 3 days ago) and r2 (replaced now) both stay.
    r3 = build(tmp_path, "r3", "app-3.js")
    assert sorted(carry_assets.carry(img2, r3, tmp_path / "o3", "r3", KEEP,
                                     t2 + timedelta(days=3))) == ["r1", "r2"]
    img3 = image(r3, tmp_path / "o3")

    # r4 eight days after r2: r1 was replaced 8 days ago and goes; r2 was replaced 5 ago.
    r4 = build(tmp_path, "r4", "app-4.js")
    assert sorted(carry_assets.carry(img3, r4, tmp_path / "o4", "r4", KEEP,
                                     t2 + timedelta(days=8))) == ["r2", "r3"]
    img4 = image(r4, tmp_path / "o4")
    assert not (img4 / "assets" / "app-1.js").exists()
    assert (img4 / "assets" / "app-2.js").is_file()
