import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
import vuetify, { transformAssetUrls } from 'vite-plugin-vuetify'

// https://vitejs.dev/config/
export default defineConfig({
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
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,woff2,png,svg,ico}'],
        // Inter and JetBrains Mono: only the Latin subsets are used (caching.md §3)
        globIgnores: ['**/*cyrillic*', '**/*greek*', '**/*vietnamese*'],
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
  },
  server: {
    port: 3000,
  },
})
