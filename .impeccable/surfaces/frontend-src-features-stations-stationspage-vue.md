---
version: 1
slug: "frontend-src-features-stations-stationspage-vue"
primary_target: "frontend/src/features/stations/StationsPage.vue"
related_targets: ["frontend/src/features/stations/StationForm.vue"]
---

# Stations: list and new station

Scope: `/stations` (list, map toggle) and `/stations/new` (+ `/stations/:id/edit`, same form). Mode: Operate. Audience: office staff first (admins, viewers), technicians on phones second, clients read their own organization's stations. Job: see the network's health and act on what is wrong, then find any station. Constraints: DBD tokens, fonts and reserved status colours; the shell may change on these pages (user, 2026-11-19); only data the API has (manual status, last visit, next calibration due, open requests and visits); no invented fault reasons or data-gap times.

## Direction contract

THESIS: The page is a handover sheet: it opens on what is wrong, ranked, each row one problem and its next step. The pane is its ledger: every filter is a counted button there, so the overview and the filter are one control (revised 2026-11-20 at the user's request: the filter buttons return to the pane; supersedes the paneless list of 2026-11-19).

OWN-WORLD: MARS-MMS as built (DESIGN.md): Ground Grey shell, Page White view, Caribbean Depth for action and selection, reserved status colours for offline, degraded, calibration and idle. Health counts set large in Google Sans with tabular figures; references in JetBrains Mono; 1 px ruled rows, no cards in the view.

STORY: An admin reads the pane's ledger in one glance (how many stations are offline, degraded, overdue for calibration or unvisited for 90 days), presses one, and takes the next step on a row (open its visit or request, or raise one). The full register is the ledger's second list. With a station open, the same buttons stay above the matching stations, so the admin works down a filtered list without going back.

FIRST VIEWPORT: Rail, pane, view. Pane: the section's page tabs, search, then Show: Needs attention (count) with its four problem buttons (label, a one-line fact, a large tabular count) and All stations (count) with its status buttons; then Narrow both lists (Organization, Country, Type, Measures). View: Stations, a one-line summary, New station; a result line naming the chosen list or filter and its count, with a removable chip per active narrowing; the ranked attention rows (problem chip, name and code, the fact, organization, country and open work, one next-step button) or the register table. With a station open the pane keeps the buttons (compact, no facts), folds the fields and lists the matching stations. Phones: the pane pins above the list with search and Scan, the two lists as a switch, that list's buttons as 40 px chips with counts, the fields in More filters.

FORM: Structure 6 of 7 (problems first, the register second), dealt as the lead; new station asks only the essentials (code, name, organization, country and time zone, a map pin) and opens the station page for the rest. seed:c6d7fa9e7564c67a

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
