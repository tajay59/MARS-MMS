"""The chart in a summary PDF (W19-11): which chart each report gets, the page it is drawn on and
what happens when it cannot be drawn. A real browser draws one only where it is installed."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime

import pytest

from app.domain import charts, summary
from app.domain.charts import ChartSpec, Series
from app.domain.summary import Doc, Kind, Table
from app.repo import charts as drawing
from app.repo import render

ZONE = "America/Jamaica"
NOW = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)


def doc(kind: Kind, columns: list[str], rows: list[list], extra: list[Table] | None = None) -> Doc:
    return Doc(kind, "T", tables=[Table("Main", columns, rows), *(extra or [])])


def test_requests_are_counted_by_status_biggest_first():
    rows = [["MR-1", "c", "p", "closed"], ["MR-2", "c", "p", "submitted"],
            ["MR-3", "c", "p", "closed"]]
    spec = charts.chart_for(doc(Kind.CLIENT_ACTIVITY, ["a", "b", "c", "d"], rows), ZONE)
    assert spec and spec.categories == ["closed", "submitted"]
    assert spec.series[0].values == [2.0, 1.0] and spec.horizontal


def test_station_history_counts_events_in_the_months_of_the_report_zone():
    # 02:00 UTC on 1 November is still October in Jamaica
    rows = [[datetime(2026, 11, 1, 2, tzinfo=UTC), "x"],
            [datetime(2026, 10, 3, 12, tzinfo=UTC), "x"],
            [datetime(2026, 10, 9, 12, tzinfo=UTC), "x"]]
    spec = charts.chart_for(doc(Kind.STATION_HISTORY, ["When", "Station"], rows), ZONE)
    assert spec and spec.categories == ["2026-10"] and spec.series[0].values == [3.0]


def test_calibration_due_shows_overdue_and_due_soon_for_each_station():
    rows = [["JM-1", "", "", None, -3, "Overdue"], ["JM-1", "", "", None, 4, "Due soon"],
            ["JM-2", "", "", None, 9, "Due soon"]]
    spec = charts.chart_for(doc(Kind.CALIBRATION_DUE, list("abcdef"), rows), ZONE)
    assert spec and spec.categories == ["JM-1", "JM-2"]
    assert {s.name: s.values for s in spec.series} == {"Overdue": [1.0, 0.0],
                                                       "Due soon": [1.0, 1.0]}


def test_turnaround_draws_the_by_category_table_not_the_closed_requests():
    by_category = Table("By category", ["Category", "Closed", "Median days", "90th percentile"],
                        [["fault", 4, 2.5, 6.0], ["upgrade", 1, 9.0, 9.0]])
    spec = charts.chart_for(doc(Kind.REQUEST_TURNAROUND, ["Request"], [["MR-1"]], [by_category]),
                            ZONE)
    assert spec and spec.categories == ["fault", "upgrade"]
    assert [s.name for s in spec.series] == ["Median days", "90th percentile"]


def test_a_long_list_shows_the_largest_and_says_so():
    rows = [["x", f"ST-{i:02d}"] for i in range(20) for _ in range(i + 1)]
    spec = charts.chart_for(doc(Kind.CONFIGURATION_HISTORY, ["a", "b"], rows), ZONE)
    assert spec and len(spec.categories) == charts.MAX_BARS and spec.categories[0] == "ST-19"
    assert spec.note and "12 largest of 20" in spec.note


def test_there_is_no_chart_when_there_is_nothing_to_draw_and_none_for_station_asset():
    assert charts.chart_for(doc(Kind.NETWORK_STATUS, list("abcd"), []), ZONE) is None
    zero = [["Model A", "", 1, 1, 0, None, 0]]
    assert charts.chart_for(doc(Kind.SENSOR_RELIABILITY, list("abcdefg"), zero), ZONE) is None
    assert charts.chart_for(doc(Kind.STATION_ASSET, ["a"], [["x"]]), ZONE) is None


def test_a_spec_survives_the_trip_through_a_view():
    spec = ChartSpec("T", ["a"], [Series("S", [1.0])], horizontal=True, note="n", alt="alt")
    assert ChartSpec.from_view(spec.to_view()) == spec


def test_the_page_holds_no_data_so_a_name_cannot_end_a_tag():
    spec = ChartSpec("T", ["</script><img src=x onerror=alert(1)>"], [Series("S", [1.0])])
    page, script = drawing.page_files(spec)
    assert "onerror" not in page and "script-src file:" in page
    assert "default-src 'none'" in page
    assert "onerror" in script  # in the data, a string for the chart to print as text
    assert script.startswith("var options = ")


def test_options_show_values_on_the_bars_and_leave_room_for_the_longest_one():
    horizontal = drawing.options(ChartSpec("T", ["a", "b"], [Series("S", [12.0, 5.0])],
                                           horizontal=True))
    assert horizontal["dataLabels"]["enabled"] and horizontal["xaxis"]["max"] == 14
    assert horizontal["legend"]["show"] is False and horizontal["yaxis"]["decimalsInFloat"] == 0
    columns = drawing.options(ChartSpec("T", ["a"], [Series("A", [1.5]), Series("B", [2.0])]))
    assert columns["legend"]["show"] is True and columns["yaxis"]["decimalsInFloat"] == 1
    assert "max" not in columns["xaxis"]


async def test_a_missing_browser_leaves_the_chart_out():
    spec = ChartSpec("T", ["a"], [Series("S", [1.0])])
    assert await drawing.ChromiumCharts("no-such-browser-here").draw(spec) is None


class Drawer:
    def __init__(self, picture: bytes | None = b"\x89PNG-fake", *, boom: bool = False) -> None:
        self.picture, self.boom = picture, boom

    async def draw(self, spec: ChartSpec) -> bytes | None:
        if self.boom:
            raise RuntimeError("browser died")
        return self.picture


def chart_view() -> dict:
    spec = ChartSpec("Stations by status", ["operational"], [Series("Stations", [3.0])],
                     alt="Stations by status. operational: Stations 3.")
    d = summary.build(Kind.NETWORK_STATUS, {
        "stations": {"s1": {"_id": "s1", "code": "A", "name": "A", "country": "JM",
                            "status": "operational"}},
        "last_visit": {}, "open_requests": {}, "overdue_units": {}})
    return summary.pdf_view(d, subtitle="s", filters="f", zone=ZONE, generated_at=NOW,
                            generated_by="x", chart=spec.to_view())


async def test_the_picture_goes_into_the_page_with_its_words():
    v = await render.WeasyRenderer(Drawer()).with_chart(chart_view())
    html = render.render_summary_html(v, summary.TEMPLATE_VERSION)
    assert 'src="data:image/png;base64,' in html and "Stations by status. operational" in html


@pytest.mark.parametrize("drawer", [None, Drawer(None), Drawer(boom=True)])
async def test_a_chart_that_cannot_be_drawn_is_left_out_and_the_table_still_prints(drawer):
    v = await render.WeasyRenderer(drawer).with_chart(chart_view())
    html = render.render_summary_html(v, summary.TEMPLATE_VERSION)
    assert "<img" not in html and "could not be drawn" in html and "<table" in html


def browser() -> str | None:
    wanted = os.environ.get("REPORT_CHROMIUM_PATH") or "chromium"
    return shutil.which(wanted)


@pytest.mark.skipif(browser() is None, reason="no Chromium here: the service image has one")
async def test_a_real_browser_draws_a_picture():
    spec = ChartSpec("T", ["closed", "submitted"], [Series("Requests", [12.0, 5.0])],
                     horizontal=True)
    picture = await drawing.ChromiumCharts(browser() or "", 60).draw(spec)
    assert picture is not None and picture.startswith(drawing.PNG) and len(picture) > 5000
