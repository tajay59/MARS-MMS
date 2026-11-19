---
name: MARS-MMS
description: The field logbook for weather-station maintenance; calm in the office, readable on a hillside, official when signed.
colors:
  caribbean-depth: "#0A6780"
  on-caribbean-depth: "#FFFFFF"
  caribbean-depth-container: "#B9EAFF"
  on-caribbean-depth-container: "#004D62"
  caribbean-depth-50: "#DEF4FF"
  caribbean-depth-700: "#004D62"
  harbour-slate: "#4C626B"
  dusk-lavender: "#5B5B7E"
  ground: "#EAEEF2"
  tile: "#FFFFFF"
  ink: "#171C1F"
  ink-secondary: "#40484C"
  ink-muted: "#70787C"
  rule: "#DEE3E6"
  rule-strong: "#C0C8CC"
  surface-50: "#F0F4F7"
  danger: "#BA1A1A"
  danger-container: "#FFDAD6"
  success: "#15803D"
  success-container: "#DCFCE7"
  warning: "#B45309"
  warning-container: "#FEF3C7"
  status-submitted: "#FFFFFF"
  status-approved: "#E0F2FE"
  status-assigned: "#DBEAFE"
  status-scheduled: "#E0E7FF"
  status-in-progress: "#EDE9FE"
  status-client-review: "#FEF3C7"
  status-reopened: "#FFEDD5"
  status-closed: "#DCFCE7"
  status-denied: "#FEE2E2"
  status-cancelled: "#E2E8F0"
  station-operational: "#15803D"
  station-degraded: "#B45309"
  station-offline: "#B91C1C"
  station-decommissioned: "#64748B"
  sticky-note: "#FFF3B0"
  on-sticky-note: "#7A5C00"
  sticky-task: "#D3F2DA"
  on-sticky-task: "#1B6B34"
  sticky-recommendation: "#FFDCD8"
  on-sticky-recommendation: "#A8251B"
  sticky-config: "#EADFFF"
  on-sticky-config: "#61389A"
typography:
  display:
    fontFamily: "Google Sans Variable, Roboto Flex Variable, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: "2.375rem"
  headline:
    fontFamily: "Google Sans Variable, Roboto Flex Variable, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: "1.75rem"
  title:
    fontFamily: "Google Sans Variable, Roboto Flex Variable, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: "1.5rem"
  kpi:
    fontFamily: "Google Sans Variable, Roboto Flex Variable, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: "2.5rem"
    fontFeature: "\"tnum\""
  body:
    fontFamily: "Roboto Flex Variable, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: "1.5rem"
  body-sm:
    fontFamily: "Roboto Flex Variable, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: "1.25rem"
  label:
    fontFamily: "Roboto Flex Variable, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: "1.25rem"
  caption:
    fontFamily: "Roboto Flex Variable, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: "1rem"
  field-action:
    fontFamily: "Roboto Flex Variable, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: "1.5rem"
  mono:
    fontFamily: "JetBrains Mono Variable, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: "1.25rem"
rounded:
  tile: "0px"
  md: "6px"
  card: "10px"
  rail-icon: "12px"
  full: "9999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "6": "24px"
  "8": "32px"
  "12": "48px"
  tile-gap: "5px"
components:
  button-primary:
    backgroundColor: "{colors.caribbean-depth}"
    textColor: "{colors.on-caribbean-depth}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  button-primary-field:
    backgroundColor: "{colors.caribbean-depth}"
    textColor: "{colors.on-caribbean-depth}"
    typography: "{typography.field-action}"
    rounded: "{rounded.md}"
    height: "48px"
  button-secondary:
    backgroundColor: "{colors.tile}"
    textColor: "{colors.caribbean-depth}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    height: "40px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.on-caribbean-depth}"
    rounded: "{rounded.md}"
    height: "40px"
  input:
    backgroundColor: "{colors.surface-50}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    height: "40px"
  card:
    backgroundColor: "{colors.tile}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "24px"
  status-chip-in-progress:
    backgroundColor: "{colors.status-in-progress}"
    textColor: "#5B21B6"
    typography: "{typography.caption}"
    rounded: "{rounded.full}"
    height: "24px"
  pane-row-selected:
    backgroundColor: "{colors.caribbean-depth-50}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    height: "72px"
  rail-icon-active:
    backgroundColor: "{colors.caribbean-depth-container}"
    textColor: "{colors.caribbean-depth-700}"
    rounded: "{rounded.rail-icon}"
    size: "48px"
  sticky-note-card:
    backgroundColor: "{colors.tile}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "16px"
---

<!-- Derived from the built app (frontend/src/app/theme/) on 2026-11-19. docs/DBD.md is the binding source: where this file and DBD disagree, DBD wins and this file is regenerated with /impeccable document. Colours here are the built-in Material 3 theme in light mode; admins can replace the brand colours for everyone (W4-12), never the status, feedback or sticky colours. -->

# Design System: MARS-MMS

## Overview

**Creative North Star: "The Field Logbook"**

MARS-MMS is the book a technician carries up the hill and the record a client signs at the end. It has to survive the field: no signal, sun on the screen, wet or gloved hands, a visit recorded over days before it syncs. And it has to read as official once it is signed. The look is a well-kept logbook: plain ruled pages, a clear hand, and colour only where something needs attention.

The office sees a dense, quiet instrument: three square tiles on a grey ground, a rail of section icons, a pane with the list, a view with the record. The field sees the same book opened wide, with 48 px targets, 16 px text and one main action per screen. Clients see roomier pages in plain words. Records (references, serials, hashes, signed reports) take a print-like, monospaced, versioned form, because an auditor will read them.

It is not a weather app. No animated clouds, glossy icons, stock illustrations or decorative gradients; the only gradient is a person's avatar.

**Key Characteristics:**
- Tonal, flat surfaces: tiles stand out from the ground by colour alone.
- Status first: every record shows its status as a chip with an icon and a word.
- Colour is reserved: status colours mean status, sticky tints mean board kinds, the brand blue-teal means "act here".
- Three typefaces with three jobs: Google Sans titles, Roboto Flex text, JetBrains Mono for anything someone might copy.
- Field mode scales up, never redesigns: same components at 48 px.

## Colors

A cool slate logbook page with one deep blue-teal ink for action, and a strictly reserved set of status colours.

### Primary
- **Caribbean Depth** (`caribbean-depth`): primary buttons, links, the focus ring, the selected tab's underline, the active rail fill's icon. The built-in Material 3 seed (#026D88) gives it; an admin can replace it.
- **Caribbean Shallows** (`caribbean-depth-container`, `caribbean-depth-50`): the active rail icon and pane tab fill, a selected list row. Never a background for whole sections.

### Secondary
- **Harbour Slate** (`harbour-slate`): Material's secondary; used with Dusk Lavender only in person-avatar gradients (tones 30 to 40).

### Tertiary
- **Dusk Lavender** (`dusk-lavender`): the avatar gradient's other end. Nowhere else.

### Neutral
- **Ground Grey** (`ground`): behind the app shell's tiles (dark: the lowest surface container).
- **Page White** (`tile`): tiles, cards, dialogs, sticky notes.
- **Ruled Line** (`rule`, `rule-strong`): 1 px dividers inside tiles and card borders; the stronger one around sticky notes and inputs that need an edge.
- **Faint Fill** (`surface-50`): filled inputs, row hover.
- **Logbook Ink** (`ink`): all primary text; field pages use only this.
- **Pencil** (`ink-secondary`): secondary text, hints, meta. Always at full strength, never by opacity.
- **Faded Pencil** (`ink-muted`): icons in empty states, outlines.

### Status (reserved)
- **Request status** (`status-*` with their `on-status-*` text): chips, the timeline, nothing else. Submitted is white with a border; the rest are pale fills with dark text.
- **Station status** (`station-*`): map markers and station chips; the same colours in dark mode, because markers sit on light map tiles.
- **Feedback** (`success`, `warning`, `danger` and their containers): banners, toasts, field errors, the final confirm of a destructive action.
- **Sticky tints** (`sticky-*` with `on-sticky-*`): the visit board's four kinds (Note yellow, Task green, Recommendation red, Config purple), as a 4 px top edge, icon and label, and the open sheet's header. Only on board elements.

### Named Rules
**The Reserved Ink Rule.** A status colour appears only where it states a status. If removing the colour would lose no information, it was decoration: take it out.

**The Theme-Proof Status Rule.** Status, feedback and sticky colours never come from the Material theme, so no admin's brand change can make two statuses look alike.

## Typography

**Display Font:** Google Sans (variable), falling back to Roboto Flex
**Body Font:** Roboto Flex (variable), falling back to system-ui
**Label/Mono Font:** JetBrains Mono (variable), falling back to ui-monospace

**Character:** Google Sans gives titles and KPI numbers a Material voice; Roboto Flex stays legible at 12 to 16 px on a phone in sunlight; JetBrains Mono keeps 0/O and 1/l/I apart in serials like `HMP155-K1230045`. All three are self-hosted and precached: the CSP blocks font CDNs and the field works offline.

### Hierarchy
- **Display** (600, 30/38 px; 24/32 on phones): the page or record title.
- **Headline** (600, 20/28 px): section headings, dialog titles.
- **Title** (600, 16/24 px): card titles, tab panel and form section headings, sticky-note titles (two lines).
- **KPI** (600, 32/40 px, tabular figures): dashboard numbers.
- **Body** (400, 16/24 px): paragraphs, inputs, comments; reading text at most 75 characters wide.
- **Body small** (400, 14/20 px): table cells, list meta, menu items on staff desktop.
- **Label** (500, 14/20 px): form labels, chip and button text.
- **Caption** (500, 12/16 px): timestamps, badge counts. The smallest size allowed.
- **Field action** (600, 18/24 px): primary buttons in the field shell (Arrive, Depart station, End visit).
- **Mono** (500, 14/20 px): `MR-2026-0042`, `VR-2026-0042-02`, serials, config versions, short hashes.

### Named Rules
**The Sentence Case Rule.** Headings, buttons and menu items are in sentence case. The only capitals are DRAFT and SUPERSEDED watermarks.

**The Copyable Is Mono Rule.** Anything a person might read aloud, copy or compare (a reference, a serial, a hash, a file name) is in JetBrains Mono; nothing else is.

**The Upright Rule.** No italics for emphasis; use 600 weight. Numbers in tables, readings and dates use tabular figures and right-align.

## Layout

Three frames, and only their content changes. The **app shell** (staff and clients) is three square tiles on the ground colour, 5 px apart and 5 px from the window edge: the rail (64 px), the interactive pane (300 px on tablets, 360 px, 420 px from 1536 px; hideable from 1024 px) and the view (the rest; reading width at most 1080 px, tables and maps full width). There is no app-wide top bar. Below 1024 px the rail becomes a translucent bottom bar (surface at 85% with a backdrop blur), and below 768 px the pane and view go full bleed, one after the other. The **field shell** (phones during a visit) is a 56 px app bar, the page with 16 px gutters, and a 64 px bottom bar plus the safe area. **Public pages** use a split panel: 40% dark primary with the logo and one photograph, 60% a white form card at most 440 px wide.

Spacing is on a 4 px grid (4, 8, 12, 16, 24, 32, 48). Breakpoints are in px and match Vuetify's thresholds: 640, 768, 1024, 1280, 1536. Staff pages may be dense; client pages are roomy.

### Named Rules
**The One Primary Rule.** Each view has one primary button. Alternatives are outlined; low-weight actions are text.

**The Frame Stays Put Rule.** Never add a top bar, a floating panel or a second navigation to a shell. A page fills the view with its header and body and puts its list or controls in the pane.

## Elevation & Depth

Flat by default, tonal by structure. Tiles are separated from the ground by colour only: no border, no shadow, no radius. Inside a tile, sections are separated by 1 px rules, never by nested bordered cards. Shadows belong only to things that float above the page: menus, dialogs, toasts, the field action bar and the bottom bar's soft upward edge.

### Shadow Vocabulary
- **Float low** (`box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)`): tooltips and small menus.
- **Float mid** (`box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)`): menus, popovers.
- **Float high** (`box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)`): dialogs, toasts, the field action bar.

### Named Rules
**The No Cards In Tiles Rule.** A tile never holds a bordered card. Cards are for public pages, dialogs, menus and sticky notes.

## Shapes

Square where the structure is, softly rounded where a hand touches. The shell's tiles and tables have no radius. Inputs, buttons and tooltips have gently curved corners (6 px); cards, dialogs, sticky notes and list rows a little more (10 px); rail icons 12 px; chips, badges and pane tabs are fully round. Message-style rows in the pane (72 px, 48 px avatar) round fully when open. Borders are 1 px; the one heavier edge is a sticky note's 4 px top stripe or a banner's 4 px left stripe, in its kind's or feedback's colour.

## Components

Vuetify components used as they come, styled once through global defaults; Tailwind does layout. No ripple anywhere.

### Buttons
- **Shape:** gently curved (6 px).
- **Primary:** Caribbean Depth fill, white 14 px/500 text, 40 px tall; 48 px with 18 px/600 text in the field shell. Verb-first labels ("Submit request", "Sign and accept").
- **Hover / Focus:** a 150 ms ease-out tint; the focus ring is a 2 px Caribbean Depth outline 2 px out.
- **Secondary:** page white with a 1 px Caribbean Depth border and text.
- **Text:** no border, Caribbean Depth text, underline on hover ("Cancel", "Clear signature").
- **Danger:** the danger red with white text, only on the final confirm of Deny, Cancel request, Reject work, Disable user, Revoke QR.

### Chips
- **Style:** pill, 24 px tall, 12 px/500 text, a 14 px icon, the status's pale fill with its dark text.
- **State:** never clickable on their own (StatusChip). Filter chips above lists and the board carry counts.

### Cards / Containers
- **Corner Style:** 10 px.
- **Background:** page white.
- **Shadow Strategy:** none; see Elevation.
- **Border:** 1 px ruled line.
- **Internal Padding:** 24 px (16 px on phones).

### Inputs / Fields
- **Style:** filled (a faint fill), no border, 6 px corners, 40 px tall (48 in the field); label above as a plain label, hint below in Pencil at full strength; optional fields say "(optional)".
- **Focus:** the shared 2 px focus ring.
- **Error / Disabled:** error text in the danger container's dark red with an alert icon; a form with two or more errors adds a linked summary at the top.

### Navigation
- **Rail:** 64 px tile, one icon per section, a CSS tooltip on hover and keyboard focus, a dot for something waiting. The active fill is one 12 px-rounded tile in Caribbean Shallows that slides to the chosen section.
- **Bottom bar (below 1024 px and in the field):** four sections and Me; labels always shown at 12 px; the open section has no fill, its icon and bold label in Caribbean Depth with a dot below.
- **Tabs:** underline style, the active tab in Caribbean Depth with a 2 px underline; the strip scrolls sideways on phones.

### Sticky note (signature component)
A white card with a 1 px ruled border, 10 px corners, no shadow, and a 4 px top stripe in its kind's accent. Icon and kind label in the accent, the title in Google Sans 16 px (two lines), two lines of description in Pencil, then the kind's detail (a task's "2 of 3" with a progress bar, a recommendation's priority, Config's file count), and a footer with the file count, "Shared" or "Staff only" and the author's initials. The whole card opens the element sheet; the title alone is its name. One column on phones, two from 640 px, three from 1024 px.

### Sync badge (signature component)
A cloud icon on the rail and in the field app bar: a green check when synced, an amber count when work is waiting, spinning while syncing, red when it failed. It is always visible in the field, because the user must be able to see that nothing is lost.

## Do's and Don'ts

### Do:
- **Do** take every colour from a token (`bg-primary`, `text-surface-600`); Tailwind's default palette is removed.
- **Do** keep field pages at 48 px targets, 16 px or larger text and the strongest ink only.
- **Do** show every status as a chip with an icon and a word, so colour is never the only signal.
- **Do** give secondary text full-strength Pencil, never reduced opacity; text meets 4.5:1 in light and dark.
- **Do** separate sections inside a tile with 1 px ruled lines.
- **Do** keep motion short (150 ms hovers, 200 ms dialogs; the shell's GSAP motion through `dur()`), and off under reduced motion or Settings › Animations off.

### Don't:
- **Don't** use decorative gradients; the person avatar is the only exception.
- **Don't** use stock illustrations or weather-app theatrics (animated clouds, glossy icons).
- **Don't** use a status, feedback or sticky colour for decoration, or a brand colour for a status.
- **Don't** put bordered cards inside the app shell's tiles, or shadows on anything that does not float.
- **Don't** add custom component CSS when a Vuetify default or Tailwind utility can do it.
- **Don't** use italics for emphasis or title case in UI text.
