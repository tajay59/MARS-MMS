# Pilot device check (Phase 8, W23)

One run on each pilot technician's **own phone**, before the training session. It gathers every real-phone check that was put off since W6 into one sitting, because the pilot is the last place they can go: a launch criterion is "a full visit recorded offline on a real Android and iOS device synced with no loss" (PRD §8), and Phase 5 is not formally closed until an iPhone has run it. Plan and reasons: [plans/W23-plan.md](../plans/W23-plan.md), decision W23-4.

**Status:** not run. At least one iPhone and one Android phone must run it (plan question 8).

**This repo is public.** Fill the result sheet in a private note. Only pass or fail per part, the phone's OS and browser version, and the measured numbers go back into this file or the docs site. No names of people, clients or stations.

## What this closes

| Open since | Check | Part here | Android | iPhone |
|---|---|---|---|---|
| Phase 1 (W4, issue #8) | Install, the offline shell, the session, the update prompt in the installed app | A, J | Passed 2026-10-18 | Open |
| W6 (finding F15) | An upload from the installed app survives a reload without a second copy | E | No result recorded | Open |
| W6, W11 (finding F4) | A file over 64 MiB, and a 2-minute phone video processed | E | No result recorded | Open |
| W7 (QR-2) | A printed label scanned by the camera app and by the in-app scanner | D | No result recorded | Open |
| W9 | A notification missed while the app was in the background arrives on return | G | No result recorded | Open |
| W13 (findings F2, F3; risk R4) | 50 photos and 3 videos stored, the phone restarted, the PIN unlocks them | B, C | No result recorded | Open |
| W14, W15 (OFF-7, OFF-8, finding F12) | A whole visit with no signal, synced once, nothing lost or doubled | F | No result recorded | Open (blocks closing Phase 5) |
| W17, W18 | A signature drawn on the phone; a client accepts work and uploads a PDF report | H | No result recorded | Open |
| W22 | The code step of two-step sign-in on a phone's keyboard | I | No result recorded | Open |

"No result recorded" means the repository holds no result. If a check was done and written down elsewhere, mark it here with its date instead of running it again.

## Before you start

**Where:** staging, `https://rnd.yanacreations.com`, release 0.8 or later (the public pages show `Version 0.8.x`). Run `bash infra/scripts/readiness.sh https://rnd.yanacreations.com --expect-version 0.8.0` first: a failed line there is not the phone's fault.

**The admin prepares (a desk, with signal):**

1. Each technician has a staff account on staging and has signed in once.
2. One test client account in an organization that has **no real client users** on staging (nobody outside the team may be emailed).
3. Two requests and two visits as in the field test runbook, [field-test.md](../field-test.md) section 1 (title `[Device check] …`), each visit with two stations, the admin added as an attendee.
4. The labels of those stations printed from **Admin › Station tools** at 100%.
5. One more request, taken to **Client Review** (a visit ended, its report finalized), for part H.

**The phone:**

- Android: Chrome, up to date. iPhone: Safari, iOS 17 or later. Write down the model, the OS version and the browser version.
- A phone passcode is set (the offline PIN protects the app, the passcode protects the phone).
- At least 2 GB free.
- **iPhone: do everything in the installed app, not in a Safari tab.** The installed app has its own storage (finding F2): work prepared in a tab is not in the app, and Safari may delete a tab's data after seven days without use.

"No signal" is **airplane mode**, with Wi-Fi off too.

## A. Install and the shell

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| A1 | Open the site in the browser, with signal. Time the first load until the page can be used | Under a minute on mobile data (W4 measured 31 s on Android after finding F14). Write the time down | | |
| A2 | Install. Android: the Install card on the dashboard, or Chrome's menu. iPhone: Share, then Add to Home Screen (the app shows these steps; there is no install prompt on iOS) | An icon named MARS-MMS on the home screen, with the logo and no white box round it | | |
| A3 | Open it from the home screen | No browser address bar. The status bar and the bottom bar do not sit under the notch or the home indicator (finding F13) | | |
| A4 | Sign in. Close the app (swipe it away), open it again | Still signed in, no password asked | | |
| A5 | Airplane mode on. Close the app, open it again | The app opens (its shell is on the phone). It says there is no connection where a page needs one; it never shows the browser's own offline page | | |
| A6 | Airplane mode off | The app carries on without a reload | | |
| A7 | Switch the phone between light and dark | The app follows (when its setting is System) | | |

## B. The offline PIN

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| B1 | **My profile › Offline PIN**: set a PIN | Saved | | |
| B2 | Open a visit, **Prepare for field**, wait for **Ready offline** | Every document and configuration file is listed as on the phone. Write down how long it took | | |
| B3 | Airplane mode on. Close the app, open it | The unlock page asks for the PIN | | |
| B4 | Enter a wrong PIN once, then the right one | One refusal, then the app opens, marked offline. (Five wrong PINs in a row turn offline unlock off) | | |
| B5 | **Switch the phone off and on**, still in airplane mode. Open the app, unlock | The prepared visit is there | | |
| B6 | Airplane mode off | The app signs in for real by itself; no password asked | | |

Do not test five wrong PINs on a phone that is about to be used: it turns offline unlock off until the next sign-in with signal. If you want that check, do it last.

## C. Storage (W13; findings F2, F3; risk R4)

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| C1 | **Me › Sync › This phone**, then **Copy report**. Paste it into the private note | It says installed, whether the browser promised to keep the data (`persisted`), and used and available storage. On an iPhone `persisted` may be **no** (WebKit bug 271401): write it down, it is not a failure by itself | | |
| C2 | Open **Storage check** from that card. **Add photos and videos**: 50 photos and 3 videos of 1 to 2 minutes, taken now or from the gallery | All 53 listed as stored on this phone, with the total size | | |
| C3 | Switch the phone off and on. Open the app, unlock, open **Storage check** | All 53 still there, same total | | |
| C4 | Leave the phone unused overnight if you can, then look again | Still there. (This is the nearest a day can come to the seven-day rule; the installed app is exempt from it, a tab is not) | | |
| C5 | **Copy report** again, then **Remove test files** | The report shows the storage used; after removing, the count is 0 | | |

## D. Labels (W7, QR-2)

Follow [W7-label-scan-check.md](W7-label-scan-check.md) sections 2 to 6 with the labels printed above, filling the column for this phone. With a prepared visit on the phone, also:

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| D1 | Airplane mode on. **Stations › Scan**, scan the label of a **prepared** station | The stored copy of the station opens, read only, and its configuration file opens | | |
| D2 | Scan the label of a station that is **not** prepared | "No signal, and this station isn't prepared", with a way to enter the code | | |
| D3 | iPhone only: close the installed app, open it, open Scan again | Write down whether the camera permission is asked again (iOS may ask on each start of an installed app) | | |

## E. Uploads with signal (W6 finding F15; W11; finding F4)

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| E1 | On a station's **Documents** tab, upload a PDF of 10 MB or more over mobile data | Progress, then the document listed as available after the check | | |
| E2 | Start the same upload with another file, and **reload the app** halfway. Choose the same file again | Only the missing parts are sent (it finishes sooner than a fresh upload would), and the document is listed **once** | | |
| E3 | On a started visit's board, add a Task and put a **2-minute video**, recorded now, in its Before media, over Wi-Fi | It uploads, shows "processing", then plays. Write down the file size, the upload time and the time until it plays | | |
| E4 | If the video is under 64 MiB, record a longer one (4K, or 3 to 4 minutes) so one file is over 64 MiB | The same, and the app does not freeze or restart while it prepares the file (finding F4) | | |
| E5 | During E3 or E4, lock the screen for 30 seconds, unlock | Android: the upload carried on. iPhone: it stopped and **resumes by itself** when the app is back (finding F12). No second copy either way | | |

## F. A whole visit with no signal (the launch criterion)

Run the field test runbook, [field-test.md](../field-test.md): section 2 the day before, then scenarios **S1 to S8 and S10** in section 3, the server's counts in section 4, the result sheet in section 5 and the clean-up in section 6. Where it says release 0.5.0, read the release on staging now. S9 (an update while work is waiting) is part J here.

Pass is by **counts**, as there: what the phone recorded is on the server once, a second sync changes nothing, and the owner-change conflict is under **Needs attention** and can be exported.

iPhone, in addition:

| # | Do | Expect | iPhone |
|---|---|---|---|
| F1 | During S5, leave the app (go to the home screen) for a minute while files upload | The sync stopped while the app was away and carries on when it is opened again. Nothing is doubled. The Sync page said to keep the app open | |
| F2 | During S5, stay on the Sync page without touching the phone | The screen stays on while it syncs (the wake lock), where iOS allows it. Write down if it dims | |
| F3 | After S7, **Copy report** | Nothing waiting; the prepared visit is gone from the phone | |

## G. Live updates and notifications (W9)

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| G1 | With the app open on the dashboard, the admin assigns a request to this technician from a desk | A notification appears in the app within a few seconds, with no reload. (This also proves the live connection is allowed by the content security policy on this browser) | | |
| G2 | Leave the app for a minute (home screen). The admin adds a comment to that request. Open the app | The missed notification is there within a few seconds of returning | | |
| G3 | Airplane mode on for a minute, then off, app open | The app reconnects by itself; a comment added meanwhile arrives | | |

## H. Signatures and the client's review (W17, W18)

These need signal: signing is not offline work.

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| H1 | As the technician, open the draft visit report of an ended visit, **sign**: draw a signature with a finger | The line follows the finger without lag and the page behind does not scroll while drawing. The signature shows on the report | | |
| H2 | Turn the phone sideways and back while the sign dialog is open | The drawing is kept, or the dialog says to sign again; never a stretched signature | | |
| H3 | Sign another report with **Use my typed name as my signature** | Accepted | | |
| H4 | As the **client**, on the request in Client Review: open the review, read the report PDF on the phone | The PDF opens and every page can be read (an iPhone shows only the first page of a PDF in a frame; the app has its own viewer for that reason) | | |
| H5 | **Accept work**: sign, **Sign and accept** | "Work accepted." The request closes | | |
| H6 | On a second request in Client Review: **Send the work back** with a reason | "Sent back." The request returns to the staff | | |
| H7 | As the client, add a client report of kind PDF: choose a PDF from the phone's files | It uploads and is listed under the request's reports | | |

## I. Two-step sign-in (W22)

Only on a phone whose owner has two-step sign-in (admins must; other staff may turn it on in **My profile › Two-step sign-in**). Use a test admin on staging, not a real one.

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| I1 | Sign out, sign in with the password | The code step: six boxes, and the **number** keypad | | |
| I2 | Look at the keyboard's suggestion bar | Write down whether the phone offers the code (it can only if the phone's own password manager holds this account's code). Not a failure if it does not | | |
| I3 | Copy the code in the authenticator app, come back, paste | All six boxes fill and the sign-in finishes | | |
| I4 | Switching to the authenticator app and back | The code step is still there; the app did not start again at the password | | |
| I5 | A wrong code | "That code is incorrect. Enter the current code from your app.", and another try | | |

## J. An update while work is waiting

Only when a release reaches staging during the check (or ask the developer to deploy one: a version bump is enough).

| # | Do | Expect | Android | iPhone |
|---|---|---|---|---|
| J1 | Record a note offline on a prepared visit and keep it unsent. The developer deploys. Open the app with signal | The update prompt appears. It does not reload by itself, and not during a capture or a sync | | |
| J2 | **Reload now** | The app reloads once into the new version (the public pages show it). The waiting note is still waiting, then syncs | | |

## Result sheet (copy into a private note)

| Part | Android: pass / fail | iPhone: pass / fail | Numbers | Notes |
|---|---|---|---|---|
| Phone | model, OS, browser | model, OS, browser | | |
| A | | | first load (s) | |
| B | | | prepare time (s) | |
| C | | | persisted; used / available; 53 files kept? | |
| D | | | | camera asked again? |
| E | | | video size; upload time; time to play | |
| F | | | the field test's sheet | |
| G | | | seconds until a missed notification shows | |
| H | | | | |
| I | | | | code offered by the keyboard? |
| J | | | | |

## When something fails

1. **Copy report** at once (Me › Sync › This phone) and keep it with the time and what you did.
2. Do not clear the app's data, uninstall it or sign out: waiting work stays on the phone until it is synced or exported.
3. Tell the developer. During the pilot, a failure is filed with the pilot issue form (no names of people, clients or stations in it: the repository is public).

## Afterwards

1. Cancel the `[Device check]` requests, with the reason "Device check".
2. **Sync** shows nothing waiting on each phone. Remove the storage check's test files.
3. Put pass or fail per part, the OS versions and the numbers into the status line and the table at the top of this file, findings F2, F3, F4 and F12 in `.claude/skills/pwa/references/findings.md`, and the docs site changelog.
4. The phones then move to production at the training session: sync everything on staging first, then install the production app. It is another address, so the phone treats it as another app with its own storage.
