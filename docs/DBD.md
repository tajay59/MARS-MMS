# Design Brief Document (DBD)
## AWS-MMS — Automatic Weather Station Maintenance Management System

| | |
|---|---|
| **Version** | 1.6 |
| **Date** | 2026-10-18 |
| **Status** | Draft for review |
| **Changes in 1.1** | Components are built on Vuetify 4 instead of PrimeVue 4 (TRD 1.2, ADR-11). Icons are Material Design Icons instead of PrimeIcons. Colours, type, spacing, shells and page designs are unchanged. |
| **Changes in 1.2** | Follows AFD 1.1 and TRD 2.0: the Unlock page (offline PIN), station owners on the visit and field pages, the finalizing state on the visit report, feedback `*-container` theme colours, and links to the AFD fixed. 37 pages |
| **Changes in 1.3** | `/register`: the organization is a plain text field, not a picker of existing organizations (PRD 1.2 AUTH-1, AFD 1.2 J1) |
| **Changes in 1.4** | **The app shell** (decision W4-9, 2026-10-17) replaces the client and staff shells: three square tiles on a ground colour, 5 px apart: a slim **rail** of section icons with tooltips, an **interactive pane** (section tabs, the list or the controls) and a **view** (the details). On phones the pane and view fill the screen and the rail becomes a floating tab tile. New `ground` colour token; tiles have no corner radius. The field shell and the split panel are unchanged |
| **Changes in 1.5** | **Brand colours from a Material 3 theme** (decision W4-12, 2026-10-17; closes D1's colour part): the built-in theme is `frontend/src/app/theme/material-theme.json` (Material Theme Builder, seed `#026D88`), and admins can replace it for everyone on **Settings** (`/admin/settings`). Status colours stay fixed. **Motion with GSAP** (W4-10): the pane's width, page and list entrances, the rail's hover, sliding indicator and tooltips. **Person avatars** with initials on a brand gradient (W4-13), the one allowed gradient. **Settings** page for admins (W4-11) |
| **Changes in 1.6** | Below 1024 px the rail becomes a docked, translucent **bottom bar** with the open section as a filled pill (decision W4-14, 2026-10-18); tablets keep the pane and view side by side above it. Pane lists of people are **message-style** rows: 48 px avatar, name with a short time on its right, one line below, the open row fully round (W4-15). **Motion curves** (W4-15): the pane's width on Material 3's emphasized curve, a record opened from the pane rises in, list rows shrink while pressed and spring back |
| **Companion documents** | [PRD.md](PRD.md) v1.1 (Product Requirements), [TRD.md](TRD.md) v2.0 (Technical Requirements), [AFD.md](AFD.md) v1.1 (App Flow) |
| **Live copy** | [Claude Doc](https://claude.ai/code/artifact/b14d2c1e-0106-470a-bd5a-ffc28c4eea37) (1.1; superseded by this file) |

> The two wireframes are redrawn here as text; the live copy has the drawn versions.

---

## Purpose and scope

AWS-MMS v1 ships with a light theme and a dark theme. It is built on Vuetify 4, set to this brief through its themes and global defaults, with a single blue brand colour, a reserved set of status colours, Inter and JetBrains Mono, and three layouts (client, staff and field). This brief fixes those choices so every screen, PDF and email looks like one product.

| Document | What it decides | This brief takes from it |
| --- | --- | --- |
| PRD v1.1 | What the app does, for whom | Roles, personas, statuses, WCAG 2.2 AA (NFR-11), devices (NFR-5) |
| TRD v2.0 | How it is built | Vuetify 4, Tailwind CSS 4, theme tokens in `app/theme/brand.ts`, self-hosted fonts (CSP), WeasyPrint PDFs |
| AFD v1.1 | Which page comes next | The 37 pages, routes, tabs, menus by role, error and empty states |
| **Design brief (this)** | How each page looks | — |

- **Covers:** colour, type, spacing, layout, components, icons, imagery, the look of every page in the AFD, PDF reports and email.
- **Does not cover:** page flow and routes (AFD), API and data (TRD), the final logo.
- **Brand assets are still to come (PRD Q1).** The blue scale in this brief is a working default. When the organization supplies its colours, only the `primary` scale in `brand.ts` changes. Status colours, neutrals and type stay as they are.

## Brand personality and design principles

AWS-MMS should feel like a well-kept instrument: **calm, precise and dependable**. It is a work tool for people in offices and on remote hillsides, not a marketing site. The colour goes on the things that need attention, and everything else stays quiet.

| Principle | What it means on screen | Who it serves |
| --- | --- | --- |
| **Status first** | Every station, request, visit, report and sensor shows its status as a chip with an icon and a word. Status colours are used only for status. | Andrea scanning the queue; Maria checking her request |
| **Works in the field** | Field pages use 48 px touch targets, 16 px or larger text, the strongest text colour only, and one main action per screen. They must be readable in sunlight and usable with wet or gloved hands. | Devon at a station with no signal |
| **Nothing is lost, and the user can see that** | The sync badge, “saved on this phone” messages and progress counts are always visible in field mode. | Devon; anyone working offline |
| **Plain for clients, dense for staff** | Client pages are roomy and use plain words. Staff pages can show more columns, filters and data per screen. | Maria vs Andrea and Paul |
| **Records look official** | Signed reports, signatures, references and hashes use a formal, print-like style: mono references, clear version labels and a DRAFT watermark. | Clients signing off; auditors |
| **One way to do a thing** | Vuetify components are used as they come, with Tailwind for spacing. There are no one-off widgets and each view has one primary button. | The single developer (NFR-12) |

**Never:** decorative gradients (the one exception is the person avatar, below), stock illustrations, weather-app theatrics (animated clouds, glossy icons), colour as the only signal, or grey text that fails contrast.

## Colour palette

The palette has three parts: the **brand colours**, which come from a Material 3 theme, the **neutrals** from the same theme, and a reserved set of **status colours** that never change. Every text pairing passes WCAG 2.2 AA (4.5:1) in both themes. Tokens are set once in `app/theme/brand.ts`, which defines Vuetify's `light` and `dark` themes with the same colour names; Tailwind reads them through Vuetify's theme variables (`bg-primary`, `text-surface-700`).

### Brand and neutrals: a Material 3 theme (decision W4-12)

The brand colours are a **Material Theme Builder export**: a light and a dark scheme (49 colour roles each) and five tonal palettes (primary, secondary, tertiary, neutral, neutral-variant; tones 0–100). The built-in one is `frontend/src/app/theme/material-theme.json` (seed `#026D88`, a deep teal). An admin can replace it for everyone on **Settings › Brand colours** (`/admin/settings/colours`): upload another export, make one from a single colour, change single colours or edit the JSON, preview it on their own screen, then save. The server keeps it (`GET`/`PUT /api/v1/auth/branding`, audited as `branding.updated`) and every device keeps the last copy for the first paint and offline. `app/theme/material.ts` maps it onto the token names pages use, so no page changes when the brand does:

| Token | From the theme (light / dark) | Built-in light | Built-in dark | Use |
| --- | --- | --- | --- | --- |
| `primary` / `on-primary` | scheme `primary` / `onPrimary` | `#0A6780` / white (6.43) | `#89D0ED` / `#003544` (7.73) | Primary buttons, links, active tab, focus ring |
| `primary-50` … `primary-950` | primary palette, tones 95 (dark 15), 90, 80, 70, 60, 50, 40, 30, 20, 10 (dark 5), 5 | `primary-600` `#006781` | — | Selected rows (`primary-50`), active rail and tab fill (`primary-100`, dark `primary-800`), PWA icon (`primary-600`) |
| `secondary-600/700`, `tertiary-600/700` | secondary and tertiary palettes, tones 40 / 30 | — | — | Avatar gradients only |
| `surface` (tiles) | `surfaceContainerLowest` / `surfaceContainerLow` | `#FFFFFF` | `#171C1F` | The app shell's tiles, cards, inputs |
| `ground` | `surfaceContainer` / `surfaceContainerLowest` | `#EAEEF2` | `#0A0F11` | Behind the tiles |
| `surface-50`, `surface-100` | `surfaceContainerLow`, `surfaceContainer` / `surfaceContainer`, `surfaceContainerHigh` | | | Light fills, hover |
| `surface-200` | `surfaceContainerHighest` | `#DEE3E6` | `#303638` | Borders and dividers (decorative only) |
| `surface-300` | `outlineVariant` | | | Skeletons, strong dividers |
| `surface-500` | `outline` | `#70787C` (4.50) | `#8A9296` (5.43) | **Input and checkbox borders**, icons, placeholders |
| `surface-600` | `onSurfaceVariant` | `#40484C` (9.34) | `#C0C8CC` (10.12) | Secondary text, captions, table meta: the lightest text |
| `surface-700` | neutral-variant tone 20 / 90 | | | Labels, table body text |
| `surface-900`, `on-surface` | `onSurface` | `#171C1F` (17.18) | `#DEE3E6` (13.28) | Headings and body text |
| `info`, `info-container` | `primary`, `primaryContainer` with `onPrimaryContainer` | | | Information banners (7.27) |
| `error`, `error-container` | `error`, `errorContainer` with `onErrorContainer` | | | Danger buttons, error banners and field errors |
| `surface-variant` (Vuetify) | `inverseSurface` / `inverseOnSurface` | | | Snackbars |

Contrast figures in brackets are against the tiles. The Brand colours editor checks the same pairs (text, secondary text, primary buttons, links, field errors) for any theme and warns below 4.5:1 before an admin saves. **Status colours, success and warning never come from the theme** (they stay as listed below), so a brand change can't make two statuses look alike.

**Person avatars** (W4-13) are the one gradient in the app: a circle with the person's initials in white on a 135° gradient between two brand tones (primary, secondary or tertiary, tones 30–40, so white keeps 4.5:1 in both themes). The person's id picks one of six pairs, so they keep theirs everywhere. They are decoration (`aria-hidden`): the name is always written beside them. First used on the Registrations list.

### Feedback colours (banners, toasts, inline messages)

| Meaning | Text / icon | Background | Border | Example |
| --- | --- | --- | --- | --- |
| Success | `#166534` | `#DCFCE7` | `#15803D` | “Request submitted — MR-2026-0042” |
| Info | theme `onPrimaryContainer` | theme `primaryContainer` | theme `primary` | “This request is waiting for your review” |
| Warning | `#92400E` | `#FEF3C7` | `#B45309` | “This visit isn’t ready for offline use” |
| Danger | theme `onErrorContainer` | theme `errorContainer` | theme `error` | “This file failed the virus scan” |

The danger button is solid theme `error` with `onError` text (built-in `#BA1A1A` with white, 6.46:1). It appears only on the confirm step of a destructive action, never as the first click.

In `brand.ts` the border colour is the theme colour (`success`, `info`, `warning`, `error`) and the background and text pair is `*-container` / `on-*-container` (for example `warning-container` `#FEF3C7` with `on-warning-container` `#92400E`).

### Status colours (reserved; chips, map markers, timeline dots)

Every chip shows **icon + word + colour**, so no status depends on colour alone. Text/background pairs are Tailwind 800/100 shades, and all are 6.4:1 or better. Icons are from Material Design Icons. Each status pair is a Vuetify theme colour with its `on-*` text colour (for example `status-approved` and `on-status-approved`), so a chip switches to its dark pair with the theme.

**Request status**: one hue per stage, in workflow order (PRD §5.1):

| Status | Text | Background | Icon | Why this colour |
| --- | --- | --- | --- | --- |
| Submitted | `#1E293B` | `#FFFFFF` + `#64748B` border | `mdi-inbox-outline` | New, not yet looked at: outlined, neutral |
| Approved | `#075985` | `#E0F2FE` | `mdi-check` | Accepted, waiting on staff (sky) |
| Assigned | `#1E40AF` | `#DBEAFE` | `mdi-account-outline` | Has an owner (blue) |
| Scheduled | `#3730A3` | `#E0E7FF` | `mdi-calendar-blank-outline` | Has a date (indigo) |
| In progress | `#5B21B6` | `#EDE9FE` | `mdi-wrench-outline` | Work under way (violet) |
| Client Review | `#92400E` | `#FEF3C7` | `mdi-signature-freehand` | Waiting on the client to act (amber) |
| Reopened | `#9A3412` | `#FFEDD5` | `mdi-replay` | Sent back by the client (orange) |
| Closed | `#166534` | `#DCFCE7` | `mdi-check-circle-outline` | Done (green) |
| Denied | `#991B1B` | `#FEE2E2` | `mdi-cancel` | Refused (red) |
| Cancelled | `#334155` | `#E2E8F0` | `mdi-close-circle-outline` | Stopped (grey) |

**Station status**: chips and map markers. Markers also differ by **shape**:

| Status | Colour | Marker shape | Icon |
| --- | --- | --- | --- |
| Operational | `#15803D` | Filled circle | `mdi-check-circle-outline` |
| Degraded | `#B45309` | Filled triangle | `mdi-alert-outline` |
| Offline | `#B91C1C` | Filled square with a white × | `mdi-close` |
| Decommissioned | `#64748B` | Hollow circle | `mdi-minus-circle-outline` |

**Other status sets**: these reuse the same feedback colours, so there are no new hues:

| Set | Green (`#166534` on `#DCFCE7`) | Blue (`#1E40AF` on `#DBEAFE`) | Amber (`#92400E` on `#FEF3C7`) | Red (`#991B1B` on `#FEE2E2`) | Grey (`#334155` on `#E2E8F0`) |
| --- | --- | --- | --- | --- | --- |
| Priority | — | — | High | Urgent (solid `#B91C1C`, white text) | Low, Normal (plain text, no chip) |
| Calibration due | In date | — | Due within 30 days | Overdue | No interval set |
| Calibration result | Pass | Adjusted | — | Fail | — |
| Checklist item | OK | Fixed | — | Issue | N/A |
| Visit report | Final | — | Draft | — | Superseded |
| Sync | Synced | Syncing (spinner) | Waiting (count) | Failed | Paused |
| Sensor unit | Installed | In stock | In repair | — | Retired |
| Account | Active | — | Pending | Rejected | Disabled |

**Rules**

- Status colours never decorate. A green button or a red heading is not allowed.
- Primary blue is for actions and selection. It never means a status, so “Info” banners use blue but status chips use sky, blue, indigo and violet from the table above.
- Only one solid red chip (Urgent) is allowed per row, so urgency stands out.

### Dark theme

Dark mode ships in v1 (D2). Each user picks **Light**, **Dark** or **System** under Appearance on My profile. System is the default and follows the device. The choice is saved on the account and cached on the device for the login pages. Pages use role tokens only, so `brand.ts` holds a second set of values and no page has theme-specific code.

> Since DBD 1.5 the brand and neutral rows below (background, cards, borders, text, primary, selected, ground, danger) take their dark values from the Material theme's dark scheme (Brand and neutrals, above); the hex values in those rows are the Horizon and slate placeholders they replaced, kept for history. Feedback (success, warning), status chips and chart rows are unchanged.

| Role | Light | Dark | Dark contrast |
| --- | --- | --- | --- |
| App background | surface-50 `#F8FAFC` | `#0B1220` | — |
| Cards, inputs, dialogs | surface-0 `#FFFFFF` | `#111A2E` | — |
| Table header, read-only fields, tab strip, hover | surface-100 `#F1F5F9` | `#1A2539` | — |
| Card borders, dividers (decorative only) | surface-200 `#E2E8F0` | `#263247` | — |
| Skeleton loaders | surface-300 `#CBD5E1` | `#2E3A50` | — |
| Input and checkbox borders, icons, placeholders | surface-500 `#64748B` | `#708296` | 4.39 on cards |
| Secondary text, captions, table meta | surface-600 `#475569` | `#94A3B8` | 6.76 on cards |
| Labels, table body text | surface-700 `#334155` | `#CBD5E1` | 11.68 on cards |
| Headings and body text | surface-900 `#0F172A` | `#F1F5F9` | 15.83 on cards |
| Primary buttons, links, active tab, focus ring | primary-600 `#22569A` | primary-300 `#86B1DE`; button text primary-950 `#0F1F35` | 7.73 on cards; button text 7.38 |
| Primary hover / pressed | primary-700 / primary-800 | primary-200 `#B6D0EC` / primary-100 `#D9E7F5` | — |
| Selected row, active nav item, unread notification | primary-50 `#EFF5FB` | `#16294A` | Text 13.22 |
| App shell ground | slate-100 `#F1F5F9` | `#070C17` behind `#111A2E` tiles | Tiles stand out by colour; no border |
| Danger button, Urgent chip | `#B91C1C`, white text | `#DC2626`, white text | 4.83 |
| Internal comment background | amber-50 | `#2A2110` | Text 14.48 |

**Feedback colours (dark)**

| Meaning | Text / icon | Background | Border | Text contrast |
| --- | --- | --- | --- | --- |
| Success | `#86EFAC` | `#0B2E1A` | `#22C55E` | 10.53 |
| Info | `#B6D0EC` | `#12233D` | `#548CCB` | 9.92 |
| Warning | `#FCD34D` | `#33210A` | `#F59E0B` | 10.69 |
| Danger | `#FCA5A5` | `#3A1212` | `#EF4444` | 8.68 |

**Status chips (dark).** Each status keeps its hue, icon and word. The pair flips to light text on a deep background (Tailwind 200 on 950 shades).

| Status | Text | Background | Contrast |
| --- | --- | --- | --- |
| Submitted | `#E2E8F0` | None, with a `#94A3B8` border | 14.07 |
| Approved | `#BAE6FD` | `#0C2D48` | 10.66 |
| Assigned | `#BFDBFE` | `#172554` | 10.34 |
| Scheduled | `#C7D2FE` | `#1E1B4B` | 10.72 |
| In progress | `#DDD6FE` | `#2E1065` | 10.97 |
| Client Review | `#FDE68A` | `#3D2A06` | 11.00 |
| Reopened | `#FED7AA` | `#431407` | 11.56 |
| Closed | `#BBF7D0` | `#052E16` | 12.30 |
| Denied | `#FECACA` | `#450A0A` | 11.16 |
| Cancelled | `#E2E8F0` | `#334155` | 8.40 |

The other status sets use the dark pair of the matching hue: green = Closed, blue = Assigned, amber = Client Review, red = Denied, grey = Cancelled.

**Charts (dark):** single series `#6FA0D6`. Categories, in order: `#6FA0D6` blue, `#2DD4BF` teal, `#A78BFA` violet, `#F59E0B` amber, `#94A3B8` slate (each 6.3:1 or better on cards). Gridlines `#263247`, axis text `#94A3B8`.

**What stays the same in both themes**

- Map tiles stay standard OpenStreetMap, so station markers keep their light-theme colours and white outline. The legend, popups and filter panel follow the theme.
- The signature pad canvas stays white with dark ink, because the signature is stored and printed.
- PDF reports and email are always light.
- The media viewer and QR scanner stay black, and the login panel's left side stays primary-950.

**Field use.** The field shell follows the same setting. Light reads better in direct sun, so the Sync page has an Appearance switch for a quick change on site.

## Typography

The app uses three typefaces. **Google Sans** is for titles (page and section headings, KPI numbers), **Roboto Flex** is for all other interface text, and **JetBrains Mono** is for references, serial numbers, hashes and file names. Both are open-source (SIL OFL) and self-hosted as WOFF2 through `@fontsource-variable`. The CSP blocks font CDNs, and the service worker precaches the fonts so they work offline (TRD §13.3, §15).

| Family | Weights | Why | Fallback stack |
| --- | --- | --- | --- |
| Google Sans (variable) | 600 semibold for titles | The Material 3 display face; gives headings and KPI numbers their character. | Roboto Flex, then `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` |
| Roboto Flex (variable) | 400 regular, 500 medium | Very readable at 12–16 px on phones. Its tabular figures (`font-feature-settings: "tnum"`) keep numbers in tables and readings aligned. | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` |
| JetBrains Mono (variable) | 400, 500 | 0/O and 1/l/I are easy to tell apart, which serial numbers like `HMP155-K1230045` need | `ui-monospace, "SFMono-Regular", Consolas, monospace` |

The same two files are embedded in WeasyPrint PDF templates (`base.html.j2`), so reports match the screen.

### Type scale

The base is 16 px. Sizes are in rem so they follow the browser zoom. Phones keep 16 px for body and inputs, which stops iOS zooming into fields.

| Token | Size / line height | Weight | Use |
| --- | --- | --- | --- |
| `text-display` | 30 / 38 px (24 / 32 on phones) | 600 | Page title (“MR-2026-0042 · Rain gauge not reporting”) |
| `text-h2` | 20 / 28 px | 600 | Section and card-group headings, dialog titles |
| `text-h3` | 16 / 24 px | 600 | Card titles, tab panel headings, form section headings |
| `text-body` | 16 / 24 px | 400 | Paragraphs, form inputs, comments |
| `text-sm` | 14 / 20 px | 400 | Table cells, list meta, helper text, menu items (staff desktop) |
| `text-label` | 14 / 20 px | 500 | Form labels, chip text, button text (desktop) |
| `text-xs` | 12 / 16 px | 500 | Timestamps, captions, badge counts. This is the smallest size allowed. |
| `text-kpi` | 32 / 40 px | 600, tabular | Dashboard numbers (“4 calibrations due”) |
| `text-mono` | 14 / 20 px | 500 | `MR-2026-0042`, `VR-2026-0042-02`, serials, config versions, hash `a3f9…9c21` |
| `text-field-action` | 18 / 24 px | 600 | Field-mode primary buttons (“Arrive”, “Depart station”, “End visit”) |

**Rules**

- Use sentence case everywhere: headings, buttons and menu items (“Report a problem”, not “Report A Problem”). The only capitals are DRAFT and SUPERSEDED in report watermarks.
- Keep line length to 75 characters or fewer for reading text (comments, report narrative, descriptions), using `max-w-prose`.
- Use bold (600) for headings, KPI numbers and key values in a sentence. Never use italics for emphasis, because Roboto Flex's italic is weak at small sizes.
- Numbers in tables, readings and dates use tabular figures and right-align in numeric columns.
- Show times as `16 Oct 2026, 14:05 AST`: day month year, a 24-hour clock and the zone label wherever station local time is shown (TRD §13.2, RPT-9).

## Layout, grid and spacing

All 37 pages sit inside one of three frames: the **app shell** for staff and clients, the **field shell** for staff on phones during a visit, and the **split panel** for public pages (AFD §5.1). Spacing is on a 4 px grid. Each frame stays put, and only its content changes from page to page.

**Figure 1 — The app shell and the field shell.** The frame stays put; only the pane and view contents change.

```text
APP SHELL · desktop (staff and clients)          ground colour behind, 5 px gaps, square tiles
+----+ +------------------------+ +----------------------------------------------------+
|[M] | | Admin              [<] | | Maria Lopez                                        | (4)
|    | | (Registrations 2) Users| | Registered 17 Oct 2026, 08:00 AST                  |
|[D] | |  Organizations  Audit  | +----------------------------------------------------+
|[W] | |------------------------| |                                                    |
|[S] | | Maria Lopez            | |  Email · Phone · Organization they typed           | (5)
|[R] | |   Organization A · 2 h | |                                                    |
|[A]*| | Dev Joseph             | |  (o) Organization A  ( ) Another  ( ) A new one    |
|    | |   Island Water · 1 d   | |                                                    |
|(s) | |                        | |                          [Reject] [Approve Maria]  |
|(b) | |                        | |                                                    |
|(JR)| |                        | |                                                    |
+----+ +------------------------+ +----------------------------------------------------+
 (1)            (2) (3)
```

1. Rail tile, 64 px: the logo, one icon per section (Dashboard, Work, Stations, Reports, Admin; clients: Dashboard, Stations, Requests, Reports), then sync (staff), bell and the user menu at the bottom. It never expands: a tooltip on hover **and** keyboard focus names the section and what it holds. A dot marks a section with something waiting.
2. Interactive pane tile, 360 px (300 px on tablets, 420 px from 1536 px): the section name, its pages as tabs, then the page's list or controls. A button hides it so the view fills the width (remembered on the device).
3. Pages without a list put their controls here (dashboard filters, profile sections, user status filters).
4. View header: the page or record title, a subtitle and the page's actions.
5. View body: the details of what the pane selected. With nothing selected it shows a summary of the section and its main action.

```text
FIELD SHELL · phone, during a visit
+----------------------------+
| <- WXR-012 · Work (sync 3) | (1)
+----------------------------+
|  (*)---(@)---( )---( )     |
| Before Work  After Review  | (2)
|----------------------------|
| Rain gauge funnel clear    |
| [OK]  Fixed  Issue   N/A   | (3)
|                            |
| Cable glands sealed        |
|  OK   Fixed [Issue]  N/A   |
|                            |
| +------------------------+ |
| | Replace RH sensor      | |
| | Serials and readings   | |
| +------------------------+ |
+----------------------------+
|     [   Next: After   ]    | (4)
+----------------------------+
| Visit  Scan  Stations  Sync| (5)
+----------------------------+
```

1. App bar: back, station and step, sync badge.
2. Stepper: Before, Work, After, Review; labels always shown. `(*)` done, `(@)` current, `( )` ahead.
3. Checklist answers as 48 px OK / Fixed / Issue / N/A buttons.
4. Sticky action bar: one main button.
5. Bottom bar: Visit · Scan · Stations · Sync.

Each numbered marker matches the note beside it. The frame stays put and only the content area changes between pages.

### The shells

| Shell | Frame | Content width | Who sees it |
| --- | --- | --- | --- |
| **App shell** | Three tiles on the `ground` colour, 5 px apart and 5 px from the window edges, square corners, no border or shadow: the **rail** (64 px), the **interactive pane** (300 / 360 / 420 px, hideable from 1024 px) and the **view** (the rest). No app-wide top bar: each tile has its own header. On phones (< 768 px) the pane and view fill the screen edge to edge, one after the other; once a record is open the view shows alone with a Back button. Below 1024 px the rail becomes a **bottom bar** docked to the bottom edge, translucent (surface at 85 % with a backdrop blur, a top border and a soft upward shadow) and padded for the home indicator: four sections and **Me** (profile, notifications, sync, Admin), centred within 448 px. The section open is a filled primary pill with its label in bold primary; the others are bare 22 px icons with a hover tint, and labels are always shown (12 px). | View body max 1080 px; tables and maps use the full view | Staff and clients |
| **Field** | Top app bar, 56 px: back arrow, visit or station name, sync badge. Bottom bar, 64 px plus safe area: Visit · Scan · Stations · Sync. A sticky action bar sits above it for the step’s main button. | Full width, 16 px side gutters | Staff on phones on `/visits/:id/field`, `/scan` and `/sync` |

The app shell is plain Tailwind layout inside the one `VApp` (`frontend/src/app/shells/AppShell.vue`, `AppRail.vue`, `AppTabBar.vue`). A page fills the view with `PageBody` (its header and scrolling body) and puts its list or controls into the pane with `PaneContent`; the record it has open lives in the URL (`/admin/registrations/:id`), so a reload or Back keeps the place. The field shell uses Vuetify's `VAppBar` and `VBottomNavigation`. Nothing is reachable only by hover: the bottom bar has labels, and every rail icon has an accessible name and its tooltip text as a description.

Public pages (login, register, password reset, invitation, QR landing when logged out, verify, unlock) use a **split panel**. On desktop the left 40% is primary-950 with the logo and one station photograph, and the right 60% holds a white form card, max 440 px wide. On phones the form sits full width under a 120 px dark header.

### Breakpoints and grid

| Breakpoint (Tailwind) | Width | Columns / gutter | App shell |
| --- | --- | --- | --- |
| base (Vuetify `xs`) | < 640 px | 4 / 16 px | Pane, then view, full-bleed; a record opens alone with Back; bottom bar; tables become cards |
| `sm` | ≥ 640 px | 4 / 16 px | As base |
| `md` | ≥ 768 px | 8 / 24 px | Pane (300 px) and view as tiles, with the bottom bar instead of the rail |
| `lg` | ≥ 1024 px | 12 / 24 px | Rail, pane (360 px, hideable) and view |
| `xl` | ≥ 1280 px | 12 / 32 px | As `lg`; detail pages gain a right column (timeline, meta) |
| `2xl` | ≥ 1536 px | 12 / 32 px | Pane 420 px |

### Spacing scale (4 px base)

| Token | px | Typical use |
| --- | --- | --- |
| `1` | 4 | Icon to text inside a chip |
| `2` | 8 | Between chips; label to input |
| `3` | 12 | Inside table cells (vertical); between form helper and next field |
| `4` | 16 | Card padding on phones; page gutter on phones; between form fields |
| `6` | 24 | Card padding on desktop; between cards; grid gutter |
| `8` | 32 | Between page sections |
| `12` | 48 | Above the page title; empty-state padding |

### Surfaces, corners and depth

- **Ground** (`ground`: the theme's `surfaceContainer` in light, `surfaceContainerLowest` in dark) sits behind the app shell's tiles. **Tiles** are `surface` and stand out by colour alone: no border, no shadow, no corner radius.
- Inside a tile there are no bordered cards: sections are separated by 1 px surface-200 rules, and list rows are plain rows with a hover and a primary-50 selected state. **Cards** (surface-0, 1 px surface-200 border, no shadow) remain for public pages, dialogs and menus.
- The active rail icon, pane tab and tab-tile item use primary-100 with primary-700 (dark: primary-800 with primary-100). Status colours stay reserved for status.
- **Shadows** only on things that float: menus, dialogs, toasts and the field action bar (`shadow-lg`).
- **Corner radius:** 0 for the app shell's tiles, 6 px for inputs, buttons and tooltips, 10 px for cards, dialogs and list rows (pane lists of people are message-style: 72 px rows, 48 px avatar, name with a short time on its right, one line below, and the open row fully round), 12 px for rail icons, fully round for chips, badges and pane tabs, 0 for tables.
- **Motion** (W4-10): 150 ms ease-out for hovers, menus and tooltips, 200 ms for dialogs and drawers. The app shell's motion is GSAP (`app/motion.ts`): the **pane's width** tweens on Material 3's emphasized curve (400 ms opening, 300 ms closing) when it opens, closes or changes size, and the view tile follows (a short ease-in-out read as a jump); a new **page** rises 8 px and fades in (220 ms) while the old one goes at once; a **record** opened from the pane rises 14 px and fades in (450 ms, Material 3 emphasized decelerate, title then body) and the view scrolls to its top; a **list row** shrinks to 96 % while pressed (80 ms, ease-out) and springs back past full size (320 ms, `back.out(4)`), with a hover tint and the avatar growing to 105 %; a new page's **pane list** slides in from the rail's side; on phones the list and the record slide in from their sides. On the **rail**, the hovered icon lifts and grows a little with a soft overshoot and a fill grows out from it; pressing shrinks it; the **active fill is one tile that slides** to the section chosen; **tooltips** fade and slide out from the rail (and Escape hides them). Nothing loops except loading spinners. All motion is off under `prefers-reduced-motion`, and on a device where the person turned **Animations** off in Settings.

## Core components

Vuetify components are used as they come and styled only through the brand themes and global defaults in `app/theme/vuetify.ts`. The defaults set the look once (flat buttons, outlined inputs, flat bordered cards, no ripple), so pages don't repeat props. The field shell wraps its pages in a `VDefaultsProvider` that raises buttons and inputs to 48 px. The only custom components are the shared ones named in TRD §13.1 (`StatusChip`, `StationCard`, `MediaCapture` and `SignaturePad`) plus `SyncBadge` and `ConfirmDialog`, and all of them are built from Vuetify parts.

| Component | Vuetify base | Look | Rules |
| --- | --- | --- | --- |
| **Primary button** | `VBtn color="primary"` | Solid primary-600, white 14 px/500 text, 40 px tall (48 px in field mode, 18 px text), 6 px radius | One per view. Verb-first label (“Submit request”, “Sign and accept”). |
| **Secondary button** | `VBtn variant="outlined"` | White, 1 px primary-600 border, primary-600 text | Alternatives next to the primary (“Save draft”, “Preview PDF”) |
| **Text button** | `VBtn variant="text"` | No border; primary-600 text, underline on hover | Low-weight actions (“Cancel”, “Clear signature”) |
| **Danger button** | `VBtn color="error"` (Vuetify's `error` is the Danger red) | Solid `#B91C1C`, white text | Only on the final confirm of Deny, Cancel request, Reject work, Disable user, Revoke QR |
| **Icon button** | `VBtn icon variant="text"` | 40 px square (48 in field), surface-600 icon | Always has an `aria-label` and a `VTooltip` |
| **Text input, select, date** | `VTextField`, `VSelect` / `VAutocomplete`, `VDateInput` (`variant="outlined"`, `density="compact"`; `comfortable` in field) | 40 px tall (48 in field), white, 1 px surface-500 border, 6 px radius; focus = 2 px primary-600 ring | Label above in `text-label` as a plain `<label for>`, not Vuetify's floating label; helper text below in surface-600; mark optional fields “(optional)” rather than starring required ones |
| **Field error** | The input's `error-messages` | `#991B1B` text with `mdi-alert-circle-outline`; input border `#B91C1C` | Says what to do (“Use at least 10 characters”). A form with two or more errors also shows an error summary at the top, linked to each field. |
| **Status chip** (`StatusChip`) | `VChip` | Pill, 24 px tall, 12 px/500 text, 14 px icon, colours from the status tables | Never clickable on its own. The same component is used everywhere, including the map popup. |
| **Count badge** | `VBadge` | Red-700 dot with a white count on the bell; amber with a count on the sync badge | Shows “9+” over 9 (`max="9"`) |
| **Data table** | `VDataTableServer` (`VDataTable` for short client-side lists) | Header row surface-100, 12 px/500 surface-700 labels in sentence case; rows 48 px, 1 px surface-200 dividers, no zebra; hover surface-50; selected primary-50 | The reference column is in mono and links to the record. Status sits in column 2. Filters above the table as chips. Below `md`, each row becomes a stacked card. |
| **Card** | `VCard` | White, 1 px surface-200 border, 10 px radius, 24 px padding (16 on phones) | Title in `text-h3`; one optional action top-right |
| **Station card** (`StationCard`) | `VCard` | Station name + code (mono), status chip, country and time zone as text, no flags (“Jamaica · EST”), parameters as small grey tags, last visit date | Used in station lists on phones, the QR landing and the client dashboard |
| **Tabs** | `VTabs` + `VTabsWindow` | Underline style; active tab primary-600 text with 2 px underline | Station page (9 tabs) and request page (5). The strip scrolls sideways on phones (`show-arrows`) and the selected tab stays in view. |
| **Status timeline** | `VTimeline` | Vertical; each step is a dot in its status colour + label + date/time + actor | Request page right column (xl) or top of Overview (smaller screens). Future steps are hollow grey dots. |
| **Page banner** | `VAlert border="start"` | Full-width, 4 px left border in the feedback colour, icon, one sentence + one action | For page-level states: Client Review, “needs a connection”, signatures cleared, not prepared for offline. At most one per page. |
| **Toast** | `VSnackbarQueue` (one per app) | White card, 4 px left border in the feedback colour, `shadow-lg` | Top-right on desktop, above the bottom bar on phones. Success toasts close after 5 s; errors stay until dismissed. |
| **Dialog** | `VDialog`; confirmations use `ConfirmDialog` (a `VDialog` opened through a `useConfirm()` composable, because Vuetify has no confirm service) | 10 px radius, max 560 px, title `text-h2`; full-screen sheet on phones (`fullscreen` below `md`) | A destructive dialog names the record (“Deny MR-2026-0042?”) and has a required reason field when the PRD needs one |
| **Stepper** | `VStepper alt-labels` | Four steps: Before → Work → After → Review. Each is a numbered circle that is filled primary when done, ringed when current and grey when ahead. | Field visit only. The step label is always visible, not just the number, so the stepper never uses its `mobile` mode, which hides labels. |
| **Media capture** (`MediaCapture`) | `VCard` tiles over a native `<input type="file" capture>` | 2-column thumbnail grid on phones (4 on desktop); a large “+ Photo / video” tile first. Each tile has a phase tag (Before, During or After) and a sync dot. | Shows the count against the target (“3 Before photos”). Desktop drop zones elsewhere (attachments, Verify) use `VFileUpload`. |
| **Signature pad** (`SignaturePad`) | `signature_pad` in a `VCard` | White canvas at 3:1 ratio (full width), 1 px surface-500 border, surface-900 ink, baseline rule and “Sign here” placeholder; typed full name field; attestation checkbox with the exact wording | **Clear** text button under the canvas. The submit button is disabled until name, drawing and checkbox are all done. |
| **Sync badge** (`SyncBadge`) | `VBtn` + `VBadge` | Cloud icon. Green check when synced; amber count when waiting; spinning when syncing; red when failed. | Always on the rail (staff) and in the field app bar. Links to `/sync`. |
| **Empty state** | `VEmptyState` | Centred 48 px surface-500 icon, one `text-h3` line, one sentence, one primary or secondary button | Always offers the next action (AFD §6): “No open requests. **Report a problem**” |
| **Skeleton** | `VSkeletonLoader` | surface-200 blocks in the shape of the content | Used for loads over 300 ms; spinners only inside buttons and the sync badge |

## Iconography, imagery and data visualization

The app uses **Material Design Icons** (MDI), Vuetify's default set, in their outline variants. Real station photographs are the only imagery. Charts are drawn with ApexCharts, kept simple, and use the status colours only when they show statuses.

### Icons

- **One set only:** MDI, at 16 px inline, 20 px in buttons and menus, and 24 px in the field bottom bar and empty states. Use the `-outline` variant wherever one exists. Nothing is mixed in from other sets. If MDI lacks a glyph, the gap is filled with a single inline SVG drawn on the same 24 px grid.
- **SVG, not a font:** icons are imported one by one from `@mdi/js` (the name `mdi-map-marker-outline` becomes `mdiMapMarkerOutline`) and registered in `app/theme/icons.ts`. Only the icons used are bundled, and there is no icon font to load past the CSP or precache.
- **Icons sit next to words.** Icon-only buttons are allowed only on the rail, in tile headers and top bars, table row actions and media tiles, and each has a tooltip and `aria-label`.
- **Fixed meanings:** an icon always means the same thing everywhere.

| Meaning | Icon | Meaning | Icon |
| --- | --- | --- | --- |
| Station | `mdi-map-marker-outline` | Calibration | `mdi-tune-variant` |
| Request | `mdi-file-document-edit-outline` | Configuration | `mdi-cog-outline` |
| Visit | `mdi-car-outline` | Document / manual | `mdi-book-open-outline` |
| Visit report | `mdi-file-pdf-box` | Sensor / component | `mdi-chip` |
| Scan QR | `mdi-qrcode-scan` | Sync | `mdi-cloud-upload-outline` |
| Photo / video | `mdi-camera-outline` / `mdi-video-outline` | Signature | `mdi-signature-freehand` |
| Notifications | `mdi-bell-outline` | Audit / history | `mdi-history` |
| Map | `mdi-map-outline` | Internal comment | `mdi-eye-off-outline` |

### Imagery

- **Real stations only.** Use photographs of the organization’s own stations: the login panel, empty-state headers on the station page, and the station photo on each station page. No stock photos, illustrations or mascots.
- **Station photos** are cropped 4:3 with 10 px corners. A missing photo shows a surface-100 tile with a 32 px `mdi-map-marker-outline` and no placeholder art.
- **Visit media** keeps its own aspect ratio inside square thumbnails (`object-fit: cover`). A small tag in the top-left shows the phase (Before, During or After), and a play icon plus duration marks videos. The media viewer has a black background with capture time in station local time and the caption below.
- **Logo** (to be supplied, PRD Q1): it goes at the top of the rail (32 px tall), the login panel (48 px, reversed white) and the PDF header (12 mm tall). The PWA icon is a 512 px square mark on primary-600.

### Maps

- Leaflet with standard OpenStreetMap tiles. The OSM attribution stays visible.
- **Markers** are 28 px with a white 2 px outline, coloured and shaped by station status (see Colour palette). The selected station grows to 36 px.
- **Clusters** are primary-500 circles with a white count. Their size steps up at 10, 50 and 100 stations. A cluster does not show status; the legend says so.
- **Popup** uses `StationCard` (compact): name, code, status chip, open-request count and an “Open station” link.
- A **legend** is always visible in the bottom-left corner, showing the four statuses with shape, colour and word.

### Charts (dashboards and summary reports)

- **Default to a number before a chart.** Dashboard widgets are KPI tiles: a `text-kpi` number, a label and a link to the filtered list (“4 calibrations due →”). A chart is added only where trend or comparison is the point. Examples are request turnaround by month, technician workload, and station status by country.
- **Single-series charts use primary-500.** Charts of statuses (stations by status, requests by status) use the status colours in the same order as the status tables. Other comparisons use one hue and sort by value.
- **When categories are needed** (at most 5), use in this order: `#2F6DB5` blue, `#0F766E` teal, `#7C3AED` violet, `#B45309` amber and `#64748B` slate. Every series also gets a direct label, because a colour key alone isn’t enough.
- Gridlines are surface-200 and axis text is 12 px surface-600 (dark values under Colour palette). The ApexCharts toolbar, zoom and legend toggles are turned off, and animation is off when the user asks for reduced motion. Bar corners are square, with no 3D, shadows or donut charts. Numbers use tabular figures.
- PDF summary reports draw their charts with ApexCharts too (TRD §11.1), always in the light palette, so a chart looks the same on screen and on paper.

## Screen-by-screen design direction

Every page follows the same order from the top: **title and status, then the one main action, then content.** The tables below give each of the 37 AFD pages its shell, its layout and its single primary button. A dash means the page has no primary action.

**Figure 2 — Request page, desktop, staff view.** The request page leads with reference, status and the one next action.

```text
+------------------------------------------------------------------------------+
| Requests / MR-2026-0042                                                      |
| MR-2026-0042 · Rain gauge not reporting      [Assign staff] [Schedule visit] | (1) (2)
| (Assigned) (High)  Client organization · Jamaica · 2 stations                |
|                                                                              |
| | Assigned to 2 technicians. Schedule a visit to move it forward.            | (3)
|                                                                              |
| Overview   Comments   Visits   Reports   History                             | (4)
| ========                                                                     |
| Category      Fault                         | Status                         |
| Stations      WXR-012, WXR-019              |  *  Submitted         14 Oct   |
| Submitted     14 Oct 2026, 09:12 EST        |  *  Approved          15 Oct   |
| Description   ~~~~~~~~~~~~~~~~~~~~~~~~~~    |  @  Assigned          15 Oct   | (5)
|               ~~~~~~~~~~~~~~~~~~~~~~~~~~    |  o  Scheduled                  |
|               ~~~~~~~~~~~~~~                |  o  In progress                |
|                                             |  o  Client Review              |
|                                             |  o  Closed                     |
+------------------------------------------------------------------------------+
```

1. Header: reference and title, status and priority chips, organization, country, stations.
2. One primary action for the current status (**Schedule visit**); other actions are outlined.
3. At most one page banner, for the current state.
4. Tabs: Overview · Comments · Visits · Reports · History.
5. Status timeline in the right column on xl screens; it moves above Overview on smaller screens. `*` done, `@` current, `o` future (hollow grey).

The request page sets the pattern for the other detail pages (station, visit and sensor unit): identity and status at the top, then the next action, then tabs. The field Work step is drawn in the shells mock-up above.

### Public pages (split-panel shell)

| Page | Route | Layout and look | Primary action |
| --- | --- | --- | --- |
| Log in | `/login` | Form card: email, password with show/hide, “Forgot password?” text link, then “Create an account” as a secondary link under a divider. The reason banner (session ended, password changed) sits above the form. | Log in |
| Register | `/register` | One column. Name, email, phone, password (live rule check: “10+ characters”), and “Your organization” as a text field (`VTextField`, hint: “We’ll link your account to it”); there is no list of existing organizations on a public page | Register |
| Waiting for approval | `/register/pending` | Centred card with a 48 px `mdi-clock-outline` in amber, “We’ll email you when your account is approved”, and the email used | — |
| Forgot password / Set new password / Accept invitation | `/forgot-password`, `/reset-password/:token`, `/invite/:token` | Short single-field forms. An expired link shows a warning banner with **Send a new link**. | Send link / Save |
| QR landing | `/s/:token` | Shown only while resolving: logo + spinner + “Opening station…”. A revoked code gets a card with `mdi-qrcode-remove` and a link to Stations. | — |
| Verify a report | `/verify` | Drop zone for the PDF or a hash field. The result is a large success or danger banner naming the report number and version. | Verify |
| Unlock | `/unlock` | Centred card: avatar initials and name of the cached staff user, “Enter your PIN to open your field work”, a 6-box PIN input (`VOtpInput`, numeric keypad, 48 px boxes), the wrong-attempt count after a miss, and a text link “Log in as someone else” (needs signal). After five misses the input is replaced by a warning banner: “Connect to the internet and log in to continue. Your work is saved on this phone.” | Unlock |

### Dashboards (`/dashboard`, one per role)

A dashboard is a grid of KPI tiles above lists. Each tile is a number that links to a filtered list. There are no charts on the technician or client dashboards.

| Variant | Top row (KPI tiles) | Below | Primary action |
| --- | --- | --- | --- |
| Client | Our stations by status (4 small tiles, status colours) | Requests awaiting our review (amber banner if any), Open requests (table, 5 rows), Upcoming visits, Recent reports | Report a problem (in the view header) |
| Technician | My assigned · Queue · My upcoming visits · Waiting to sync · Reports to finalize | Two columns: My upcoming visits (cards with **Ready offline** chip) and My reports to finalize | — |
| Admin | Registrations pending · Requests awaiting approval · Unassigned queue · In Client Review · Calibrations due/overdue · Failed calibrations | Open requests by status (bar chart in status colours), station status by country (table with chips), upcoming visits, reports awaiting finalization | — |
| Viewer | As admin | As admin, with all action links removed (links to lists stay) | — |

Tiles with a count above zero that need action (pending registrations, overdue calibrations, failed calibrations) get a 4 px left border in amber or red. A tile with zero stays plain.

### Shared pages (app shell)

| Page | Route | Layout and look | Primary action |
| --- | --- | --- | --- |
| Stations list | `/stations` | Filter bar (organization\*, country, type, status, parameter) over a table: code (mono), name, status chip, organization\*, country, last visit, calibration due chip. Cards on phones. A List / Map toggle sits top-right. | New station\* |
| Station page | `/stations/:id` | Header: name, code (mono), status chip, country · time zone, photo thumbnail on the right. Then the 9 tabs (Overview · Sensors · Documents · Configurations\* · Requests · Visits · Reports · Calibration · History\*). Overview is a 2-column definition list plus a small map. Clients see a summary with fewer tabs. | Staff: Start visit (when one is scheduled) · Client: Report a problem |
| Map | `/map` | Full-bleed map in the view; the filters sit in the pane, and the status legend bottom-left. On phones, filters open in a bottom sheet. | — |
| Requests list | `/requests` | Status filter as a horizontal chip group with counts (“Client Review 2”), then the table: reference (mono), title, status chip, priority (only High and Urgent shown), stations, organization\*, assigned\*, updated | New request (admin) / Report a problem (client) |
| New request | `/requests/new` | One-column form, max 720 px, in three fieldsets: **Stations** (multi-select with station chips), **Problem** (title, description, category as a segmented `VBtnToggle`, priority), **Attachments** (drop zone). Admins get an Organization picker first. | Submit request |
| Request page | `/requests/:id` | Header: reference (mono) + title, status chip, priority chip, organization, stations as links, and assigned staff by name (shown to clients too). One page banner for the current state (“Waiting for your review”). Then 5 tabs (Overview · Comments · Visits · Reports · History\*). The status timeline is in the right column on xl screens. Admin decision buttons (Approve, Deny, Assign staff) sit in the header. | Depends on status: Approve\* · Schedule visit\* · Review and sign off (client) |
| Comments tab | (tab) | Flat thread, oldest first, each with avatar initials, name, role tag and time. Internal comments have an amber-50 background, a `mdi-eye-off-outline` icon and the label “Internal — not visible to client”. The composer sits at the bottom with an **Internal** toggle (staff). | Post |
| Review and sign off | `/requests/:id/review` | Focused page, max 880 px: summary of the work, final visit reports (cards with **Open PDF**), a media strip, then a decision card with two clear choices: **Accept work** (opens the signature card) and **Reject** (opens a reason field). | Sign and accept |
| New client report | `/requests/:id/client-reports/new` | First a choice of two large option cards: “Upload a PDF” and “Fill in the online form”. The form has a sticky footer with **Save draft** and **Submit**. | Submit |
| Visit page | `/visits/:id` | Header: visit number, status chip, dates (station local time), attending staff by name (lead marked with a star; clients see names only, no contact details), **Ready offline** chip. Below are station sections, each with its owner's name (“Recorded by Devon Brown”), arrival/departure times, a media grid by phase, and the work record summary. Lead and admins get a **Change owner** text button per station. | Prepare for field · Start visit · Continue visit (by state) |
| Media viewer | `/visits/:id/media/:mediaId` | Black full-screen, the image or video centred. Prev/next arrows and a counter (“7 of 42”). The caption, phase, station and capture time are shown below. | — |
| Visit report | `/visit-reports/:id` | Two panes on lg screens. On the left, the editor: narrative fields as auto-saving text areas, a photo picker and a facts summary with **Fix in work record** links. On the right, a live A4 preview with a DRAFT watermark. Signatures are listed at the bottom with a status. The version selector shows Draft / Final / Superseded. While finalizing, the editor is read-only and the Finalize button shows progress; a failed finalize returns to Draft with a warning banner and **Try again**. | Sign → Finalize (lead) · Download PDF (final) |
| Summary reports | `/reports` | On the left, a list of report types with one-line descriptions. On the right, filters and **Generate**. Below is a table of generated reports with a status (Building with progress, Ready, Failed) and download buttons. | Generate |
| Notifications | `/notifications` | A list grouped by Today, Yesterday and Earlier. Unread rows have a primary-50 background and a dot. Each row has an icon by type, one line of text, and a time. | Mark all as read |
| My profile | `/profile` | Sections for Details, Password, Time zone, Appearance (Light · Dark · System) and Email preferences (a switch per notification type; account emails locked on); the pane lists the sections and jumps to each | Save |

\* Staff only; hidden for clients and viewers.

### Staff and admin pages (app shell, staff sections)

| Page | Route | Layout and look | Primary action |
| --- | --- | --- | --- |
| Queue | `/queue` | Table of approved, unassigned requests, oldest first: reference, title, organization, country, priority, age (“3 days”) | Claim (per row) |
| Sensors | `/sensors` | Two tabs, Models and Units. The units table has serial (mono), model, status chip, station, calibration due chip. Units flagged for review have an amber `mdi-flag-outline`. | New model / New unit |
| Sensor unit | `/sensors/units/:id` | Header: serial (mono, large), model, status chip. Then an installation history timeline and a calibration records table with readings in tabular figures; certificates link to PDFs. | Record calibration |
| Calibration due | `/calibration` | A segmented filter (Overdue · Due in 30 days · All) and a table sorted by due date, with overdue rows first and their date in red | Export CSV |
| Registrations | `/admin/registrations/:id?` | The pane lists pending accounts (name, organization they typed, when). Choosing one opens it in the view: details, the organization match and approve or reject. With none chosen, the view shows how many are waiting. | Approve |
| Users / Organizations | `/admin/users`, `/admin/organizations` | Standard tables with role tags and status chips. Edit happens in a side drawer. | Invite user / New organization |
| Checklist templates | `/admin/checklists` | List of templates on the left. On the right, an editor where items can be dragged into order, with a version number and “Published” chip. | Publish version |
| QR labels and station import | `/admin/stations-tools` | Two cards. **Labels** has a station picker and a preview of the A4 sheet layout. **Import** is a 3-step wizard: upload, map columns, review errors. | Print labels / Import |
| Settings | `/admin/settings/:part?` | The pane lists the parts: **Appearance** (the admin's own Light / Dark / System, and Animations on or off on this device) and **Brand colours** (for everyone). Brand colours shows the theme in use as a small app shell in light and dark, then an editor with three tabs: From one colour (a colour picker that makes both themes), Colour by colour (the main roles of each scheme, or all 49) and JSON. Upload a Material Theme Builder file or download the current one. Edits preview on the admin's screen only; a sticky bar saves for everyone or discards; contrast problems show as a warning first. | Save for everyone |
| Audit log | `/admin/audit` | Dense full-width table (40 px rows, 13 px text): time, actor, action, resource, organization. Filters sit above. A row opens a drawer with a before/after diff in mono (removed lines on red-50, added on green-50). | Export CSV |

### Field pages (field shell, phones)

| Page | Route | Layout and look | Primary action |
| --- | --- | --- | --- |
| Field visit | `/visits/:id/field` | List of the visit’s stations, each a large card showing progress (“Before ✓ · Work … · After –”) and its owner; the user's own stations come first. A station owned by someone else opens with an info banner (“Owned by Devon Brown. You can add photos and videos.”), its work record read-only and the media capture tile still active. Inside a station is the 4-step stepper. **Before** and **After** are the media grid with a large capture tile. **Work** is the checklist as big OK / Fixed / Issue / N/A segmented buttons per item, then sensor actions as cards. **Review** is a summary with any missing photos flagged. | Arrive → Next → Depart station → End visit (sticky action bar) |
| QR scanner | `/scan` | Full-screen camera with a 240 px square guide and a torch toggle. “Enter code manually” text link at the bottom. | — |
| Sync status | `/sync` | A big status line at the top (“5 changes and 18 files waiting”, or “All synced” with a green check). Then a storage bar and a per-item list with progress bars; paused items show “Will resume”. Items the server couldn't apply (owner changed, visit cancelled, report final) sit in a “Needs attention” group at the top with the reason in plain words and an **Export** button. An Appearance switch (Light · Dark · System) sits at the bottom of the page. | Sync now |
| Not found | (any) | Centred `mdi-magnify` icon, “We can’t find that page”, and a link to the dashboard. The wording is the same for missing and forbidden records (AFD §5.2). | Go to dashboard |

### PDF reports and email

- **Visit report, close-out report, client form and summaries (A4):** Inter 10 pt body, 16 pt title. The header has the logo, report name, number (mono) and version. Tables have surface-100 headers and 0.5 pt surface-300 rules. Status words appear as text in the same colours, without pills. A DRAFT or SUPERSEDED diagonal watermark is 72 pt in surface-200. The footer has “Page x of y”, the generated date and the hash in mono.
- **Email:** a single 600 px column, white, with the logo at the top and one primary-600 button (“Review the work”). It uses a system font stack, because web fonts are unreliable in email, and a plain-text version is always sent.

## Accessibility and interaction standards

Every core screen meets **WCAG 2.2 AA** (NFR-11). Field mode goes further on touch size and contrast, because it is used outdoors. Each rule below is checked by axe in Playwright (TRD §14) or in a manual review before release.

| Area | Standard | How AWS-MMS meets it |
| --- | --- | --- |
| Text contrast | 4.5:1 normal, 3:1 large (1.4.3) | All tokens checked in both themes (Colour palette). The lightest text is surface-600 (built-in 9.34:1 in light, 10.12:1 in dark); the Brand colours editor warns before saving a theme that falls under 4.5:1. Field mode uses the strongest text colour only. axe runs in both themes. |
| UI contrast | 3:1 for borders, icons, focus (1.4.11) | Input borders surface-500 (4.76:1). Focus ring primary-600 (7.33:1). In dark: borders 4.39:1 and a primary-300 focus ring at 8.34:1. Status markers have a white outline on the map. |
| Colour alone | Never the only signal (1.4.1) | Chips pair an icon with a word. Map markers differ by shape. Chart series have direct labels. Errors pair an icon with text. |
| Focus | Visible and not hidden (2.4.7, 2.4.11) | A 2 px primary-600 ring with a 2 px white offset on every focusable element. Sticky bars never cover the focused field, because pages scroll it into view with padding. |
| Target size | 24 px minimum (2.5.8) | 40 px on desktop and 48 px in field mode, with at least 8 px between adjacent targets |
| Dragging | Single-pointer alternative (2.5.7) | Checklist template reordering also has up/down buttons. The signature pad is exempt, because the drawing is the content, but it has a typed-name equivalent. |
| Keyboard | Everything operable (2.1.1) | Vuetify's built-in keyboard support for tables, tabs, menus and dialogs, checked by hand on each new screen. A skip link goes to main content. Dialogs trap focus and return it on close. |
| Forms | Labels, errors, help (3.3.1–3.3.3, 3.3.7) | Visible labels (never placeholder-only). The error summary links to fields. Entered data is never cleared on an error. Data already given is not asked for again (for example the station is pre-filled from QR). |
| Authentication | No cognitive test (3.3.8) | Password managers and paste are allowed, there is no CAPTCHA puzzle, and a show/hide toggle is provided |
| Status updates | Announced (4.1.3) | Toasts, sync progress and live status changes use `aria-live="polite"`. Errors use `assertive`. |
| Zoom and reflow | 200% zoom, 320 px reflow (1.4.4, 1.4.10) | rem-based type, and tables reflow to cards below 640 px, so there is no horizontal scroll except inside wide data tables |
| Motion | Respects user setting (2.3.3) | All transitions and GSAP tweens are off under `prefers-reduced-motion` or with Settings › Animations off, and nothing auto-plays. Videos start paused. Rail tooltips appear on hover and keyboard focus, stay while hovered and close with Escape (1.4.13). |
| Media | Alternatives | Every visit photo has its caption (or “Before photo, Station WXR-012, 14:05 AST”) as alt text. Video thumbnails state their duration. |

### Interaction patterns

- **Saving:** Text that is long or can be lost (report narrative, client report form, work record) saves automatically, with “Saved · 14:05” shown next to the title. Short forms save on the button.
- **Offline:** Online-only actions (approve, sign, create request, admin) stay visible but are disabled, with a “Needs a connection” tooltip and a page banner. Field actions never wait for the network.
- **Destructive actions:** Two steps every time: the button, then a dialog naming the record with a required reason where the PRD needs one. There is no undo, so the dialog wording says what can’t be reversed.
- **Feedback timing:** Clicks respond within 100 ms (pressed state). Loads over 300 ms show a skeleton. Long jobs (summary reports, PDF render, sync) show progress, not a spinner.
- **Lists:** Default sort is newest-updated first, except the queue (oldest first) and calibration due (soonest first). Filters persist per user in the URL so links can be shared.

## Voice and microcopy

The app talks like a capable colleague: short, plain and specific. It says what happened and what to do next. All text is in English (NFR-14).

| Do | Don’t |
| --- | --- |
| “Report a problem” | “Create maintenance request ticket” |
| “Start visit”, “Sign and accept” | “Proceed”, “Submit” on its own, “OK” |
| “Saved on this phone. It will sync when you have signal.” | “Offline mode: data queued in IndexedDB” |
| “Email or password is incorrect” | “Invalid credentials (401)” |
| “This visit isn’t ready for offline use. Prepare it now while you have signal.” | “Warning! Bundle not cached!” |
| “No open requests. Report a problem” | “No data” |
| “MR-2026-0042 approved” (toast) | “Success!” |
| “station” in all screen text | “AWS”, which readers may take for Amazon Web Services; keep it for the product name only |

- **Buttons** start with a verb and name the object when it isn’t obvious (“Deny request”, not “Deny”, in a dialog).
- **Clients** see plain terms: “your stations”, “the visit”, and the technician by name (“Devon Brown visits on 21 Oct”). Staff screens can use trade terms (logger, firmware, RH, BP).
- **References** (`MR-…`, `VR-…`) always appear in mono and are never shortened.
- **Status names** are written exactly as in PRD §5 (“Client Review”, “In progress”), the same on chips, filters, emails and PDFs.
- **No exclamation marks, emoji or blame** (“You entered…” becomes “This field needs…”).

## Open questions

| # | Question | Decision or assumption |
| --- | --- | --- |
| D1 | Brand colours, logo and product name shown in the app (PRD Q1) | **Logo and name supplied 2026-10-17:** the MARS-MMS mark and wordmark in `/logo` (vector SVGs `logo.svg` and `logo_main.svg`, also usable in PDFs), shown in the app as “MARS-MMS”; the PWA icon is the mark on primary-600. **Brand colours decided 2026-10-17 (W4-12):** a Material 3 theme, built in from `frontend/src/app/theme/material-theme.json` (seed `#026D88`) and replaceable by admins for everyone on Settings › Brand colours. Status colours stay fixed. The PWA icon and manifest colours come from the built-in theme (`npm run brand`); an admin's theme changes the app, not an installed icon. |
| D2 | Is a dark theme needed in v1? | **Decided 2026-10-16: yes.** Light and dark themes ship in v1, with Light / Dark / System on My profile (System is the default). See Colour palette › Dark theme. |
| D3 | Which chart library is used on dashboards and in PDFs? | **Decided 2026-10-16: ApexCharts.** `vue3-apexcharts` in the app. Summary-report PDFs render the same chart options to SVG in headless Chromium in the report worker (TRD §11.1). |
| D4 | Should the client see the assigned technician’s name (AFD A7)? | **Decided 2026-10-16: yes.** Clients see assigned and attending staff by name on the request and visit pages. Names only, with no email or phone. |
| D5 | Are station photos available for the login panel? | One approved photo is supplied with the branding. If none, a plain primary-950 panel with the logo is used. |
| D6 | Does any client need a language other than English? | No. Copy is kept in one strings file so translation can be added later. |
