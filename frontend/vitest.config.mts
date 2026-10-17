import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { defineConfig } from 'vitest/config'

// Unit tests (TP "Frontend unit"): stores, the refresh lock, guards and components.
export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    alias: { '@': fileURLToPath(new URL('src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/__tests__/*.spec.ts'],
    server: { deps: { inline: ['vuetify'] } },
    css: false,
  },
})
