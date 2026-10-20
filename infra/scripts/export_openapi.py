"""Write each built service's OpenAPI schema to frontend/openapi/<service>.json.

The frontend's API types are generated from these files (`npm run api:types` in frontend/), and
CI fails if a regenerated schema differs from the committed one (TP: OpenAPI type drift).

Run from the repo root with the venv that has the services installed:

    .venv/Scripts/python infra/scripts/export_openapi.py            # every service
    .venv/Scripts/python infra/scripts/export_openapi.py auth       # one service
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Services with a public API. platform's notification routes arrive in Phase 3.
SERVICES = ["auth", "operations", "media", "report"]


def export(service: str) -> Path:
    service_dir = ROOT / "services" / service
    sys.path.insert(0, str(service_dir))
    try:
        for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
            del sys.modules[name]  # each service has its own `app` package
        main = importlib.import_module("app.main")
        schema = main.create_app().openapi()
    finally:
        sys.path.remove(str(service_dir))
    out = ROOT / "frontend" / "openapi" / f"{service}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # LF and a stable layout, so the drift check compares content only.
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    for name in sys.argv[1:] or SERVICES:
        print(export(name).relative_to(ROOT))
