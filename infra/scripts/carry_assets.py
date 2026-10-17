"""Keep earlier releases' hashed assets in the web image (PWA finding F9, TRD §2.1).

A tab or an installed app still running release N lazy-loads N's chunks after N+1 is
deployed. If the files are gone, routes fail. Each web image therefore carries the
`/assets/` files of every release replaced less than `--keep-days` ago.

Each release writes `.releases/<id>.json` = {"built_at", "replaced_at", "files"} beside
`index.html`. Building release N+1:

  1. read the manifests in the previous image's html directory (`--previous`, may be absent);
  2. mark the previous current release replaced now;
  3. copy into `--out` the files and manifests of every release replaced within the window;
  4. write N+1's own manifest into `--dist`.

The Dockerfile copies `--out` first and `dist` over it.

    python infra/scripts/carry_assets.py --previous prev-html --dist frontend/dist \
        --out infra/nginx/carry --release "$GITHUB_SHA"
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

RELEASES = ".releases"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def own_files(dist: Path) -> list[str]:
    assets = dist / "assets"
    return sorted(p.relative_to(dist).as_posix() for p in assets.rglob("*") if p.is_file())


def carry(previous: Path | None, dist: Path, out: Path, release: str, keep: timedelta,
          now: datetime) -> list[str]:
    """Returns the IDs of the earlier releases carried into `out`."""
    if out.exists():
        shutil.rmtree(out)
    (out / RELEASES).mkdir(parents=True)
    carried: list[str] = []
    manifests = sorted((previous / RELEASES).glob("*.json")) if previous else []
    for path in manifests:
        assert previous is not None
        manifest = json.loads(path.read_text(encoding="utf-8"))
        rid = path.stem
        if rid == release:
            continue  # a rebuild of the same commit
        if manifest.get("replaced_at") is None:
            manifest["replaced_at"] = _iso(now)  # the release this one replaces
        replaced = datetime.fromisoformat(manifest["replaced_at"])
        if replaced < now - keep:
            continue
        missing = [f for f in manifest["files"] if not (previous / f).is_file()]
        if missing:
            raise SystemExit(f"release {rid} lists files the previous image lacks: {missing[:3]}")
        for name in manifest["files"]:
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(previous / name, target)
        (out / RELEASES / f"{rid}.json").write_text(json.dumps(manifest, indent=1),
                                                    encoding="utf-8")
        carried.append(rid)

    (dist / RELEASES).mkdir(exist_ok=True)
    own = {"built_at": _iso(now), "replaced_at": None, "files": own_files(dist)}
    (dist / RELEASES / f"{release}.json").write_text(json.dumps(own, indent=1), encoding="utf-8")
    return carried


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--previous", type=Path, help="html directory of the previous image")
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--keep-days", type=float, default=7)
    args = parser.parse_args()
    previous = args.previous if args.previous and args.previous.is_dir() else None
    carried = carry(previous, args.dist, args.out, args.release,
                    timedelta(days=args.keep_days), _now())
    print(f"release {args.release}: carried {len(carried)} earlier release(s) {carried}")


if __name__ == "__main__":
    main()
