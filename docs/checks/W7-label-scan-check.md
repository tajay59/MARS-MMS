# W7 exit check: scanning a printed label on real phones

IP Phase 2 exit criterion (QR-2): a printed label is scanned by an iPhone and an Android camera. The scanner's decoding is tested in Vitest; this check proves the parts only a phone can: the camera loop, the torch, the permission prompt and the installed app.

**Status:** Android not run. iPhone postponed (run the same sheet later; the iPhone column is there for that).

## Before you start

- Staging: `https://rnd.yanacreations.com`. You need an admin to print and a staff account (technician) to scan. A client account is optional (step 7).
- Check on the staging host that `REPORT_APP_URL` in `infra/.env` is `https://rnd.yanacreations.com`. A label holds that address, so a wrong value prints codes that open the wrong site.
- Chrome on the Android phone, up to date. Install the app from Chrome's menu (Install app) for the "installed" rows, and keep a normal Chrome tab for the "browser" rows.
- Light: scan indoors under normal light first, then dim the room for the torch step.

## 1. Print the sheet (desktop, as admin)

1. Sign in, open **Admin › Station tools** (`/admin/stations-tools`).
2. Pick 3 to 10 stations (include one at a client organization), leave the phone number blank to use the default, and make the sheet.
3. Open the PDF. Check: 10 labels per A4 page (2 × 5), black on white, the code and the station name readable, a QR square.
4. Print at 100% (not "fit to page"). Measure one label: 98 × 55 mm.
5. Note which station each label belongs to.

Record: sheet job time, printer, paper, any label that looks wrong.

## 2. The phone's own camera app (outside our app)

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| 2.1 | Point the stock camera at a label | A banner for `https://rnd.yanacreations.com/s/…` appears | | |
| 2.2 | Tap it while signed out | Opens the app on the log in page; after logging in you land on that station (the `next` parameter) | | |
| 2.3 | Scan again while signed in | Opens the station page directly | | |
| 2.4 | Scan from 15 cm, 30 cm, 50 cm; at an angle; in dim light | Reads at every distance a person would hold a phone | | |

## 3. The in-app scanner, in a browser tab

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| 3.1 | Signed in as a **technician** (not a client: a client gets "Page not found" on `/scan`, by design), open **Stations › Scan** (`/scan`) for the first time. The bar must read Dashboard, Work, Stations, Reports | No camera prompt yet. A card "Scan a station label" with "Turn on the camera" and "Enter the station code". (If the site already has camera permission, the camera starts at once: note which) | | |
| 3.2 | Tap "Turn on the camera" | The browser's permission prompt appears once | | |
| 3.3 | Allow | Live video, four white corners, the hint "Point the camera at the code on the station", the torch button if the phone has a torch | | |
| 3.4 | Hold a label in the square | Short buzz, green corners and "Label found", then the station page. The scanner does not reopen on its own | | |
| 3.5 | As a client, scan the label of a station owned by another organization | "We can't find that station", the same page as for an unknown code | | |
| 3.6 | Print a label, replace its QR on the station page (**Regenerate**), then scan the old one | "This code is no longer valid", with a way to the stations list | | |
| 3.7 | Scan something that is not a label (a shop QR code) | The hint "That isn't a MARS-MMS label. Try another.", then the camera starts again after about 2 seconds | | |
| 3.8 | Hold nothing in view for a minute | No crash, no heat, the page stays responsive | | |

## 4. The torch

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| 4.1 | Dim the room, tap the torch button | The LED lights; the button says it is on | | |
| 4.2 | Scan with the torch on | Reads the label | | |
| 4.3 | Tap again; then leave the page with the torch on | LED goes off in both cases | | |
| 4.4 | On a phone with no torch | The button is not shown | | |

## 5. Permission states

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| 5.1 | Deny the prompt | "The camera is turned off", telling you to allow the camera for MARS-MMS in the phone's settings; "Enter the station code" offered; no loop of prompts. Reopening Scan goes straight to this card | | |
| 5.2 | Allow it in the site settings, tap "Try the camera again" | The camera starts | | |
| 5.3 | Start the camera in another app (a call), then open Scan | "The camera can't be used" (another app may be using it); the code field works | | |
| 5.4 | Lock the screen with the camera on, unlock | The camera comes back, or Turn on the camera is offered; no frozen frame | | |

## 6. The installed app

Repeat 3.1 to 3.4, 4.1 and 5.1 from the installed app (home screen icon).

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| 6.1 | First camera use inside the installed app | The prompt appears again if the browser tab's choice is not shared. Record whether it does | | |
| 6.2 | Scan a label | Station page opens inside the installed app, not in the browser | | |
| 6.3 | Tap a label link from the stock camera app while the installed app is open | Opens in the installed app or in Chrome. Record which | | |

## 7. No signal

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| 7.1 | Sign in and open **Scan** and "Enter the station code" once online (this loads the station list into memory), then turn on airplane mode without reloading | The code field still finds stations and shows "Works offline" | | |
| 7.2 | Type a station code and open the match | The station page opens. Record what it shows with no signal: Phase 2 has no offline station data yet (Phase 5 prepares stations) | | |
| 7.3 | Scan a label in airplane mode | The label is read, then "No signal, and this station isn't prepared", with "Try again" and "Enter the station code". Expected for now | | |
| 7.4 | Close and reopen the app in airplane mode | The list is gone from memory: the code field says the list isn't on the phone yet. Known; record it | | |

## What to write down

- Phone model, OS version, browser and version, installed or tab.
- For any failure: what was on screen, the time, and a screen recording if you can.
- Anything slow (more than 2 seconds from a label in view to the station page).

## Result

Fill in: date, tester, device, pass or fail per section, issues opened. A pass on Android closes the Android half of the W7 exit; the iPhone half stays open until its column is filled.
