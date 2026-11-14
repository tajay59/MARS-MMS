"""Counts of a ZAP report by risk, and an exit code: 1 when any alert is high risk, else 0.

Prints counts only. The repository is public and so are its run logs, so a finding's name or the
address it was seen at must not be printed here (W20 plan, decision 8).

    python .zap/summarize.py report.json
"""

import json
import sys

LEVELS = {"3": "high", "2": "medium", "1": "low", "0": "informational"}


def main(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, ValueError):
        print("::error::ZAP wrote no readable report")
        return 1
    counts: dict[str, int] = {}
    for site in report.get("site", []):
        for alert in site.get("alerts", []):
            level = LEVELS.get(str(alert.get("riskcode")), "other")
            counts[level] = counts.get(level, 0) + 1
    print("ZAP alerts by risk:", counts or "none")
    if counts.get("high"):
        print("::error::a high risk alert: run infra/scripts/zap-baseline.sh for the details")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
