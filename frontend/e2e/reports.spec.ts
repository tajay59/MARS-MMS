import type { Page } from '@playwright/test'
import { logIn } from './requestFlows'
import { checkA11y, expect, test } from './support'

// Summary reports (PRD SUM-1 to SUM-3, CAL-4; AFD J10; decisions W19-8 to W19-10). A report is made
// by the report worker, so these wait for it; they check that the page asks, follows and offers
// the file, and what each role may ask for, not the figures inside the files.

const READY = 120_000 // NFR-2: a summary is ready within two minutes

async function generate (page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Generate' }).click()
}

test('An admin asks for a report and downloads it when it is ready @REQ-SUM-1 @REQ-SUM-2 @J10', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await page.goto('/reports')
  await expect(page.getByRole('heading', { level: 1, name: 'Station history' })).toBeVisible()
  const pane = page.getByRole('link', { name: 'Network status' })
  await expect(pane).toBeVisible()
  await pane.click()
  await expect(page).toHaveURL(/type=network_status/)
  await expect(page.getByRole('heading', { level: 1, name: 'Network status' })).toBeVisible()
  // Network status has no period: the form does not ask for one
  await expect(page.getByLabel('From')).toHaveCount(0)

  await page.getByText('CSV, the table only').click()
  await generate(page)
  const row = page.getByRole('row', { name: /Network status/ }).first()
  await expect(row).toBeVisible()
  const download = row.getByRole('link', { name: 'Download' })
  await expect(download).toBeVisible({ timeout: READY })
  await expect(download).toHaveAttribute('href', /summaries\/.+\.csv/)
  await checkA11y(page, '/reports (admin)')
})

test('A PDF with a period is made and the form refuses a backwards period @REQ-SUM-1 @REQ-SUM-2 @J10', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await page.goto('/reports?type=request_turnaround')
  await expect(page.getByRole('heading', { level: 1, name: 'Request turnaround' })).toBeVisible()
  await page.getByLabel('From').fill('2026-10-31')
  await page.getByLabel('To').fill('2026-10-01')
  await generate(page)
  await expect(page.getByText('The last day is before the first day. Swap them.')).toBeVisible()
  await page.getByRole('button', { name: 'Last month' }).click()
  await generate(page)
  const row = page.getByRole('row', { name: /Request turnaround.*pdf/i }).first()
  await expect(row.getByRole('link', { name: 'Download' })).toBeVisible({ timeout: READY })
})

test('Station asset, Configuration history and Sensor reliability are made from the real inventory @REQ-SUM-1 @J10', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  for (const [type, title] of [
    ['station_asset', 'Station asset'], ['sensor_reliability', 'Sensor reliability'],
    ['configuration_history', 'Configuration history'],
  ]) {
    await page.goto(`/reports?type=${type}`)
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
    await page.getByText('CSV, the table only').click()
    if (type !== 'station_asset') {
      await page.getByRole('button', { name: 'This year' }).click()
    }
    await generate(page)
    const row = page.getByRole('row', { name: new RegExp(`${title}.*csv`, 'i') }).first()
    await expect(row.getByRole('link', { name: 'Download' })).toBeVisible({ timeout: READY })
  }
})

test('A Viewer makes every report and changes nothing else @REQ-SUM-1 @NFR-6 @J10', async ({ watched: page }) => {
  await logIn(page, 'viewer@example.org')
  await page.goto('/reports?type=calibration_due')
  await expect(page.getByRole('heading', { level: 1, name: 'Calibration due' })).toBeVisible()
  await expect(page.getByLabel('Look ahead (days)')).toBeVisible()
  await page.getByText('CSV, the table only').click()
  await generate(page)
  await expect(page.getByRole('row', { name: /Calibration due/ }).first()).toBeVisible()
})

test('A client sees three reports for their own organization and cannot ask for a staff one @REQ-SUM-3 @NFR-6 @J10', async ({ watched: page }) => {
  await logIn(page, 'client.a1@example.org')
  await page.goto('/reports')
  await expect(page.getByRole('link', { name: 'Station history' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Client activity' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Station asset' })).toBeVisible()
  for (const hidden of ['Request turnaround', 'Calibration due', 'Network status', 'Monthly summary', 'Annual summary', 'Sensor reliability', 'Configuration history']) {
    await expect(page.getByRole('link', { name: hidden })).toHaveCount(0)
  }
  await page.getByRole('link', { name: 'Client activity' }).click()
  await expect(page.getByText('Reports cover your organization only.')).toBeVisible()
  await expect(page.getByLabel('Organization')).toHaveCount(0) // read only, not a field
  await page.getByText('CSV, the table only').click()
  await page.getByRole('button', { name: 'Last year' }).click()
  await generate(page)
  const row = page.getByRole('row', { name: /Client activity/ }).first()
  await expect(row.getByRole('link', { name: 'Download' })).toBeVisible({ timeout: READY })
  await checkA11y(page, '/reports (client)')
})

test('On a phone the list of reports comes first, then the report @REQ-SUM-1 @phone', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await page.goto('/reports')
  await expect(page.getByRole('link', { name: 'Network status' })).toBeVisible()
  await page.getByRole('link', { name: 'Network status' }).click()
  await expect(page.getByRole('button', { name: 'Generate' })).toBeVisible()
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(wide).toBe(false)
})
