import type { Page } from '@playwright/test'
import { checkA11y, expect, seedPassword, submitPaced, test } from './support'

/*
  Settings (AFD 1.4, decision W4-11) and the brand colours everyone sees (W4-12): an admin makes
  a theme from one colour, previews it, saves it for everyone, and goes back to the built-in one.
  Leaves the stack on the built-in colours.
*/

const ADMIN = 'admin@example.org'

test.describe.configure({ mode: 'serial' })

function primary (page: Page): Promise<string> {
  return page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--v-theme-primary').trim())
}

test('An admin changes the brand colours for everyone, then goes back to the built-in ones @AUD-1', async ({ watched: page, browser }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ADMIN)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)

  // Settings is the last Admin tab; Appearance opens first
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: /^Admin/ }).click()
  await page.getByRole('navigation', { name: 'Admin pages' }).getByRole('link', { name: 'Settings' }).click()
  await expect(page).toHaveURL(/\/admin\/settings$/)
  await expect(page.getByRole('heading', { name: 'Animations' })).toBeVisible()
  await checkA11y(page, '/admin/settings (appearance)')

  await page.getByRole('link', { name: 'Brand colours' }).click()
  await expect(page).toHaveURL(/\/admin\/settings\/colours$/)
  await checkA11y(page, '/admin/settings/colours')
  const builtIn = await primary(page)
  const before = await (await page.request.get('/api/v1/auth/branding')).json() as { version: number }

  // From one colour: a preview on this screen only
  await page.getByLabel('Brand colour', { exact: true }).fill('#7B1FA2')
  await page.getByRole('button', { name: 'Make the themes' }).click()
  await expect(page.getByRole('heading', { name: /^Preview:/ })).toBeVisible()
  await expect.poll(() => primary(page)).not.toBe(builtIn)
  const purple = await primary(page)
  await checkA11y(page, '/admin/settings/colours (a generated theme)')

  await page.getByRole('button', { name: 'Save for everyone' }).click()
  await expect(page.getByText(/^Saved\. Everyone sees the new colours/)).toBeVisible()
  const saved = await (await page.request.get('/api/v1/auth/branding')).json() as { version: number, material: unknown }
  expect(saved.version).toBe(before.version + 1)
  expect(saved.material).not.toBeNull()

  // Someone else, signed out on another device, gets them on the login page
  const other = await browser.newContext({ ignoreHTTPSErrors: true })
  const visitor = await other.newPage()
  await visitor.goto('/login')
  await expect.poll(() => primary(visitor)).toBe(purple)
  await other.close()

  // Back to the built-in colours, for everyone
  await page.getByRole('button', { name: 'Go back to the built-in colours' }).click()
  await page.getByRole('button', { name: 'Use the built-in colours for everyone' }).click()
  await expect(page.getByText(/^Saved\./)).toBeVisible()
  await expect.poll(() => primary(page)).toBe(builtIn)
  const after = await (await page.request.get('/api/v1/auth/branding')).json() as { version: number, material: unknown }
  expect(after).toMatchObject({ version: before.version + 2, material: null })
})
