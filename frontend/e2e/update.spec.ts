import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from './support'

/*
  The update prompt between two releases (F5; pwa skill service-worker.md §3). A deploy that
  changes any precached file changes sw.js, so the browser installs the new worker and leaves
  it waiting. Here the next release is made by changing sw.js's bytes in the folder Nginx serves
  (compose.yml mounts frontend/dist, or MMS_SPA_DIR), which starts the same lifecycle.
  Local stack only: it writes to the served files. On staging, check it by hand after two deploys.
*/

const dist = path.resolve(import.meta.dirname, '..', process.env.MMS_SPA_DIR ?? 'dist')
const swFile = path.join(dist, 'sw.js')

test.skip(Boolean(process.env.MMS_E2E_URL), 'needs the local stack: it changes the served sw.js')

test('a new release waits for the user, survives "Later" and applies on "Reload now" @NFR-4', async ({ watched: page }) => {
  await page.goto('/login')
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)
  const firstWorker = await page.evaluate(() => navigator.serviceWorker.controller!.scriptURL)

  // The technician has typed something when the next release arrives.
  await page.getByLabel('Email').fill('typed.before@example.org')

  const original = readFileSync(swFile)
  try {
    writeFileSync(swFile, Buffer.concat([original, Buffer.from(`\n// next release ${Date.now()}\n`)]))

    // The app looks for a release when it comes back to the foreground (usePwa).
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
    const prompt = page.getByText('A new version of MARS-MMS is ready')
    await expect(prompt).toBeVisible()

    // Nothing reloaded on its own: the page and what was typed are still there.
    await expect(page.getByLabel('Email')).toHaveValue('typed.before@example.org')
    const state = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      return { waiting: Boolean(registration?.waiting), active: registration?.active?.state }
    })
    expect(state).toEqual({ waiting: true, active: 'activated' })

    // "Later" hides the prompt; the waiting release is offered again the next time the app opens.
    await page.getByRole('button', { name: 'Later' }).click()
    await expect(prompt).toBeHidden()
    await page.reload()
    await expect(prompt).toBeVisible()

    // "Reload now" activates the new worker and reloads every open tab under it.
    await Promise.all([
      page.waitForEvent('load'),
      page.getByRole('button', { name: 'Reload now' }).click(),
    ])
    await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
    await expect(prompt).toBeHidden()
    const after = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      return {
        waiting: Boolean(registration?.waiting),
        controlled: navigator.serviceWorker.controller?.scriptURL,
      }
    })
    expect(after).toEqual({ waiting: false, controlled: firstWorker })
  } finally {
    writeFileSync(swFile, original)
  }
})
