---
name: MARS Visit Board
colors:
  surface: '#ffffff'
  background: '#eaeef2'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f0f4f7'
  surface-container: '#eaeef2'
  surface-container-high: '#e4e9ec'
  surface-container-highest: '#dee3e6'
  on-surface: '#171c1f'
  on-background: '#171c1f'
  on-surface-variant: '#40484c'
  outline: '#70787c'
  outline-variant: '#c0c8cc'
  primary: '#0a6780'
  on-primary: '#ffffff'
  primary-container: '#b9eaff'
  on-primary-container: '#004d62'
  secondary: '#40484c'
  on-secondary: '#ffffff'
  tertiary: '#0a6780'
  on-tertiary: '#ffffff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  note-container: '#fff3b0'
  on-note-container: '#7a5c00'
  task-container: '#d3f2da'
  on-task-container: '#1b6b34'
  recommendation-container: '#ffdcd8'
  on-recommendation-container: '#a8251b'
  config-container: '#eadfff'
  on-config-container: '#61389a'
  warning-container: '#fef3c7'
  on-warning-container: '#92400e'
typography:
  display-lg:
    fontFamily: Google Sans
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Google Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 26px
  headline-sm:
    fontFamily: Google Sans
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 21px
  body-lg:
    fontFamily: Roboto Flex
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-md:
    fontFamily: Roboto Flex
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Roboto Flex
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
  kind-label:
    fontFamily: Roboto Flex
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 14px
    letterSpacing: 0.06em
  mono:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
rounded:
  sm: 0.375rem
  DEFAULT: 0.625rem
  md: 0.625rem
  lg: 0.875rem
  full: 9999px
spacing:
  tile-gap: 5px
  margin: 1.5rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

MARS-MMS is the maintenance app of an organization that runs automatic weather stations on Earth, for clients in several Caribbean countries (Jamaica, Barbados, Trinidad). "MARS" is only the product's name: nothing in it relates to the planet Mars, space, habitats, rovers, missions or sci-fi. Every place, photo and word is about ordinary weather stations: masts, rain gauges, sensors, loggers, solar panels, enclosures, by the sea or in the hills. Technicians use it on site, on phones in bright sun, often with no signal; office staff use it on laptops. This design system is for one feature: the **visit board**, where a technician records everything that happened at a station during a visit as coloured sticky notes of four kinds: Note, Task, Recommendation and Config.

The look is calm, precise and practical, like a well-kept site logbook. Most of the screen is white and quiet grey. The only strong colours are the primary teal-blue for actions and the four sticky-note tints, which tell the kinds apart at a glance. Density is balanced: a daily work tool, not a dashboard and not a landing page. Motion is minimal.

Two layouts exist, and every screen uses one of them:

- **Desktop app shell** (1280 x 900 web screens): three tiles on a light grey ground (#EAEEF2), 5px apart and 5px from the window edge. A 64px **rail** of section icons on the left, a 340px **pane** with the section's tabs and a list, and the **view**, which fills the rest. Tiles are white with 10px corners, no border and no shadow.
- **Phone field shell** (390 x 844 mobile screens): a 56px top app bar (back arrow, station name, a small line under it, a sync badge), the content in one column with 16px side margins, and a 64px bottom bar with four labelled items: Visit, Scan, Stations, Sync.

## Colors

- **Ground** (#EAEEF2) sits behind the tiles of the desktop shell. **Tiles and sheets** are white (#FFFFFF). **Insets** such as text fields and file lists use pale grey (#F0F4F7); quiet chips use #EAEEF2.
- **Text** is near-black blue-grey (#171C1F). **Secondary text**, labels and metadata are #40484C. Hairline dividers are 1px #C0C8CC, used between list rows and under headers only.
- **Primary** teal-blue (#0A6780, white text) is for the main button, links, the active tab underline and focus rings. **Primary container** (#B9EAFF, text #004D62) marks the selected list row, the active filter chip, the active rail icon and tonal buttons. There is no second accent.
- **Sticky-note colours** belong to board elements only, never to anything else. Each kind has an accent (a 4px top edge on its white card, the kind's icon and its label) and a pale tint (the header band of its open sheet and its swatch in the Add menu; never the card itself):
  - Note: tint #FFF3B0, accent #7A5C00 (yellow)
  - Task: tint #D3F2DA, accent #1B6B34 (green)
  - Recommendation: tint #FFDCD8, accent #A8251B (red)
  - Config: tint #EADFFF, accent #61389A (purple)
  Body text on a tint stays #171C1F; secondary text on a tint stays #40484C. All of these pass WCAG AA.
- **Warnings** (for example, incomplete tasks in the End visit dialog) use #FEF3C7 with #92400E text. **Errors** use #FFDAD6 with #93000A text.
- Never use the sticky-note colours for buttons, headings or icons outside a board element. Never use pure black, gradients (one exception: a person's initials avatar may use a teal gradient from #0A6780 to #5AA9C4), neon or glows.

### Dark theme

Dark mode ships, so each screen may also be asked for in dark. Keep the same layout and swap the colours:

- Ground #0A0F11; tiles and sheets #171C1F; insets #1B2023; quiet chips #252B2D; hairlines #40484C.
- Text #DEE3E6; secondary text #C0C8CC.
- Primary #89D0ED with text #003544; primary container #004D62 with text #B9EAFF.
- Sticky-note tints and accents: Note #3B3414 / #F2D35B, Task #173A23 / #7FD99A, Recommendation #45201C / #FF9C92, Config #2E2343 / #CDB3FA. Body text on a tint #F1F5F9.
- Warning #4A3A12 with #FDE7B5 text; error #4A1B18 with #FDDCD9 text.

## Typography

- **Titles** (page titles, sheet titles, sticky-note titles, section headings): Google Sans, semibold. If Google Sans is not available, use Google Sans Flex, then Roboto Flex.
- **Everything else**: Roboto Flex, 14 to 15px, line height 1.45.
- **References and file names** (visit and request numbers such as VR-2026-0038-01 and MR-2026-0038, station codes such as JM-KIN-001, serial numbers, file names such as KIN_main_v4.2.CR1, code): JetBrains Mono, 12 to 13px.
- **Kind labels** on sticky notes and sheets ("NOTE", "TASK", "RECOMMENDATION", "CONFIG"): 11px, bold, uppercase, 0.06em letter spacing, in the kind's accent colour, always next to the kind's icon.
- Hierarchy comes from size, weight and the secondary text colour, not from boxes. Labels are small and muted; values are dark.
- Never use a serif font.

## Layout & Spacing

- **Desktop view tile**: a header 72px high (title, then a line of chips and the request reference, the actions on the right), a row of station tabs (plain text, the active one in primary with a 2px underline and a small muted second line), then the body with 24px side padding.
- **The board**: a row of filter chips with counts (All, Notes, Tasks, Recommendations, Config), then a grid of sticky notes, newest first. 3 columns in the desktop view, 1 column on a phone, 14px gaps. No dragging and no free canvas.
- **Sheets** (an element opened): a dialog over a dark scrim on desktop (560px for a Note or Recommendation, 720px for a Task or Config, which show Before and After side by side); a full-screen sheet on a phone.
- **Phone**: 16px side margins, 12px between sticky notes, a floating "Add" button 56px high, 16px above the bottom bar, bottom right.
- Touch targets are at least 44px everywhere; task checkboxes sit in 48px rows.

## Elevation & Depth

Flat. Tiles have no shadow. Sticky notes have no shadow at rest. Only things that float get a soft shadow: open menus, dialogs, sheets and the floating Add button. The scrim behind a dialog is the background at about 40% darkness.

## Shapes

- Tiles: 10px corners. Sticky notes: 10px corners with a 4px top edge in the kind's accent. Dialogs and sheets: 14px corners (24px at the top of a phone bottom sheet).
- Buttons and fields: 8px corners. Small chips: 6px corners. Filter chips: fully rounded. Thumbnails: 6 to 8px corners.
- No pill-shaped main buttons. No circles behind icons except avatars and the floating play button on a video.

## Components

- **Sticky note** (a whole tappable white card, 1px hairline border, 10px corners, a 4px top edge in the kind's accent, no shadow): in order, the kind's icon and uppercase kind label in the accent (with an optional detail on the right of that line: "High" for a high-priority recommendation, "Complete" with a check for a finished task); the title in Google Sans 16px semibold, up to two lines; up to two lines of description in secondary text; for a task, a thin progress bar in the accent with "2 of 3"; a footer line with a small thumbnail and "4 files", a small grey chip "Shared" or "Staff only", and the author's initials avatar on the right.
- **Element sheet**: a header band in the kind's tint (kind icon and label, close button, the title in Google Sans 22px, a muted line "Author · Station · time"), then the body on white: Title and Description fields, the kind's own part, the file sections, a "Share with client" switch with one line of explanation, and a footer with a quiet "Delete" on the left and "Done" on the right.
  - Task: a checklist of 48px rows (checkbox filled with the accent when ticked, the item text, a small muted line "Name · time" under ticked items, up and down buttons to reorder), an "Add item" field with a tonal button, then **Before** and **After** sections side by side.
  - Recommendation: a Priority segmented control (Low, Medium, High), and a tonal button "Create a request from this"; once made, it reads "Request MR-2026-0051" as a link.
  - Config: **Before** and **After** sections that list files as rows (a square type badge in the config tint with the extension, such as CR1, PY, PDF, TXT; the file name in mono; the size; a state on the right: Ready, Checking, a progress bar, or Refused), plus photos.
- **File section**: a heading ("Photos and video", "Before", "After") with a count on the right, a grid of 4:3 thumbnails, and an outlined "add" tile ("Photo or video", or "File, photo or video" for Config). An upload in progress shows the percent, the file name and a thin progress bar in its tile.
- **File viewer** (inside the sheet, never a new tab): a top bar with a back button naming the element and the file name on the right. Photos and video sit on black with previous and next buttons, a "2 of 3" counter and the caption and capture time below. A PDF shows its pages on grey with page count and zoom. A text or code file shows in JetBrains Mono with line numbers. Any other file shows a large type badge, the name, size and a Download button.
- **Filter chip**: 32px high, fully rounded, outlined; the active one filled with the primary container and no outline; a count in smaller text after the label.
- **Add menu** (desktop): a primary "Add" button with a plus icon opens a menu of the four kinds, each with a 36px square swatch in its tint showing its icon, the kind's name in bold and one line of explanation. On a phone the same list is a bottom sheet.
- **Banners**: one sentence with an icon, on pale primary for information, warning colours for warnings, error colours for errors.
- **Buttons**: primary (solid #0A6780, white text), tonal (primary container), outlined (1px hairline, primary text) and text buttons. One primary button per screen or dialog.
- **Icons**: Material Design Icons, outline style: note-text-outline (Note), checkbox-marked-outline (Task), lightbulb-on-outline (Recommendation), file-cog-outline (Config), plus image, video, file, download, close, arrow-left, chevrons, plus, delete-outline, information-outline, wifi-off.

## Voice

Plain, short and direct, in British-style dates and 24-hour times ("Tue 14 Oct", "08:12 EST"). Use these words: Note, Task, Recommendation, Config, board, visit, station, Before, After, Share with client, Staff only, Add, Done, End visit. Say "Saved · 09:12" next to text that saves itself. Errors say what happened and what to do ("This was changed on another device. Here is the saved copy."). Offline says "This needs a connection".

Keep the data identical on every screen:

- Visit VR-2026-0038-01, request MR-2026-0038 "Modem offline since Friday", status Started, today from 07:30.
- Stations: Kingston Harbour (JM-KIN-001, owned by you, Andrea Clarke, arrived 08:12 EST) and Montego Bay Airport (JM-MBJ-002, owned by Devon Brown).
- People: Andrea Clarke (AC, lead) and Devon Brown (DB).
- Kingston Harbour's board (7 elements): Task "Replace the RH sensor" (2 of 3, 4 files, Shared); Recommendation "Replace the guy wires next quarter" (High, 2 photos, Shared); Note "Water inside the enclosure" (3 files, Staff only); Config "Logger program 4.2" (1 before, 1 after, Staff only); Task "Clean the rain gauge funnel" (Complete, 2 of 2, Shared); Task "Check the solar charge controller" (0 of 4, uploading 1 of 2, Shared); Note "Gate lock replaced by harbour staff" (no files, Shared).
- The client's view: the ended visit VR-2026-0031-01 "Annual inspection", Tue 14 Oct.

## Banned

Anything about the planet Mars, space or sci-fi (habitats, rovers, sectors, missions, relays, "operational feeds", telemetry overlays on photos); a top app header bar above the desktop shell (the rail holds the logo); invented badges, codes or verification claims ("Verified checksum", "PDF/A verified", "E2E encrypted", "ACTIVE", "LOG #892", "SECTOR-04", "EST 20M", "REV-A"); words on photos; a "Cancel" next to "Done" in a sheet that saves as you type; status colours (amber, red, green chips) for things that are not a status; sticky notes filled with their tint (a sticky note is a white card; only its top edge, icon and label carry the colour); emoji; serif fonts; Inter or Plus Jakarta Sans; gradients other than avatars; glows, neon or blur; shadows on tiles or sticky notes; sticky-note colours used outside board elements; red and green as the only way to tell kinds apart (the icon and label are always there); a free canvas or dragging; cards inside cards; decorative icon circles; pill-shaped main buttons; more than one primary button per screen; placeholder names (John Doe, Acme) or invented statistics; technical jargon such as "payload", "entity" or "artifact"; claims of certifications or standards.
