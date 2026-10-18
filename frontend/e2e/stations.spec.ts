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

test('A technician adds a station, edits it, and is warned before leaving unsaved changes @STN-1 @STN-2', async ({ watched: page }) => {
  const code = `E2E-${Date.now().toString(36).toUpperCase()}`
  await logIn(page, 'tech1@example.org')
  await page.goto('/stations')
  await page.getByRole('link', { name: 'New station' }).click()
  await expect(page).toHaveURL(/\/stations\/new/)
  await expect(page.getByRole('heading', { level: 1, name: 'New station' })).toBeVisible()
  await checkA11y(page, '/stations/new')

  // An empty form says what is missing, with a summary linked to each field
  await page.getByRole('button', { name: 'Create station' }).click()
  await expect(page.getByText(/Fix \d+ things to save/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Enter the station’s name' })).toBeVisible()

  await page.getByLabel('Code', { exact: true }).fill(code.toLowerCase())
  await page.getByLabel('Name', { exact: true }).fill('E2E Test Station')
  await page.getByLabel('Owner organization').click()
  await page.getByRole('option', { name: 'Organization A' }).click()
  await page.getByLabel('Country').fill('Jamaica') // a long list: type to find it
  await page.getByRole('option', { name: 'Jamaica' }).click()
  await expect(page.getByLabel('Time zone')).toHaveValue('America/Jamaica') // a one-zone country
  await page.getByLabel('Latitude').fill('18.0123')
  await page.getByLabel('Longitude').fill('-76.8')
  await expect(page.getByRole('img', { name: 'Location 18.0123, -76.8000' })).toBeVisible()
  await page.getByRole('button', { name: '+ AT' }).click()
  await page.getByLabel('Add a parameter').fill('soil_t')
  await page.getByLabel('Add a parameter').press('Enter')
  await expect(page.getByText('2 of 40')).toBeVisible()
  await page.getByLabel('Logger model').fill('CR1000X')

  // Another station has the code
  await page.getByLabel('Code', { exact: true }).fill('JM-KIN-001')
  await page.getByRole('button', { name: 'Create station' }).click()
  await expect(page.getByText('Another station has this code. Use a different one.')).toBeVisible()

  await page.getByLabel('Code', { exact: true }).fill(code.toLowerCase())
  await page.getByRole('button', { name: 'Create station' }).click()
  await expect(page).toHaveURL(/\/stations\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('heading', { level: 1, name: 'E2E Test Station' })).toBeVisible()
  await expect(page.getByText(code, { exact: true }).first()).toBeVisible() // saved in capitals
  await expect(page.getByText('SOIL_T').first()).toBeVisible()

  // Edit: only the name changes; the owner is fixed
  await page.getByRole('link', { name: 'Edit' }).click()
  await expect(page).toHaveURL(/\/edit/)
  await expect(page.getByLabel('Owner organization')).toHaveAttribute('readonly', '')
  await checkA11y(page, '/stations/:id/edit')
  await page.getByLabel('Name', { exact: true }).fill('E2E Test Station East')

  // Leaving with a change asks first; staying keeps it
  await page.getByRole('button', { name: 'Cancel' }).first().click()
  await expect(page.getByRole('alertdialog', { name: 'Leave without saving?' })).toBeVisible()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue('E2E Test Station East')

  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'E2E Test Station East' })).toBeVisible()
  await expect(page).not.toHaveURL(/\/edit/)
})

test('Viewers and clients do not get the station forms @STN-1 @STN-2', async ({ watched: page }) => {
  await logIn(page, 'viewer@example.org')
  await page.goto('/stations')
  await expect(page.getByRole('table', { name: /Stations/ })).toBeVisible()
  await expect(page.getByRole('link', { name: 'New station' })).toHaveCount(0)
  await page.goto('/stations/new')
  await expect(page).toHaveURL(/\/stations$/) // back to the list
})
