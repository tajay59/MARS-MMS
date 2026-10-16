# Sources

Every external source this skill draws on, grouped as in the original recommendation, with what each is for in AWS-MMS. All links were checked on **2026-10-16**. Fetch a page when you need detail beyond the reference files; never copy large passages into the repo.

**Reading order for a newcomer:** web.dev Learn PWA → Vite PWA guides → WebKit storage policy and firt.dev → the Offline Cookbook.

## 1. Core guides

| Source | Use it for |
|---|---|
| [web.dev Learn PWA](https://web.dev/learn/pwa) | The course. Chapters below, mapped to this project |
| [MDN Progressive web apps](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps) | Standards reference and browser compatibility tables for each API (NFR-5) |
| [MDN: Making PWAs installable](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable) | Manifest requirements per browser |
| [MDN: Offline and background operation](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Offline_and_background_operation) | Background Sync, Periodic Sync, Background Fetch, push: what exists and where |
| [MDN: PWA best practices](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Best_practices) | Cross-browser checklist |
| [MDN: Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria) | Quota numbers per browser, `persist()` behaviour, LRU eviction |
| [web.dev: The service worker lifecycle](https://web.dev/articles/service-worker-lifecycle) | Install, waiting, activate, `skipWaiting`, `clients.claim` |
| [web.dev: The Offline Cookbook](https://web.dev/articles/offline-cookbook) | The caching strategies and when each fits |
| [web.dev: Storage for the web](https://web.dev/articles/storage-for-the-web) | Which storage API for what; quota; eviction |
| [web.dev: Persistent storage](https://web.dev/articles/persistent-storage) | `persist()`, `persisted()`, how browsers grant it |
| [web.dev: Install criteria](https://web.dev/articles/install-criteria) | Chromium installability rules |
| [web.dev: Serving cached audio and video (range requests)](https://web.dev/articles/sw-range-requests) | Why the worker should not touch media responses |

### Learn PWA chapters → AWS-MMS

| Chapter | Matters for | Reference file |
|---|---|---|
| [Foundations](https://web.dev/learn/pwa/foundations), [App design](https://web.dev/learn/pwa/app-design) | Standalone UX in the field shell, safe areas | manifest-install.md |
| [Assets and data](https://web.dev/learn/pwa/assets-and-data) | What goes in Cache Storage vs IndexedDB | caching.md, offline-data.md |
| [Service workers](https://web.dev/learn/pwa/service-workers), [Caching](https://web.dev/learn/pwa/caching), [Serving](https://web.dev/learn/pwa/serving), [Workbox](https://web.dev/learn/pwa/workbox) | `src/sw/sw.ts` | service-worker.md, caching.md |
| [Offline data](https://web.dev/learn/pwa/offline-data) | Dexie, outbox, blobs | offline-data.md, storage.md |
| [Installation](https://web.dev/learn/pwa/installation), [Web app manifest](https://web.dev/learn/pwa/web-app-manifest), [Installation prompt](https://web.dev/learn/pwa/installation-prompt) | Manifest, install prompt on first prepare | manifest-install.md |
| [Update](https://web.dev/learn/pwa/update) | Prompt-for-update, never mid-visit | service-worker.md |
| [Detection](https://web.dev/learn/pwa/detection) | Detecting standalone mode (iOS storage split) | ios-safari.md |
| [Enhancements](https://web.dev/learn/pwa/enhancements), [OS integration](https://web.dev/learn/pwa/os-integration), [Capabilities](https://web.dev/learn/pwa/capabilities) | Badging, wake lock, shortcuts (optional) | manifest-install.md |
| [Tools and debug](https://web.dev/learn/pwa/tools-and-debug) | DevTools, remote debugging phones | testing.md |
| [Architecture](https://web.dev/learn/pwa/architecture), [Complexity management](https://web.dev/learn/pwa/complexity) | SPA + app shell, keeping the worker small | service-worker.md |
| Windows, Experimental | Not needed in v1 | — |

## 2. The project's tools

| Source | Use it for |
|---|---|
| [Vite PWA guide](https://vite-pwa-org.netlify.app/guide/) | Plugin options |
| [Vite PWA: injectManifest](https://vite-pwa-org.netlify.app/guide/inject-manifest.html) | Our strategy: `srcDir`, `filename`, `self.__WB_MANIFEST`, TypeScript, `SKIP_WAITING` |
| [Vite PWA: Prompt for update](https://vite-pwa-org.netlify.app/guide/prompt-for-update.html) | Our update flow |
| [Vite PWA: Vue](https://vite-pwa-org.netlify.app/frameworks/vue.html) | `useRegisterSW` from `virtual:pwa-register/vue`, periodic update checks |
| [Vite PWA: Development](https://vite-pwa-org.netlify.app/guide/development.html) | `devOptions`, testing the worker in dev |
| [Vite PWA: Assets generator](https://vite-pwa-org.netlify.app/assets-generator/) | Icons and the apple-touch-icon from one source image |
| [vite-plugin-pwa README](https://github.com/vite-pwa/vite-plugin-pwa) and [releases](https://github.com/vite-pwa/vite-plugin-pwa/releases) | Version requirements (2.0.0 needs Node ≥ 20.19; Vite 3.1–8 supported) |
| [Workbox docs](https://developer.chrome.com/docs/workbox) | Module reference |
| [workbox-precaching](https://developer.chrome.com/docs/workbox/modules/workbox-precaching), [workbox-routing](https://developer.chrome.com/docs/workbox/modules/workbox-routing), [workbox-expiration](https://developer.chrome.com/docs/workbox/modules/workbox-expiration), [workbox-cacheable-response](https://developer.chrome.com/docs/workbox/modules/workbox-cacheable-response) | The four modules `sw.ts` uses |
| [Workbox: Handling service worker updates](https://developer.chrome.com/docs/workbox/handling-service-worker-updates) | The prompt pattern |
| [Workbox: Remove buggy service workers](https://developer.chrome.com/docs/workbox/remove-buggy-service-workers) | The kill switch |
| [Workbox: Understanding storage quota](https://developer.chrome.com/docs/workbox/understanding-storage-quota) | Opaque responses count about 7 MB each in Chrome |
| [Dexie docs](https://dexie.org/docs/), [Best practices](https://dexie.org/docs/Tutorial/Best-Practices), [Vue tutorial](https://dexie.org/docs/Tutorial/Vue), [`Dexie.version()`](https://dexie.org/docs/Dexie/Dexie.version%28%29) | Schema, versioning, transactions, `liveQuery` in Vue |
| [MDN Web Locks API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API) | `mms-auth-refresh` and the sync lock |
| [MDN Screen Wake Lock API](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API) | Keeping the screen on during a long sync (optional) |
| [MDN `StorageManager.persist()`](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/persist) | Exact API behaviour |

**Versions checked 2026-10-16:** vite-plugin-pwa **2.0.0** (peer `workbox-build`/`workbox-window` ^7.4.1), Workbox **7.4.1**, Dexie **4.4.6**. Repo: Vite ^8, Vue ^3.5, Node 24 (`frontend/.nvmrc`).

## 3. iOS and Safari

| Source | Use it for |
|---|---|
| [WebKit: Updates to Storage Policy](https://webkit.org/blog/14403/updates-to-storage-policy/) | Safari 17+ quotas, eviction, how `persist()` is granted ("whether the website is opened as a Home Screen Web App") |
| [WebKit: Full third-party cookie blocking and more](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/) | The 7-day cap on script-writable storage, and why home-screen web apps are not subject to Safari's counter |
| [firt.dev: iOS PWA compatibility](https://firt.dev/notes/pwa-ios/) | Feature-by-feature iOS support with versions (page updated 13 Oct 2026) |
| [firt.dev: Learn PWA notes](https://firt.dev/learn-pwa/) | Firtman's index to the course he co-wrote |
| [What PWA Can Do Today](https://whatpwacando.today/) | Try each feature live on the test phones (storage, install, wake lock, camera) |
| [WebKit Bug 271401](https://bugs.webkit.org/show_bug.cgi?id=271401) | `persist()` returning `false` in Safari 17 (open, unassigned) |
| [heise: iOS 26 web app behaviour](https://heise.de/-10749652) | iOS 26: every site added to the Home Screen opens as a web app by default |
| [WebKit features in Safari 18.4](https://webkit.org/blog/16574/webkit-features-in-safari-18-4/) | Declarative Web Push, Screen Wake Lock in installed apps |

## 4. Checking and polish

| Source | Use it for |
|---|---|
| [Chrome DevTools: Debug PWAs](https://developer.chrome.com/docs/devtools/progressive-web-apps) | Application panel: manifest, workers, storage, offline |
| [Edge DevTools for PWAs](https://learn.microsoft.com/en-us/microsoft-edge/devtools/progressive-web-apps/) | Same, in Edge |
| [Lighthouse PWA](https://developer.chrome.com/docs/lighthouse/pwa) | Note: **PWA testing in Lighthouse is deprecated.** Use DevTools' Manifest pane for installability |
| [Microsoft Edge PWA docs](https://learn.microsoft.com/en-us/microsoft-edge/progressive-web-apps/how-to/) and [best practices](https://learn.microsoft.com/en-us/microsoft-edge/progressive-web-apps/how-to/best-practices) | Desktop install for staff on Edge |
| [Playwright: Service workers](https://playwright.dev/docs/service-workers) | "Service workers are only supported on Chromium-based browsers" in Playwright's SW APIs |

## 5. Policies that constrain the build

| Source | Constraint |
|---|---|
| [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/) | "Offline use is not permitted on tile.openstreetmap.org." No prefetch. Honour Cache-Control, Expires, ETag. Visible attribution. See findings.md F1 |

## Complementary skills (not installed)

- [vuejs-ai/skills](https://github.com/vuejs-ai/skills): Vue, Pinia, Router and testing best practices, with Vue core team involvement. `npx skills add vuejs-ai/skills`.
- [antfu/skills](https://github.com/antfu/skills): `vite`, `vitest`, `pinia` skills generated from the official docs.

Read any third-party skill folder in full before installing it; it runs with your permissions.
