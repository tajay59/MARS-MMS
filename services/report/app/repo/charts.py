"""Draws a chart for a summary PDF (W19-11; TRD 11.1, DBD D3): ApexCharts in headless Chromium.

One browser process for each chart. The report image carries Chromium and the vendored
ApexCharts (`app/charts/`); the worker writes a small page into a temporary folder, asks the
browser for a PNG of it and reads the file back. A chart that cannot be drawn, in 30 seconds or
at all, is left out: `draw` returns None and the report prints its table without it.

The page has a Content-Security-Policy that allows only local script files, so a station or
model name that looks like HTML is text and nothing else.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol

from mms_common.logging import get_logger

from app.domain.charts import ChartSpec

log = get_logger(__name__)

APEX = Path(__file__).resolve().parent.parent / "charts" / "apexcharts.min.js"
WIDTH = 720  # CSS pixels; the picture is taken at three times this for print
SCALE = 3
PNG = b"\x89PNG\r\n\x1a\n"
# Brand blue, a light tint of it and a dark slate: distinct on screen and in greyscale print
COLORS = ["#0a6780", "#7fb0c0", "#3d4b52"]


class ChartDrawer(Protocol):
    async def draw(self, spec: ChartSpec) -> bytes | None: ...


def height_for(spec: ChartSpec) -> int:
    """Taller for a horizontal chart with many bars; a column chart is a fixed height."""
    if spec.horizontal:
        return 70 + 34 * len(spec.categories) * max(1, len(spec.series))
    return 300


def options(spec: ChartSpec) -> dict[str, Any]:
    """The ApexCharts options. Animations are off (the picture is taken at once), values are
    written on the bars (a printed chart has no hover) and the colours are fixed."""
    whole = all(float(v).is_integer() for s in spec.series for v in s.values)
    peak = max((v for s in spec.series for v in s.values), default=1) or 1
    return {
        "chart": {
            "type": "bar", "width": WIDTH, "height": height_for(spec), "background": "#ffffff",
            "fontFamily": "Inter, sans-serif", "foreColor": "#3d4b52",
            "animations": {"enabled": False}, "toolbar": {"show": False},
            "parentHeightOffset": 0, "zoom": {"enabled": False},
        },
        "series": [{"name": s.name, "data": s.values} for s in spec.series],
        "xaxis": {"categories": spec.categories, "labels": {"trim": True, "rotate": -45,
                                                             "rotateAlways": False},
                  # Room past the longest bar for its value (the axis of a horizontal chart)
                  **({"max": math.ceil(peak * 1.15)} if spec.horizontal else {})},
        "yaxis": {"decimalsInFloat": 0 if whole else 1, "min": 0},
        "plotOptions": {"bar": {"horizontal": spec.horizontal, "borderRadius": 2,
                                "columnWidth": "60%", "barHeight": "70%",
                                "dataLabels": {"position": "top"}}},
        # The value sits past the end of its bar, on white, so dark text always reads
        "dataLabels": {"enabled": True, "style": {"fontSize": "11px", "colors": ["#1f2d33"]},
                       "textAnchor": "start" if spec.horizontal else "middle",
                       "offsetX": 8 if spec.horizontal else 0,
                       "offsetY": 0 if spec.horizontal else -18,
                       "background": {"enabled": False}},
        "colors": COLORS[: len(spec.series)],
        "legend": {"show": len(spec.series) > 1, "position": "top", "horizontalAlign": "left"},
        "grid": {"borderColor": "#dbe3e7", "strokeDashArray": 3},
        "stroke": {"show": False},
        "tooltip": {"enabled": False},
    }


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; script-src file:; style-src 'unsafe-inline'; img-src data:">
<style>html,body{{margin:0;background:#fff}}#c{{width:{width}px;height:{height}px}}</style>
</head><body><div id="c"></div>
<script src="{apex}"></script><script src="chart.js"></script></body></html>
"""

SCRIPT = (
    "var options = %s;\n"
    "new ApexCharts(document.getElementById('c'), options).render();\n"
)


def page_files(spec: ChartSpec) -> tuple[str, str]:
    """The page and its script. The data is in a script file, not in the page, so nothing a
    name could say can end a tag."""
    page = PAGE.format(width=WIDTH, height=height_for(spec), apex=APEX.as_uri())
    return page, SCRIPT % json.dumps(options(spec))


class ChromiumCharts:
    def __init__(self, binary: str = "chromium", timeout_s: int = 30) -> None:
        self.binary = binary
        self.timeout_s = timeout_s

    def command(self, exe: str, folder: Path, png: Path, spec: ChartSpec) -> list[str]:
        return [
            exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
            "--disable-extensions", "--no-first-run", "--hide-scrollbars", "--disable-breakpad",
            f"--force-device-scale-factor={SCALE}",
            f"--window-size={WIDTH},{height_for(spec) + 16}",
            "--virtual-time-budget=5000",
            f"--user-data-dir={folder / 'profile'}", f"--screenshot={png}",
            (folder / "chart.html").as_uri(),
        ]

    async def draw(self, spec: ChartSpec) -> bytes | None:
        exe = shutil.which(self.binary)
        if exe is None:
            log.warning("chart_browser_missing", binary=self.binary)
            return None
        page, script = page_files(spec)
        with tempfile.TemporaryDirectory(prefix="mms-chart-") as tmp:
            folder = Path(tmp)
            (folder / "chart.html").write_text(page, encoding="utf-8")
            (folder / "chart.js").write_text(script, encoding="utf-8")
            png = folder / "chart.png"
            process = await asyncio.create_subprocess_exec(
                *self.command(exe, folder, png, spec),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                # The service user has no home folder, and Chromium needs somewhere to write
                env={**os.environ, "HOME": tmp, "XDG_CONFIG_HOME": tmp, "XDG_CACHE_HOME": tmp})
            try:
                await asyncio.wait_for(process.wait(), self.timeout_s)
            except TimeoutError:
                process.kill()
                await process.wait()
                log.warning("chart_timeout", title=spec.title, seconds=self.timeout_s)
                return None
            if process.returncode != 0 or not png.exists():
                log.warning("chart_failed", title=spec.title, code=process.returncode)
                return None
            data = png.read_bytes()
        return data if data.startswith(PNG) else None
