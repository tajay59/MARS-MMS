import type { Page } from '@playwright/test'
import { checkA11y, expect, seedPassword, submitPaced, test } from './support'

/*
  The stations list and page (PRD STN-5, CAL-3; DBD "Stations list", "Station page"), on the
  operations demo seed: five made-up stations, three for Organization A in Jamaica and two for B.
*/

async function logIn (page: Page, email: string): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)
}

test('A technician filters the stations and opens one @STN-5 @CAL-3', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/stations')

  const table = page.getByRole('table', { name: /Stations/ })
  await expect(table.getByRole('link', { name: 'JM-KIN-001' })).toBeVisible()
  await expect(table.getByRole('link', { name: 'TT-POS-001' })).toBeVisible()
  await expect(table.getByRole('columnheader', { name: 'Organization' })).toBeVisible()
  await checkA11y(page, '/stations')

  // Status from the pane, kept in the URL
  await page.getByRole('button', { name: /^Offline/ }).click()
  await expect(page).toHaveURL(/status=offline/)
  await expect(table.getByRole('link', { name: 'JM-BLU-003' })).toBeVisible()
  await expect(table.getByRole('link', { name: 'JM-KIN-001' })).toHaveCount(0)

  await page.getByRole('button', { name: /^All/ }).click()
  await page.getByRole('searchbox', { name: /Search stations/ }).fill('harbour')
  await expect(table.getByRole('row')).toHaveCount(2) // the header and Kingston Harbour

  await table.getByRole('link', { name: 'JM-KIN-001' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Kingston Harbour' })).toBeVisible()
  await expect(page.getByText('Gate code with the harbour office.')).toBeVisible()
  await checkA11y(page, '/stations/:id (overview)')

  await page.getByRole('tab', { name: /Sensors/ }).click()
  await expect(page).toHaveURL(/tab=sensors/)
  await expect(page.getByRole('cell', { name: 'V-23001' })).toBeVisible()
  await checkA11y(page, '/stations/:id (sensors)')

  await page.getByRole('tab', { name: 'Calibration' }).click()
  await expect(page.getByRole('table', { name: /Calibrations at Kingston Harbour/ })
    .or(page.getByText('No calibrations recorded at this station yet.'))).toBeVisible()
})

test('A client sees only their organization’s stations, and less of each @STN-5', async ({ watched: page }) => {
  await logIn(page, 'client.a1@example.org')
  await page.goto('/stations')

  const table = page.getByRole('table', { name: /Stations/ })
  await expect(table.getByRole('link', { name: 'JM-KIN-001' })).toBeVisible()
  await expect(table.getByRole('link', { name: /^TT-/ })).toHaveCount(0)
  await expect(table.getByRole('columnheader', { name: 'Organization' })).toHaveCount(0)
  await checkA11y(page, '/stations (client)')

  await table.getByRole('link', { name: 'JM-KIN-001' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Kingston Harbour' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Calibration' })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Configurations' })).toHaveCount(0)
  await checkA11y(page, '/stations/:id (client)')

  // Another organization's station and a missing one look the same (ADR-16)
  await page.goto('/stations/01900000-0000-7000-8000-000000000000')
  await expect(page.getByText('We can’t find this station.')).toBeVisible()
})
