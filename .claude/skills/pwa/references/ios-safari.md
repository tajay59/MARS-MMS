# iOS and iPadOS Safari

The biggest risk for AWS-MMS. Most PWA guides are written for Chrome; the field test and the W13 check depend on iPhones.

Sources: [firt.dev iOS PWA compatibility](https://firt.dev/notes/pwa-ios/) (updated 13 Oct 2026), [WebKit storage policy](https://webkit.org/blog/14403/updates-to-storage-policy/), [WebKit 7-day cap](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/), [heise on iOS 26](https://heise.de/-10749652), [WebKit features in Safari 18.4](https://webkit.org/blog/16574/webkit-features-in-safari-18-4/), [What PWA Can Do Today](https://whatpwacando.today/). NFR-5 supports the current and previous major iOS versions (iOS 26 and 18 in October 2026).

## 1. What iOS supports (and what that means here)

| Feature | iOS | Consequence for AWS-MMS |
|---|---|---|
| Service worker, Cache Storage | Yes (11.3) | Offline shell works |
| IndexedDB, blobs in IndexedDB | Yes | Dexie works; test 200 MB blobs (W13) |
| Storage quota API, persistent mode | Quota 17+, persist 15.2+ | `persist()` may return `false` (F3) |
| Storage shared with Safari | **No** | Installed app and Safari tab are separate devices, in effect (F2) |
| Install prompt (`beforeinstallprompt`, `appinstalled`) | **No** | Instructions sheet instead (manifest-install.md §4) |
| Any site opens as a web app from the Home Screen | iOS 26 | Users can turn "Open as Web App" off; check `display-mode` |
| Background Sync, Periodic Sync, Background Fetch | **No** | Sync only while the app is open |
| JS in the background | **No** (suspended soon after leaving the app or locking the screen) | Uploads pause; resumable parts make that safe |
| Web Locks, BroadcastChannel | Yes (15.4) | Refresh and sync locks work |
| Navigation preload | Yes (15.4) | Not needed |
| Web Push, Badging | 16.4+, installed only | Not in v1 |
| Screen Wake Lock | 16.4; installed apps 18.4+ | Optional: keep the screen on while syncing |
| Web Share (incl. files) | Yes | Conflict export |
| `getUserMedia`, `<input capture>` | Yes | Camera capture works installed or not |
| Geolocation | Yes, but our `Permissions-Policy` sets `geolocation=()` | Not used |
| Manifest `display` | `standalone`, `browser` only | `minimal-ui` → browser, `fullscreen` → standalone |
| Manifest icons | 15.4+; `apple-touch-icon` overrides; maskable ignored | Provide an opaque 180 px apple-touch-icon |
| `background_color`, `orientation`, `shortcuts` | Ignored on iOS | Don't rely on them |
| Status bar colour | `theme-color` meta | Already set for light and dark |
| Links outside scope | Open in an in-app browser | Don't link to `files.` host for offline viewing |
| Network Information, Vibration, Bluetooth, NFC | **No** | Don't use |

## 2. The rules this creates

1. **Field work happens in the installed app.** Storage is separate, the 7-day rule doesn't apply there, and `persist()` is more likely. On iOS, when **Prepare for field** runs in a Safari tab (`display-mode` is not `standalone`), stop and show the install steps. Needs an AFD J5 change (F2).
2. **Sync only runs while the app is open.** Show "Keep AWS-MMS open while it syncs" on `/sync` during uploads. Optionally hold a Screen Wake Lock while syncing on iOS 18.4+ installed apps and Android, released when done or when the page is hidden.
3. **Expect to be killed.** iOS frees memory by terminating background web apps. On relaunch, the app restores the last route (or `/unlock` with no signal), and nothing is lost because every step is already in Dexie.
4. **Memory is tight.** Don't read a 200 MB video into an `ArrayBuffer` (F4). Resize photos one at a time, closing each `ImageBitmap` (`bitmap.close()`) after drawing.
5. **Install steps are part of training** (IP Phase 8): Share → Add to Home Screen → keep **Open as Web App** on → open from the Home Screen → log in → prepare.
6. **The installed app starts logged in** on iOS 17.2+ because Safari's login cookies are copied at install. Earlier versions need a fresh login.

## 3. HTTPS and certificates

iOS refuses service workers on pages with untrusted certificates. Local testing on an iPhone needs the dev CA installed and trusted on the phone (Settings → General → About → Certificate Trust Settings), or use staging.

## 4. Debugging an iPhone

- **Safari Web Inspector** needs a Mac: enable Settings → Safari → Advanced → Web Inspector on the phone, connect by cable, open Develop in desktop Safari. Installed web apps appear there too.
- **Without a Mac:** build a diagnostics panel in `/sync` (staff only): app version, worker state, `persisted()`, `estimate()`, `display-mode`, queue counts, the last 50 sync log lines. Use it in W13, W15 and the pilot.
- WebKit in Playwright only approximates iOS (TP). The real phone decides.

## 5. Media quirks to test with the TP fixtures

- iPhone photos may be HEIC and videos HEVC `.mov` (TP fixtures). What `<input accept="image/*">` hands the page (HEIC or a converted JPEG) depends on iOS settings and version. Resize must work on both; the server pipeline handles HEVC (MED-2).
- `lastModified` on a camera capture is close to capture time; read EXIF first where present.
- Check that a 2-minute video plays from a local blob URL (`<video src="blob:…">`) on the iPhone before upload, if the UI offers a preview.

## 6. Checks that need a real iPhone (W13, W15)

- Install, open from the Home Screen, log in, set the PIN, prepare a visit.
- 50 photos and 3 videos stored offline; restart the phone; unlock with the PIN; everything is there (IP W13).
- `persist()` result and `estimate()` numbers recorded in the diagnostics panel.
- Uploads interrupted by locking the screen resume afterwards.
- A whole visit with no signal, then sync with zero loss (IP Phase 5 exit criterion).
