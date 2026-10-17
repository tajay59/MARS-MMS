import { defineConfig, devices } from '@playwright/test'

/*
  End-to-end journeys against the local Compose stack (TP "End-to-end"). Start it first:
    cd infra && docker compose -f compose.yml -f compose.dev.yml up -d --build
  then `npm run build` here (Nginx serves frontend/dist) and `npm run test:e2e`.
  MMS_E2E_URL points the tests at another host (staging smoke).
*/

const baseURL = process.env.MMS_E2E_URL ?? 'https://mms.localhost'

export default defineConfig({
  testDir: 'e2e',
  globalSetup: './e2e/global-setup.ts',
  // Journeys share the stack's rate limits (Nginx `auth` zone: 10/min per IP): one at a time.
  workers: 1,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  // The real stack: Argon2 and the breached-password check take a few seconds on register
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    ignoreHTTPSErrors: true, // the local stack's self-signed certificate
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Chromium won't register a service worker on an untrusted certificate, even with
        // ignoreHTTPSErrors; the local stack's is self-signed (pwa skill vite-pwa-vue.md §6).
        launchOptions: { args: ['--ignore-certificate-errors'] },
      },
    },
    { name: 'phone', use: { ...devices['Pixel 7'] }, grep: /@phone/ },
  ],
})
