import type { Page } from '@playwright/test'
import { goInApp, restartOffline, typePin } from './offlineFlows'
import { logIn } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  The offline field session (AUTH-12, ADR-20; W13-3 to W13-8): a technician sets a device PIN, the
  app starts with no signal and asks for it, the right PIN opens the field pages, five wrong ones
  turn offline unlock off, and logging out takes the PIN away. Chromium only: it needs the real
  service worker (F6).
*/

const PIN = '4729'
const WRONG = '1357'

async function setPin (page: Page, pin: string): Promise<void> {
  await page.goto('/profile')
  await page.getByRole('button', { name: 'Set a PIN' }).click()
  await page.getByLabel('PIN', { exact: true }).fill(pin)
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByLabel('Repeat the PIN').fill(pin)
  await page.getByRole('button', { name: 'Save PIN' }).click()
  await expect(page.getByRole('button', { name: 'Change PIN' })).toBeVisible()
}

test('The PIN opens the field pages with no signal, and other pages say they need a connection @AUTH-12 @OFF-3', async ({ watched: page, context }) => {
  await logIn(page, 'tech1@example.org')
  await setPin(page, PIN)

  await restartOffline(page, context)
  await expect(page).toHaveURL(/\/unlock\?next=\/sync/)
  await expect(page.getByRole('heading', { name: 'Unlock your field work' })).toBeVisible()
  await expect(page.getByText('Technician', { exact: true })).toBeVisible()
  await checkA11y(page, '/unlock')

  // A wrong PIN says how many tries are left
  await typePin(page, WRONG)
  await expect(page.getByText('That PIN is not right.')).toBeVisible()
  await expect(page.getByText('4 tries left.')).toBeVisible()

  await typePin(page, PIN)
  await expect(page).toHaveURL(/\/sync$/)
  await expect(page.getByText('All synced')).toBeVisible()

  // Pages that need the server say so
  await goInApp(page, '/requests')
  await expect(page).toHaveURL(/\/needs-connection\?from=\/requests/)
  await expect(page.getByRole('heading', { name: 'This needs a connection' })).toBeVisible()
  await checkA11y(page, '/needs-connection')

  // Signal comes back: Try again signs in for real and opens the page that was wanted
  await context.setOffline(false)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page).toHaveURL(/\/requests$/)
})

test('Five wrong PINs turn offline unlock off until the next login with signal @AUTH-12', async ({ watched: page, context }) => {
  await logIn(page, 'tech1@example.org')
  await setPin(page, PIN)
  await restartOffline(page, context)

  for (let n = 0; n < 5; n++) {
    await typePin(page, WRONG)
    await expect(page.getByText('That PIN is not right.').or(page.getByText('Offline unlock is turned off'))).toBeVisible()
  }
  await expect(page.getByRole('heading', { name: 'Offline unlock is turned off' })).toBeVisible()
  await expect(page.getByText('Your work is saved on this phone.')).toBeVisible()
  await checkA11y(page, '/unlock (turned off)')

  // Still off after the app is closed and opened again: the count is kept on the phone
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Offline unlock is turned off' })).toBeVisible()

  // A login with signal turns it back on (the refresh cookie signs in; no PIN is asked online)
  await context.setOffline(false)
  await page.goto('/sync')
  await expect(page.getByText('All synced')).toBeVisible()
  await context.setOffline(true)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Unlock your field work' })).toBeVisible()
  await typePin(page, PIN)
  await expect(page).toHaveURL(/\/sync$/)
})

test('Logging out takes the PIN away, and the app starts at the login page @AUTH-12', async ({ watched: page, context }) => {
  await logIn(page, 'tech1@example.org')
  await setPin(page, PIN)
  await page.getByRole('button', { name: /Account menu/ }).click()
  await page.getByRole('menuitem', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login$/)

  await restartOffline(page, context, '/login')
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
  await page.goto('/sync')
  await expect(page).toHaveURL(/\/login/)
})

test('A viewer is not offered a PIN @AUTH-12', async ({ watched: page }) => {
  await logIn(page, 'viewer@example.org')
  await page.goto('/profile')
  await expect(page.getByRole('heading', { name: 'My profile' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Offline PIN' })).toHaveCount(0)
})
