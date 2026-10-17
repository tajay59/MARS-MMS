import { expect, test } from './support'

/*
  Staging smoke (TRD §18; release.yml runs `--grep @smoke` after each deploy). Needs no seed
  users, so it runs against a fresh staging as well as the local stack. The offline-shell test
  in offline.spec.ts is tagged @smoke too.
*/

test('the gateway serves the app with the TRD headers and routes auth @smoke', async ({ request }) => {
  const index = await request.get('/')
  expect(index.status()).toBe(200)
  const headers = index.headers()
  expect(headers['content-security-policy']).toContain('script-src \'self\'')
  expect(headers['content-security-policy']).toContain('worker-src \'self\'')
  expect(headers['strict-transport-security']).toMatch(/^max-age=31536000/)
  expect(headers['cache-control']).toBe('no-cache')

  // The update check reads these fresh every time (TRD §2.1; F10).
  for (const path of ['/sw.js', '/manifest.webmanifest', '/theme-init.js']) {
    const response = await request.get(path)
    expect(response.status(), path).toBe(200)
    expect(response.headers()['cache-control'], path).toBe('no-cache')
  }

  // auth is up and checks tokens itself; /internal/ never leaves the host.
  const me = await request.get('/api/v1/auth/me')
  expect(me.status()).toBe(401)
  expect(me.headers()['content-type']).toMatch(/^application\/problem\+json/)
  expect((await request.get('/internal/account-links')).status()).toBe(404)
})

test('the login page renders with no CSP violation or uncaught error @smoke', async ({ watched: page }) => {
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
})
