# vite-plugin-pwa + Vue: setup for `frontend/`

Sources: [Vite PWA guide](https://vite-pwa-org.netlify.app/guide/), [injectManifest](https://vite-pwa-org.netlify.app/guide/inject-manifest.html), [Vue](https://vite-pwa-org.netlify.app/frameworks/vue.html), [Development](https://vite-pwa-org.netlify.app/guide/development.html), [Assets generator](https://vite-pwa-org.netlify.app/assets-generator/), plugin source (2.0.0, read 2026-10-16).

Versions (2026-10-16): **vite-plugin-pwa 2.0.0** needs Node ≥ 20.19 (repo uses Node 24) and supports Vite 3.1 to 8. It brings `workbox-build` and `workbox-window` ^7.4.1. **Workbox 7.4.1.**

## 1. Install

```sh
cd frontend
npm i -D vite-plugin-pwa @vite-pwa/assets-generator \
  workbox-core workbox-precaching workbox-routing workbox-strategies \
  workbox-expiration workbox-cacheable-response workbox-window
npm i dexie            # runtime dependency (offline/)
```

The `workbox-*` packages are dev dependencies because they're bundled into `sw.js` at build time.

## 2. `vite.config.mts`

Add the plugin **after** `vue`, `vuetify` and `tailwindcss`:

```ts
import { VitePWA } from 'vite-plugin-pwa'

VitePWA({
  strategies: 'injectManifest',
  srcDir: 'src/sw',
  filename: 'sw.ts',              // emitted as /sw.js. Never rename (service-worker.md §3)
  registerType: 'prompt',         // the default; stated for clarity
  injectRegister: false,          // we register from Vue with useRegisterSW; no inline script (CSP)
  manifest: { /* manifest-install.md §2 */ },
  injectManifest: {
    globPatterns: ['**/*.{js,css,html,woff2,png,svg,ico}'],
    globIgnores: ['**/*cyrillic*', '**/*greek*', '**/*vietnamese*'],  // caching.md §3
    // maximumFileSizeToCacheInBytes: default 2 MiB; the build fails above it
  },
  devOptions: {
    enabled: false,               // turn on only while working on src/sw (see §6)
    type: 'module',
    navigateFallback: 'index.html',
  },
})
```

- The plugin adds the manifest and its icons to the precache itself.
- Add `<link rel="apple-touch-icon" href="/apple-touch-icon-180x180.png">` and `viewport-fit=cover` (manifest-install.md §5) to `index.html`.
- `injectRegister: false` is required here: `'inline'` would inject an inline script, which the CSP blocks.

## 3. TypeScript

The worker needs the WebWorker lib; the app needs DOM. Adding both to one project causes type clashes, so give the worker its own project.

`frontend/tsconfig.sw.json`:

```json
{
  "extends": "@vue/tsconfig/tsconfig.json",
  "include": ["src/sw/**/*.ts"],
  "compilerOptions": {
    "composite": true,
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.sw.tsbuildinfo",
    "lib": ["ESNext", "WebWorker"],
    "types": []
  }
}
```

- Add `{ "path": "./tsconfig.sw.json" }` to `tsconfig.json` `references`, and `"src/sw/**"` to `exclude` in `tsconfig.app.json`, so `vue-tsc --build` checks both.
- If the worker imports the sync core from `src/offline/`, those files are type-checked under WebWorker too. That's useful: it proves the core has no DOM dependency (service-worker.md §5).
- `self.__WB_MANIFEST` is typed by `workbox-precaching`. Declare `let self: ServiceWorkerGlobalScope` in `sw.ts`.
- App side, in `env.d.ts`: `/// <reference types="vite-plugin-pwa/vue" />` (types `virtual:pwa-register/vue`), plus `BeforeInstallPromptEvent` (manifest-install.md §4).
- ESLint: add a flat-config block for `src/sw/**` with `globals.serviceworker` and no DOM globals.

## 4. Registration and the update prompt (`src/app/pwa/`)

Register **once**, in a component mounted by `App.vue` (not per shell, or each shell would register again):

```ts
// src/app/pwa/usePwa.ts
import { useRegisterSW } from 'virtual:pwa-register/vue'

const HOUR = 60 * 60 * 1000

export function usePwa() {
  return useRegisterSW({
    // immediate: true is the Vue default
    onRegisteredSW(swUrl, r) {
      if (!r) return
      const check = async () => {
        if (r.installing || !navigator.onLine) return
        const res = await fetch(swUrl, { cache: 'no-store', headers: { 'cache-control': 'no-cache' } }).catch(() => null)
        if (res?.status === 200) await r.update()
      }
      setInterval(check, HOUR)
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') void check()
      })
    },
    async onNeedReload() {
      // Another tab (or this one) accepted the update. Save before reloading.
      await flushPendingWrites()   // from offline/; resolves when queued Dexie writes are done
      rememberRoute()              // so launch returns here (AFD J6 step 0)
      location.reload()
    },
    onRegisterError(error) {
      console.error('Service worker registration failed', error)
    },
  })
}
```

Returned refs: `needRefresh`, `offlineReady` (`Ref<boolean>`) and `updateServiceWorker()`.

The component shows a Vuetify `VSnackbar` (`timeout="-1"`, `role="status"`):

- `needRefresh`: "A new version is ready." with **Reload** (calls `updateServiceWorker()`) and **Later**. In the field shell, hold it until the user is on the station list, `/sync` or has ended the visit (service-worker.md §3).
- `offlineReady`: staff only, once: "AWS-MMS now works offline on this device." Clients don't need it.
- Copy follows DBD "Voice and microcopy"; run `writing-guidelines`.

Gotcha from the plugin docs: `workbox-window` treats a registration repeated within one minute as "external", which can show the wrong prompt. Don't re-register on route changes.

## 5. Icons

`frontend/pwa-assets.config.ts`:

```ts
import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config'

export default defineConfig({
  preset: minimal2023Preset,
  images: ['public/logo.svg'],   // placeholder until branding (D1)
})
```

Run `npx pwa-assets-generator` and commit the PNGs, or wire it into the plugin with the `pwaAssets` option. Check the apple-touch icon is opaque.

## 6. Developing and testing the worker

- **Real behaviour needs a production build:** `npm run build && npm run preview` (serves `dist/` on localhost, which counts as a secure context).
- `devOptions.enabled: true` runs the worker in `npm run dev` as an ES module. The dev precache is nearly empty, so it's for wiring (messages, routes), not offline tests.
- DevTools → Application → Service workers: **Update on reload** while editing; **Offline** to simulate; **Unregister** and **Clear site data** to start clean.
- On a phone over the LAN, the page needs HTTPS with a certificate the phone trusts (iOS refuses workers on untrusted certificates). Use the local stack's TLS with its root CA installed on the test phone, or test on staging.
- Workbox logs: `injectManifest.enableWorkboxModulesLogs: true` in a debug build only.
