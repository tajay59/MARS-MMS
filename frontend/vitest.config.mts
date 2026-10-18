import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { defineConfig } from 'vitest/config'

// Unit tests (TP "Frontend unit"): stores, the refresh lock, guards and components.
export default defineConfig({
  define: { __APP_VERSION__: JSON.stringify('0.0.0-test') },
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    alias: { '@': fileURLToPath(new URL('src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/__tests__/*.spec.ts'],
    // The colour library's ESM build has extensionless imports: let Vite resolve them
    server: { deps: { inline: ['vuetify', '@material/material-color-utilities'] } },
    css: false,
  },
})
