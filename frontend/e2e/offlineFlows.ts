import type { BrowserContext, Page } from '@playwright/test'
import { expect } from './support'

// Steps the offline journeys share (unlock.spec.ts, prepare.spec.ts).

/** Offline, restarted on /sync: the app asks for the PIN. */
export async function restartOffline (page: Page, context: BrowserContext, path = '/sync'): Promise<void> {
  await page.goto(path)
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)
  await context.setOffline(true)
  await page.reload()
}

export async function typePin (page: Page, pin: string): Promise<void> {
  for (const digit of pin) {
    await page.getByRole('button', { name: digit, exact: true }).click()
  }
  await page.getByRole('button', { name: 'Unlock', exact: true }).click()
}

/** Moves inside the running app, without a page load (a load would ask for the PIN again). */
export async function goInApp (page: Page, path: string): Promise<void> {
  await page.evaluate(async target => {
    const root = document.querySelector('#app') as unknown as { __vue_app__: { config: { globalProperties: { $router: { push: (to: string) => Promise<unknown> } } } } }
    await root.__vue_app__.config.globalProperties.$router.push(target)
  }, path)
}
