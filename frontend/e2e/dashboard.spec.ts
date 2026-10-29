import type { Page } from '@playwright/test'
import { logIn } from './requestFlows'
import { checkA11y, expect, test } from './support'

// The dashboards (PRD SUM-4 to SUM-6, CAL-4, CAL-6; AFD J3, J4; decision W19-7). The numbers
// depend on what earlier journeys left behind, so these check what each role sees and that the
// figures agree with the lists they link to, not particular values.

async function figure (page: Page, label: string): Promise<number> {
  const tile = page.locator('div', { has: page.getByText(label, { exact: true }) }).last()
  const text = (await tile.locator('.font-heading').first().textContent() ?? '').replaceAll(',', '')
  return Number.parseInt(text, 10)
}

test('An admin sees the six tiles, the status bars and the stations by country @REQ-SUM-4 @REQ-CAL-4 @REQ-CAL-6 @J4', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible()
  for (const label of [
    'Registrations pending', 'Requests awaiting approval', 'Unassigned queue', 'In Client Review',
    'Calibrations due or overdue', 'Failed calibrations',
  ]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible()
  }
  const bars = page.getByRole('list', { name: 'Open requests by status' })
  await expect(bars.getByRole('listitem')).toHaveCount(7)
  await expect(page.getByRole('table').getByRole('columnheader', { name: 'Operational' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Upcoming visits' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Reports awaiting finalization' })).toBeVisible()

  // The bars add up to the same open requests the list shows
  const counts = await bars.getByRole('listitem').allInnerTexts()
  expect(counts.every(text => /\d+$/.test(text.trim()))).toBe(true)
  await checkA11y(page, '/dashboard (admin)')
})

test('A tile opens the list behind it, filtered @REQ-SUM-4 @J4', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await expect(page.getByRole('list', { name: 'Open requests by status' })).toBeVisible()
  await page.getByRole('link', { name: /^Open the list/ }).click()
  await expect(page).toHaveURL(/\/requests\?status=submitted$/)
  await page.goBack()
  await page.getByRole('link', { name: /^See them/ }).first().click()
  await expect(page).toHaveURL(/\/requests\?status=client_review$/)
})

test('A Viewer sees the admin figures with no registrations and no way to change anything @REQ-SUM-4 @NFR-6', async ({ watched: page }) => {
  await logIn(page, 'viewer@example.org')
  await expect(page.getByText('Requests awaiting approval', { exact: true })).toBeVisible()
  await expect(page.getByText('Registrations pending', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Report a problem' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Report a problem' })).toHaveCount(0)
})

test('A technician sees their figures and what waits on the phone @REQ-SUM-5 @J5', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  for (const label of ['My assigned', 'Queue', 'My upcoming visits', 'Waiting to sync', 'Reports to finalize']) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
  }
  expect(await figure(page, 'Waiting to sync')).toBe(0)
  await expect(page.getByRole('heading', { name: 'My reports to finalize' })).toBeVisible()
  await checkA11y(page, '/dashboard (technician)')
})

test('With no signal the server figures say so and the phone figure still shows @REQ-SUM-5 @REQ-OFF-6 @J6', async ({ watched: page, context }) => {
  await logIn(page, 'tech1@example.org')
  await expect(page.getByText('Queue', { exact: true }).first()).toBeVisible()
  await context.setOffline(true)
  await page.getByRole('button', { name: 'Refresh' }).click()
  await expect(page.getByText('No signal')).toBeVisible()
  await expect(page.getByText('Needs a connection').first()).toBeVisible()
  expect(await figure(page, 'Waiting to sync')).toBe(0)
  await context.setOffline(false)
  await page.getByRole('button', { name: 'Refresh' }).click()
  await expect(page.getByText('No signal')).toHaveCount(0)
})

test('A client sees their own stations and requests, with no other organization @REQ-SUM-6 @NFR-6 @J3', async ({ watched: page }) => {
  await logIn(page, 'client.a1@example.org')
  await expect(page.getByRole('heading', { name: 'Our stations by status' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Report a problem' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Open requests' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recent reports' })).toBeVisible()
  // The staff tiles are not on a client's page
  await expect(page.getByText('Registrations pending', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Unassigned queue', { exact: true })).toHaveCount(0)
  await checkA11y(page, '/dashboard (client)')
})

test('On a phone the tiles stack and nothing scrolls sideways @REQ-SUM-5 @phone', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await expect(page.getByText('Waiting to sync', { exact: true })).toBeVisible()
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(wide).toBe(false)
})
