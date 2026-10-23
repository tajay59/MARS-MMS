import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
import vuetify, { transformAssetUrls } from 'vite-plugin-vuetify'

// The release shown in the app. Only a version bump changes it, not every commit: a changed
// precached file means a new sw.js and an update prompt on every phone.
const { version } = JSON.parse(readFileSync(new URL('package.json', import.meta.url), 'utf8')) as { version: string }

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  plugins: [
    vue({
      template: { transformAssetUrls },
    }),
    // Auto-imports Vuetify components and compiles its Sass with our settings (TRD §13.2)
    vuetify({
      autoImport: true,
      styles: {
        configFile: 'src/app/theme/settings.scss',
      },
    }),
    tailwindcss(),
    // The minimal service worker and manifest (F5, IP W4). Rules: pwa skill §2.
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src/sw',
      filename: 'sw.ts', // emitted as /sw.js; never rename it
      registerType: 'prompt', // updates wait for the user (stores/update.ts)
      // The kill switch (W15-3; runbook in the docs site, Infrastructure › Releases): `npm run
      // build:kill` emits a sw.js that unregisters itself and clears the caches. It is
      // never deployed by a release; an operator ships it by hand if a broken worker reaches phones.
      selfDestroying: mode === 'kill',
      injectRegister: false, // registered from Vue (app/pwa/usePwa.ts): no inline script under the CSP
      manifest: {
        id: '/',
        name: 'MARS-MMS',
        short_name: 'MARS-MMS',
        description: 'Weather station maintenance',
        lang: 'en',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        // The built-in brand colours (src/app/theme/material-theme.json): light primary and background
        theme_color: '#0A6780',
        background_color: '#F5FAFD',
        icons: [
          { src: 'pwa-64x64.png', sizes: '64x64', type: 'image/png' },
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      // The installed app's icons live with the operating system, and the favicon only shows in a
      // browser tab: none of them is precached (F14), so they cost an install nothing.
      includeManifestIcons: false,
      injectManifest: {
        // Google Sans, Roboto Flex and JetBrains Mono: only the Latin subsets are precached
        // (caching.md §3); Google Sans ships a file for every script
        globPatterns: ['**/*.{js,css,html,svg}', '**/*-latin-*.woff2'],
        // The brand-colour generator is loaded only by an admin on Settings, which needs a connection
        // anyway (OFF-10); leaving it out keeps the first install short (F14, e2e/offline.spec.ts).
        // pdf.js and its worker (1.6 MB) stay out too: a PDF on the board needs a connection until
        // Phase 5 decides whether the field bundle carries them (F17, W11-30).
        globIgnores: ['**/materialGenerate-*.js', '**/pdf-*.js', '**/pdf.worker*.js'],
      },
      devOptions: {
        enabled: false, // `npm run build && npm run preview` to work on the worker
        type: 'module',
        navigateFallback: 'index.html',
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('src', import.meta.url)),
    },
  },
  build: {
    // Fonts never become data: URIs: the CSP has no font-src, so default-src 'self' blocks them
    // (TRD §15). Small images may still be inlined.
    assetsInlineLimit: (file: string) => /\.(?:woff2?|ttf|otf)$/.test(file) ? false : undefined,
    rolldownOptions: {
      output: {
        // Few, larger chunks (F14): the worker precaches every chunk on install, and each file costs
        // a round trip on a phone's link. `vendor` is the libraries the first page needs, which
        // change rarely, so an update downloads `app` again but not them. `app` is all of src/ and
        // what its pages import. A large library used by one page stays out of both only behind
        // a dynamic import(), as materialGenerate, the QR drawing (qrCode.ts) and Leaflet are.
        codeSplitting: {
          groups: [
            { name: 'vendor', test: /[\\/]node_modules[\\/]/, tags: ['$initial'], priority: 2 },
            { name: 'app', test: id => /[\\/]src[\\/]/.test(id) && !/materialGenerate|[\\/]qrCode\.ts/.test(id), priority: 1 },
          ],
        },
      },
    },
  },
  server: {
    port: 3000,
  },
}))
