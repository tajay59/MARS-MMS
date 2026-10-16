# Manifest, install and standalone UX

Sources: web.dev Learn PWA (Installation, Web app manifest, Installation prompt, Detection), [web.dev install criteria](https://web.dev/articles/install-criteria), [MDN installable](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable), [firt.dev iOS](https://firt.dev/notes/pwa-ios/), [Edge PWA docs](https://learn.microsoft.com/en-us/microsoft-edge/progressive-web-apps/how-to/).

## 1. Why install matters here

Installing is not cosmetic for AWS-MMS. On iOS:

- An installed (home-screen) web app has **its own storage**, separate from Safari's. Data prepared in a Safari tab is **not** visible in the installed app, and the reverse.
- Home-screen web apps are not subject to Safari's 7-day cap on script-writable storage, and WebKit grants `persist()` "based on heuristics like whether the website is opened as a Home Screen Web App".

So on iPhones, **field work must be prepared and recorded in the installed app**. See findings.md F2.

## 2. The manifest

vite-plugin-pwa writes `manifest.webmanifest` and injects the `<link rel="manifest">`. Configure it in `vite.config.mts` (full config in vite-pwa-vue.md):

```ts
manifest: {
  id: '/',
  name: 'AWS-MMS',              // placeholder until branding (D1, Q1)
  short_name: 'AWS-MMS',
  description: 'Weather station maintenance',
  lang: 'en',
  start_url: '/',               // the router sends users to /dashboard or /login (AFD §5.2)
  scope: '/',
  display: 'standalone',
  theme_color: '#22569A',       // primary, matches the light theme-color meta tag
  background_color: '#F8FAFC',  // light `background` from brand.ts
  icons: [
    { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
    { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
    { src: 'maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
  ],
},
```

Rules:

- **Never change `id`, `start_url`'s origin or `scope`** after launch. `id` is the app's identity; changing it makes browsers treat it as a new app.
- **No `orientation` lock.** Tablets and desktops use the same app.
- **No `shortcuts` in v1.** Shortcuts are the same for every role; a client tapping "Scan" would land on a not-found page.
- `theme_color` in the manifest is one value. The two `theme-color` meta tags already in `frontend/index.html` (light `#22569A`, dark `#0B1220`) override it in the browser and the installed app's title bar.

### Icons

Generate from one source image with `@vite-pwa/assets-generator` (`minimal2023Preset`): 64, 192, 512, maskable 512, `apple-touch-icon-180x180.png` and the favicon. The source is a placeholder until D1.

- **iOS ignores maskable icons** and still prefers `<link rel="apple-touch-icon">` over manifest icons when the tag exists. Give it an opaque 180×180 PNG (transparent areas turn black).
- iOS 26 accepts SVG manifest icons, but older iOS doesn't. Keep PNGs.
- Add to `index.html`: `<link rel="apple-touch-icon" href="/apple-touch-icon-180x180.png">`.

## 3. Installability by browser

| Browser | How it installs | Prompt event |
|---|---|---|
| Chrome, Edge (Android and desktop) | Browser UI, or our button calling the saved `beforeinstallprompt` event | `beforeinstallprompt`, `appinstalled` |
| Samsung Internet | Browser UI and `beforeinstallprompt` | Yes |
| Safari iOS / iPadOS | Share → **Add to Home Screen**. From iOS 26 every site added opens as a web app unless the user turns off **Open as Web App** | **None.** No `beforeinstallprompt`, no `appinstalled` |
| Safari macOS | File → Add to Dock | None |
| Firefox Android | Menu → Install / Add to Home screen | None |

Chromium needs HTTPS, a manifest with `name` or `short_name`, 192 and 512 px icons, `start_url`, and `display` of `standalone`, `fullscreen` or `minimal-ui`.

## 4. The install prompt in AWS-MMS (IP Phase 5)

Who and when:

- **Staff only.** Clients never work offline; they can still install from the browser menu.
- **At the point of need**: J5 step 4, **Prepare for field**, before the PIN is set. Also a permanent **Install app** item in the staff user menu while not installed.
- Never on first page load and never as a modal that blocks work.

How:

```ts
// app/install.ts (sketch)
const deferred = shallowRef<BeforeInstallPromptEvent | null>(null)
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferred.value = e as BeforeInstallPromptEvent })
window.addEventListener('appinstalled', () => { deferred.value = null })

export const isStandalone = () => matchMedia('(display-mode: standalone)').matches
export const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent)
  || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) // iPadOS reports as Mac

export async function promptInstall() {   // call from a click handler only
  if (!deferred.value) return 'unavailable'
  await deferred.value.prompt()
  const { outcome } = await deferred.value.userChoice
  deferred.value = null
  return outcome
}
```

- Chromium: show an **Install app** button only when `deferred` is set; call `promptInstall()` from the click.
- iOS: show a short sheet with the steps (Share → Add to Home Screen → keep **Open as Web App** on → open AWS-MMS from the Home Screen and prepare the visit there). Use DBD voice; check copy with `writing-guidelines`.
- `BeforeInstallPromptEvent` is not in TypeScript's DOM lib; declare it in `env.d.ts`.

## 5. Standalone UX (field shell)

In standalone mode there is no address bar, back button, reload button or pull-to-refresh on iOS. Design for it:

- **Every field page has an in-app way back** (the stepper and bottom bar already do this). Never rely on the browser back button.
- **"Sync now" replaces pull-to-refresh.**
- **Safe areas:** add `viewport-fit=cover` to the viewport meta tag and pad the bottom navigation and top bar with `env(safe-area-inset-bottom)` / `env(safe-area-inset-top)` (Tailwind arbitrary values, e.g. `pb-[env(safe-area-inset-bottom)]`). Check on a notched iPhone.
- **Overscroll:** `overscroll-behavior: none` on the field shell's scroll root stops rubber-banding the whole app.
- **Links leaving scope** (anything not on `mms.<host>`) open in an in-app browser on iOS. Presigned file links on `files.<host>` are out of scope: open documents from Dexie blobs with object URLs instead when offline.
- **Detect the mode** with `matchMedia('(display-mode: standalone)')`, not `navigator.standalone` (deprecated).
- **Don't depend on hover**; touch targets 48 px in the field shell (TRD §13.2).
- The app can be killed and relaunched by iOS at any time. Every field step already saves to Dexie; also **store the current route** so launch returns there (AFD J6 step 0: "the page they were on").

## 6. Desktop (Edge, Chrome)

Staff often work on desktops. Installing is optional there and nothing changes in behaviour.

- Installed apps open in their own window with the page `<title>` as window title. Keep titles meaningful per route.
- Badging (`navigator.setAppBadge(n)`) could show waiting sync items. Optional, Chromium desktop and installed iOS 16.4+ (iOS needs notification permission). Not in the v1 plan.
- Window Controls Overlay, file and protocol handlers, Microsoft Store: not needed in v1.
