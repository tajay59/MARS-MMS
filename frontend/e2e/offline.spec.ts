import { expect, test } from './support'

/*
  The minimal service worker (F5; pwa skill checklists.md): the app shell opens with no signal
  after one online visit, and Cache Storage holds the precache only, never an API response
  (TRD §7.6, §13.3). Chromium only: Playwright's service-worker support (F6).
*/

test('the app opens offline from the precache, and no API response is cached @NFR-4 @smoke', async ({ watched: page, context }) => {
  await page.goto('/login')
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })
  // First install: clientsClaim() puts the open page under the worker without a reload.
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)

  await context.setOffline(true)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()

  // A deep link with no signal: the navigation fallback serves index.html, the router takes over.
  await page.goto('/sync')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()

  const cached = await page.evaluate(async () => {
    const urls: string[] = []
    for (const name of await caches.keys()) {
      const cache = await caches.open(name)
      urls.push(...(await cache.keys()).map(r => `${name} ${new URL(r.url).pathname}`))
    }
    return urls
  })
  expect(cached.length).toBeGreaterThan(10)
  expect(cached.every(entry => entry.startsWith('workbox-precache'))).toBe(true)
  expect(cached.some(entry => entry.includes('/api/'))).toBe(false)
  await context.setOffline(false)
})
