# Google Stitch prompts: the visit board

Upload `DESIGN.md` (this folder) as the project's design system first. Then paste one prompt per screen. Prompts marked **Web** are desktop screens at 1280 x 900; prompts marked **Mobile** are phone screens at 390 x 844. Each prompt is self-contained, so Stitch does not need to remember earlier screens, but they share the same data and wording.

After a screen is made, ask for its dark version with prompt D at the end.

---

## 1. The board (Web)

```
Desktop web app screen, 1280 x 900, following DESIGN.md. The desktop app shell: three white tiles with 10px corners on a light grey ground (#EAEEF2), 5px apart.

Left rail tile, 64px wide: a round teal logo at the top, then three outline icons stacked: dashboard, clipboard (Work, active, on the pale primary container), map marker (Stations).

Pane tile, 340px wide: heading "Work"; three small round tabs "Queue", "Requests", "Visits" (Visits active); a search field "Search visits"; a list of three visit rows, each a bold line and a muted line with a small grey chip:
- "VR-2026-0042-01 · Rain gauge reads zero" / chip "Planned", "Tomorrow 08:00 to Thu 16:00"
- "VR-2026-0038-01 · Modem offline since Friday" / chip "Started", "Today 07:30" (this row is selected: pale primary background)
- "VR-2026-0031-01 · Annual inspection" / chip "Ended", "Last Tue"

View tile, the rest of the width:
- Header: title "VR-2026-0038-01" in Google Sans 20px; below it a pale primary chip "Started", the text "Modem offline since Friday" and "MR-2026-0038" in mono. On the right one primary button "End visit".
- Station tabs (plain text, active one teal with a 2px underline): "Kingston Harbour" with the small line "Owned by you · 7 on the board" (active), and "Montego Bay Airport" with "Owner Devon Brown · 2 on the board".
- A row: fully rounded outlined filter chips "All 7" (active, filled pale primary), "Notes 2", "Tasks 3", "Recommendations 1", "Config 1"; on the right, muted "Arrived 08:12 EST", an outlined small button "Depart" and a primary button "Add" with a plus icon.
- A muted line with an info icon: "Shared notes are shown to the client when the visit ends."
- A 3-column grid of seven sticky notes, newest first. Each sticky note is a white card with a 1px hairline border, 10px corners and a 4px top edge in its kind's accent colour, no shadow: kind icon and uppercase kind label in the accent, a Google Sans 16px title, two lines of muted description, then a footer with a small thumbnail, a file count, a small grey chip and the author's initials avatar (teal gradient circle).
  1. Green Task "Replace the RH sensor", "Reads 100% since Friday. Swap for the spare and send the old unit for repair.", a thin green progress bar "2 of 3", footer "4 files", chip "Shared", avatar AC.
  2. Red Recommendation "Replace the guy wires next quarter", "High" with an up arrow at the right of the kind line, "Corrosion on all three anchors, worst on the north side. Safe for now.", footer "2 photos", "Shared", DB.
  3. Yellow Note "Water inside the enclosure", "Desiccant used up. The seal is cracked on the hinge side.", footer video thumbnail, "3 files", chip "Staff only", AC.
  4. Purple Config "Logger program 4.2", "Adds the new RH channel. Before: version 4.1 as found on the logger.", footer with a file icon, "1 before · 1 after", "Staff only", AC.
  5. Green Task "Clean the rain gauge funnel", "Complete" with a check at the right of the kind line, "Leaves and a wasp nest in the funnel.", full progress bar "2 of 2", "2 photos", "Shared", DB.
  6. Green Task "Check the solar charge controller", "Battery at 11.6 V at 08:00.", empty progress bar "0 of 4", footer "Uploading 1 of 2" with a tiny progress bar, "Shared", AC.
  7. Yellow Note "Gate lock replaced by harbour staff", "New key held at the harbour office, not in the key box.", footer "No files", "Shared", AC.
```

## 2. The board with the Add menu open (Web)

```
The same desktop visit board screen as before (VR-2026-0038-01, Kingston Harbour, seven sticky notes), following DESIGN.md, with the "Add" button's menu open below it on the right. The menu is a white panel, 340px wide, 12px corners, a soft shadow, holding four rows. Each row has a 36px square swatch in the kind's tint with the kind's icon in its accent and a 3px accent edge on top, then the kind's name in bold and one muted line:
- Note (yellow): "Something you saw, with photos or video" (this row is hovered, on pale grey)
- Task (green): "Work to do, with a checklist and before and after photos"
- Recommendation (red): "Work the client should plan for, with a priority"
- Config (purple): "Logger or modem files, before and after a change"
```

## 3. Note sheet (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: the visit board dimmed behind a dark scrim, and a centred dialog 560px wide, 14px corners, white, soft shadow.

Dialog header band in the Note tint (#FFF3B0) with a 4px accent top edge: the note icon and "NOTE" in the accent (#7A5C00), a close button on the right; the title "Water inside the enclosure" in Google Sans 22px; a muted line "Andrea Clarke · Kingston Harbour · today 08:31 EST".

Body on white:
- Field "Title" with "Water inside the enclosure".
- Field "Description" (multi-line, pale grey) with "Desiccant used up. The seal is cracked on the hinge side; replacement ordered.", and below it a small check and "Saved · 08:33".
- Section "Photos and video" with "3 files" on the right: a 4-column grid of 4:3 thumbnails: two photos (grey blocks with an image icon), one video with a round play button and "0:22", and an outlined add tile "Photo or video" with a plus. A muted line: "Opening one shows it here, in this sheet."
- A hairline, then a switch (off) "Share with client" with the muted line "Off for notes. Shared notes are shown to the client when the visit ends."

Footer: a quiet text button "Delete note" with a bin icon on the left, a text button "Done" on the right.
```

## 4. Recommendation sheet (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: the visit board dimmed behind a dark scrim, and a centred dialog 560px wide.

Header band in the Recommendation tint (#FFDCD8) with a 4px red accent top edge (#A8251B): the lightbulb icon and "RECOMMENDATION", a close button; the title "Replace the guy wires next quarter"; the muted line "Devon Brown · Kingston Harbour · today 09:05 EST".

Body:
- "Priority": a segmented control "Low", "Medium", "High" with High selected (pale primary).
- "Description": "Corrosion on all three anchors, worst on the north side. Safe for now; replace before the hurricane season."
- "Photos and video" with "2 photos, 1 on its way": two photo thumbnails, one tile uploading ("62% IMG_2251.JPG" and a thin progress bar), and an add tile.
- Switch on: "Share with client", muted "On for recommendations. The client sees it, with its priority, when the visit ends."
- Section "Follow-up": a tonal button "Create a request from this" with a plus; under it a pale grey row with a check: "Once made, the button becomes the link: Request MR-2026-0051" (the reference is a link); a muted line "Opens the request form with the station, title and description filled in. Needs a connection."

Footer: "Delete" on the left, "Done" on the right.
```

## 5. Task sheet, being filled in (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: the board dimmed behind a scrim, and a dialog 720px wide.

Header band in the Task tint (#D3F2DA) with a 4px green accent edge (#1B6B34): the checkbox icon and "TASK", a close button; the title "Replace the RH sensor"; muted "Andrea Clarke · Kingston Harbour · today 08:20 EST · saved 09:12"; a thin green progress bar with "2 of 3 done".

Body:
- "Description": "Reads 100% since Friday. Swap for the spare and send the old unit for repair."
- "Checklist": three 48px rows separated by hairlines. Each row: a checkbox (ticked ones filled green with a white check), the item text, and up and down arrow buttons on the right.
  1. Ticked: "Fit the spare RH sensor, serial V-23044", small muted "Andrea Clarke · 08:56".
  2. Ticked: "Check the reading against the reference: 78% and 77%", "Andrea Clarke · 09:10".
  3. Not ticked: "Record the swap on the Sensors page".
  Below: a field with a teal focus ring holding "Label the old unit for repair" and a tonal button "Add item".
- Two sections side by side: "Before" (2 files: a photo and a video "0:18", plus an add tile) and "After" (2 photos, plus an add tile).
- Switch on: "Share with client", muted "On for tasks. The client sees the task, its checklist and photos when the visit ends."

Footer: "Delete task" on the left, "Done" on the right.
```

## 6. Task sheet, complete and read only (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: the board dimmed behind a scrim, and a dialog 440px wide, as seen by someone who did not write it.

Header band in the Task tint with the green accent edge: "TASK", on the right a check and "Complete" in green, a close button; the title "Clean the rain gauge funnel"; muted "Devon Brown · completed 09:40 EST".

Body:
- A pale primary banner with an info icon: "Only Devon Brown or the station's owner can change this."
- The description as plain text: "Leaves and a wasp nest in the funnel."
- Two ticked checklist rows (no reorder buttons): "Clear the funnel and the filter" / "Devon Brown · 09:31", and "Tip test: 10 tips logged for 2 mm" / "Devon Brown · 09:40".
- "Before" with one photo and "After" with one photo, side by side.
- A muted line "Shared with the client".

Footer: a single text button "Close" on the right.
```

## 7. Config sheet (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: the board dimmed behind a scrim, and a dialog 720px wide.

Header band in the Config tint (#EADFFF) with a 4px purple accent edge (#61389A): a cog icon and "CONFIG", a close button; the title "Logger program 4.2"; muted "Andrea Clarke · Kingston Harbour · today 09:20 EST".

Body:
- "Description": "Adds the new RH channel and moves the scan to 10 s. Before: version 4.1 as found on the logger."
- Two columns side by side.
  "Before", muted "As found": a list of file rows in a hairline-outlined box, each row a 36px square badge in the config tint with the extension, the file name in mono, the size below it, and a state on the right:
  - "CR1" "KIN_main_v4.1.CR1" "18 KB" "Ready" (teal)
  - "TXT" "modem_settings.txt" "2 KB" "Ready"
  Then one photo thumbnail, and an outlined button "File, photo or video".
  "After", muted "What the station runs now":
  - "CR1" "KIN_main_v4.2.CR1" "19 KB" "Ready"
  - "PY" "rh_offset.py" "4 KB" "Checking" (muted)
  - "PDF" "wiring_RH_channel.pdf" "1.2 MB of 2.1 MB" with a small progress bar
  - a red alert badge, "setup.exe", "Programs that run on a computer can't be added.", "Refused" in red
  Then the outlined button "File, photo or video".
- A pale grey note with an info icon: "When the visit ends, the After files become the station's next configuration version. Changing them later adds another version; a version never changes."
- Switch off: "Share with client", muted "Off for configuration files."

Footer: "Delete" on the left, "Done" on the right.
```

## 8. Config sheet, after the visit ended (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: the board dimmed behind a scrim, and a small dialog 420px wide. Header band in the Config tint with the purple accent edge: "CONFIG", close button, title "Logger program 4.2", muted "After the visit ended". Body: a pale primary row with a check: "The After files are configuration version 6 of Kingston Harbour." where "configuration version 6" is a link; then a muted paragraph "The station's Configurations tab lists it with the visit it came from. Its files can be compared with version 5 there."
```

## 9. Opening a photo (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: a dialog 720px wide over the dimmed board, showing a photo inside the Note sheet. Top bar: a back button with an arrow "Water inside the enclosure" in primary on the left, muted "Photo" on the right. The photo area is black, the photo centred (a calm grey placeholder with an image icon), a small dark counter "2 of 3" at the top centre, round translucent previous and next buttons at the sides. Below on white: the caption "Cracked seal on the hinge side" and a muted line "Taken 08:24 EST · Andrea Clarke".
```

## 10. Playing a video (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: a dialog 720px wide over the dimmed board, showing a video inside the Task sheet. Top bar: back button "Replace the RH sensor", muted "Before · video" on the right. A black area with the video frame (a grey placeholder), and under it a dark control bar: pause icon, "0:06", a thin progress bar about one third full, "0:18". Below on white: caption "Logger reads 100% RH" and the muted line "Plays here, in place".
```

## 11. Reading a PDF (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: a dialog 720px wide over the dimmed board, showing a PDF inside the Config sheet. Top bar: back button "Logger program 4.2", the file name "wiring_RH_channel.pdf" in mono on the right. A thin toolbar: "Page 1 of 4" on the left; on the right square buttons for zoom out, "100%", zoom in, and download. Below, a grey area with white A4 pages stacked and centred: page one titled "RH channel wiring, CR1000" with lines of text and a simple wiring diagram box, the top of page two below it.
```

## 12. Reading a code file (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: a dialog 720px wide over the dimmed board, showing a Python file inside the Config sheet. Top bar: back button "Logger program 4.2", the file name "rh_offset.py" in mono on the right. The file on a pale grey panel in JetBrains Mono 13px with muted line numbers 1 to 9 on the left; keywords in the config accent (#61389A), strings in the task accent (#1B6B34), the comment in muted grey:

# RH offset for the HMP155 on channel 3
OFFSET = -1.2

def corrected(raw):
    value = raw + OFFSET
    return min(100.0, max(0.0, value))

if __name__ == "__main__":
    print(corrected(78.9))

A footer line: muted "Shown as text · 4 KB" and a small outlined "Download" button.
```

## 13. A file with no preview, and no signal (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md, showing two dialogs side by side over the dimmed board, each 480px wide with a back button "Logger program 4.2" at the top.
Left, a file with no preview: centred, a 64px square badge in the config tint with "CR1" in the purple accent, the name "KIN_main_v4.2.CR1" in mono, the muted text "19 KB. This kind of file can't be shown here. Download it to open it in LoggerNet.", and a primary button "Download" with a download icon.
Right, a PDF with no signal: centred, a 64px grey square with a wifi-off icon, the bold line "This needs a connection", the muted text "PDFs and text files open when you have signal. Photos and video you took on this phone still show.", and an outlined button "Try again".
```

## 14. End visit (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: the visit board dimmed behind a scrim and a centred dialog 560px wide titled "End VR-2026-0038-01?" in Google Sans 20px.
- A warning banner (#FEF3C7, text #92400E, alert icon): "2 tasks are not complete. You can still finish them after the visit ends, until the report is finalized."
- Two rows on the Task tint with 8px corners: "Replace the RH sensor · Kingston Harbour" with "2 of 3" in green on the right, and "Check the solar charge controller · Kingston Harbour" with "0 of 4".
- "Is another visit needed?" with two outlined radio options "Yes" and "No" (No selected, teal ring).
- A pale primary info banner: "Ending shares 5 elements with the client and makes configuration version 6 of Kingston Harbour from Logger program 4.2."
- Footer: a text button "Go back" and a primary button "End anyway".
```

## 15. End visit refused: a file still being checked (Web)

```
The same End visit dialog as before, following DESIGN.md, after pressing "End anyway": above the footer an error banner (#FFDAD6, text #93000A, alert icon): "Wait a moment for 1 file. rh_offset.py on Logger program 4.2 is still being checked. Try again in a minute." with the file name in mono. The buttons stay "Go back" and "End anyway".
```

## 16. Edge states of the board (Web)

```
Desktop web screen, 1280 x 900, following DESIGN.md: a light grey ground with four white panels in a 2 x 2 grid, each with a small uppercase muted caption at the top.
1. "Empty board": centred, a 56px grey square with a note icon, the bold line "Nothing recorded at this station yet", the muted line "Add a note, a task, a recommendation or configuration files as you work.", and a primary button "Add" with a plus.
2. "Loading, then failed": two grey skeleton blocks the shape of sticky notes, then an error banner "We couldn't load the board. Check your signal, then try again." and an outlined button "Try again".
3. "Saved on another device": an error banner "This was changed on another device. Here is the saved copy. What you typed is kept below so you can copy it."; a yellow sticky-note style block "Water inside the enclosure" / "Saved by Andrea Clarke on the office PC, 10:05"; a pale grey block "Your version" / "Desiccant used up; seal cracked on the hinge side and the top."; buttons "Discard mine" (text) and "Edit the saved copy" (primary).
4. "Deleted, and offline": a pale primary banner "This was deleted. Devon Brown deleted it at 10:12. Nothing you change here will be saved."; a pale grey banner with a wifi-off icon "Create a request needs a connection. The recommendation is saved; make the request when you have signal."
```

## 17. The client's board (Web)

```
Desktop web app screen, 1280 x 900, following DESIGN.md, as a client sees it. The app shell: rail with dashboard, map marker (Stations) and clipboard (Requests, active); pane "Requests" with tabs "Requests" and "Visits" (active) and two rows: "VR-2026-0042-01 · Rain gauge reads zero" / "Planned", "Tomorrow 08:00", and "VR-2026-0031-01 · Annual inspection" / "Ended", "Tue 14 Oct" (selected).
View: title "VR-2026-0031-01", a grey chip "Ended", "Annual inspection", "MR-2026-0031" in mono. No buttons. Station tabs "Kingston Harbour" / "3 shared" (active) and "Port Antonio" / "1 shared". A small definition list: "Attended by" Andrea Clarke (lead), Devon Brown; "At the station" 08:12 to 11:40 EST, Tue 14 Oct. A muted line "What the team recorded at this station. Open one to see its photos and video."
A 3-column grid of three sticky notes, read only (no Shared or Staff only chips):
- Green Task "Replace the RH sensor", "Complete", "The sensor read 100% since Friday. Replaced with a calibrated spare.", full bar "3 of 3", footer thumbnail "4 files · Andrea Clarke".
- Red Recommendation "Replace the guy wires next quarter", "High", "Corrosion on all three anchors. Safe for now; replace before the hurricane season.", footer "2 photos · Request MR-2026-0051".
- Green Task "Check the solar charge controller", "2 of 4", "Battery charging normally. Two checks wait for the next visit.", half bar, "1 photo · Devon Brown".
```

## 18. The board on a phone (Mobile)

```
Mobile app screen, 390 x 844, following DESIGN.md: the phone field shell.
Top app bar: back arrow, "Kingston Harbour" in bold with the small muted line "Board · arrived 08:12" under it, and a pale primary badge "3 to sync" on the right.
Below, 16px margins: a row of rounded filter chips that scrolls sideways: "All 7" (active), "Notes 2", "Tasks 3", "Recommendations 1".
Then one column of sticky notes (white cards with a hairline border, 10px corners, a 4px top edge in the kind's accent, no shadow):
- Green Task "Replace the RH sensor", green progress bar "2 of 3", footer "4 files" and a grey chip "Shared".
- Red Recommendation "Replace the guy wires next quarter" with "High" at the right of the kind line, footer "2 photos", "Shared".
- Yellow Note "Water inside the enclosure", "Desiccant used up. The seal is cracked on the hinge side.", footer "3 files", "Staff only".
- Purple Config "Logger program 4.2" (partly cut off by the bottom bar).
A floating primary button "Add" with a plus, 56px high, 16px corners, bottom right above the bottom bar.
Bottom bar, 64px plus the home indicator, with labels: "Visit" (active, teal and bold), "Scan", "Stations", "Sync".
```

## 19. Adding on a phone (Mobile)

```
Mobile app screen, 390 x 844, following DESIGN.md: the phone board dimmed behind a scrim, and a white bottom sheet with 24px top corners and a small grab handle, titled "Add to the board". Four 64px rows, each with a 44px square swatch in the kind's tint showing its icon in the accent (3px accent edge on top), then the name in bold and a muted line:
- Note: "Something you saw, with photos or video"
- Task: "A checklist, with before and after photos"
- Recommendation: "Work the client should plan for"
- Config: "Logger or modem files, before and after"
```

## 20. A task on a phone (Mobile)

```
Mobile app screen, 390 x 844, following DESIGN.md: a full-screen sheet for a task.
Header band in the Task tint (#D3F2DA) with a 4px green top edge, under the status bar: "TASK · 2 of 3" with the checkbox icon in green, a close button on the right; the title "Replace the RH sensor" in Google Sans 22px; the muted line "Saved on this phone · 09:12".
Body, 16px margins:
- Three 52px checklist rows with hairlines: ticked "Fit the spare, serial V-23044", ticked "Check the reading: 78% and 77%", not ticked "Record the swap on the Sensors page". Ticked boxes are filled green with a white check.
- "Before · 2" with two 4:3 photo thumbnails in a row; "After · 1" with one.
- A full-width tonal button 48px high with a camera icon: "Add an After photo".
```

## 21. Adding a photo to a section on a phone (Mobile)

```
Mobile app screen, 390 x 844, following DESIGN.md: the full-screen task sheet "Replace the RH sensor" dimmed behind a scrim, and a bottom sheet titled "Add to After" with three 64px rows, each with a 40px round pale primary icon:
- camera: "Take a photo" / "Opens the camera"
- video camera: "Record a video" / "Up to about 2 minutes works best"
- images: "Choose from your phone" / "Photos and videos"
```

## 22. A photo full screen on a phone (Mobile)

```
Mobile app screen, 390 x 844, following DESIGN.md: a photo opened from the task "Replace the RH sensor". A black screen with a slim top bar: a white back arrow and "Replace the RH sensor", and "1 of 2" on the right. The photo fills the width in the middle (a calm grey placeholder). At the bottom on black: the caption "New sensor fitted" in white and a muted line "Taken 08:58 EST · Andrea Clarke". No other buttons.
```

## 23. End visit on a phone (Mobile)

```
Mobile app screen, 390 x 844, following DESIGN.md: a full-screen sheet titled "End VR-2026-0038-01?" with a close button. A warning banner (#FEF3C7, text #92400E): "2 tasks are not complete. You can still finish them after the visit ends." Two rows on the Task tint: "Replace the RH sensor" with "2 of 3", "Check the solar charge controller" with "0 of 4". "Is another visit needed?" with two large radio rows "Yes" and "No" (No selected). A pale primary note: "Ending shares 5 elements with the client." At the bottom, a full-width primary button "End anyway" 52px high and a text button "Go back" above it.
```

---

## D. Dark version of any screen

```
Make a dark version of this screen with the same layout and content, using the "Dark theme" colours in DESIGN.md: ground #0A0F11, tiles and sheets #171C1F, insets #1B2023, hairlines #40484C, text #DEE3E6, secondary text #C0C8CC, primary #89D0ED with dark text #003544, primary container #004D62 with text #B9EAFF. Sticky-note tints and accents: Note #3B3414 / #F2D35B, Task #173A23 / #7FD99A, Recommendation #45201C / #FF9C92, Config #2E2343 / #CDB3FA, with body text #F1F5F9 on the tints. No pure black except behind photos and video.
```
