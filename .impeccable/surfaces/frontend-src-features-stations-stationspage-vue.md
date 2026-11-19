---
version: 1
slug: "frontend-src-features-stations-stationspage-vue"
primary_target: "frontend/src/features/stations/StationsPage.vue"
related_targets: ["frontend/src/features/stations/StationForm.vue"]
---

# Stations: list and new station

Scope: `/stations` (list, map toggle) and `/stations/new` (+ `/stations/:id/edit`, same form). Mode: Operate. Audience: office staff first (admins, viewers), technicians on phones second, clients read their own organization's stations. Job: see the network's health and act on what is wrong, then find any station. Constraints: DBD tokens, fonts and reserved status colours; the shell may change on these pages (user, 2026-11-19); only data the API has (manual status, last visit, next calibration due, open requests and visits); no invented fault reasons or data-gap times.

## Direction contract

THESIS: The page is a handover sheet: it opens on what is wrong, ranked, each row one problem and its next step. It refuses the category default of a full register table with filters in a side pane.

OWN-WORLD: MARS-MMS as built (DESIGN.md): Ground Grey shell, Page White view, Caribbean Depth for action and selection, reserved status colours for offline, degraded, calibration and idle. Health counts set large in Google Sans with tabular figures; references in JetBrains Mono; 1 px ruled rows, no cards in the view.

STORY: An admin sees in one glance how many stations are offline, degraded, overdue for calibration or unvisited for 90 days, picks one, and takes its next step (open its visit or request, or raise one) without leaving the row. The full register is one tab away.

FIRST VIEWPORT: Rail, then a full-width view (no pane). Header: Stations, a one-line summary, search, Map, New station. Tabs: Needs attention (count) and All stations (count). Four health counts in one row, each a filter. Below, the ranked attention rows: status chip, code and name, the one problem with its fact, the organization and country, and one next-step button at the right edge.

FORM: Structure 6 of 7 (problems first, the register second), dealt as the lead; new station asks only the essentials (code, name, organization, country and time zone, a map pin) and opens the station page for the rest. seed:c6d7fa9e7564c67a

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
