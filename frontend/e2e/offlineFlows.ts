import type { Browser, BrowserContext, Page } from '@playwright/test'
import { claimedRequest } from './requestFlows'
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

/** A planned visit to both stations, owned by Tech 1. Returns its path. */
export async function plannedVisit (page: Page, browser: Browser, title: string): Promise<string> {
  const path = await claimedRequest(browser, title)
  await page.goto(path)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  await page.getByRole('dialog', { name: 'Schedule visit' }).getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/VR-\d{4}-\d{4}-01 is planned\./)).toBeVisible()
  await page.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ }).getByRole('link', { name: /VR-/ }).click()
  await expect(page).toHaveURL(/\/visits\/[\da-f-]{36}$/)
  return new URL(page.url()).pathname
}
