import type { Page } from '@playwright/test'
import { checkA11y, expect, seedPassword, submitPaced, test } from './support'

/*
  The stations list and page (PRD STN-5, CAL-3; approved "AWS-MMS Stations redesign"), on the
  operations demo seed: five made-up stations, three for Organization A in Jamaica and two for B;
  JM-BLU-003 is offline. The list opens on Needs attention; All stations is the register.
*/

const NEXT_STEP = /^(Open the visit|Open the request|Raise a request):/

async function logIn (page: Page, email: string): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)
}

test('A technician sees what needs attention, filters the register and opens a station @STN-5 @CAL-3', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/stations')

  // Needs attention first: the counts filter it, and each row has its next step
  const lists = page.getByRole('navigation', { name: 'Station lists' })
  await expect(lists.getByRole('link', { name: /Needs attention/ })).toHaveAttribute('aria-current', 'page')
  const attention = page.getByRole('list', { name: 'Stations that need attention' })
  const blue = attention.getByRole('listitem').filter({ hasText: 'JM-BLU-003' })
  await expect(blue.getByText('Marked offline', { exact: false })).toBeVisible()
  await expect(blue.getByRole('link', { name: NEXT_STEP })).toBeVisible()
  await checkA11y(page, '/stations (needs attention)')
  await page.emulateMedia({ colorScheme: 'dark' })
  await checkA11y(page, '/stations (needs attention) (dark)')
  await page.emulateMedia({ colorScheme: 'light' })

  await page.getByRole('group', { name: 'Show only' }).getByRole('button', { name: /^Offline/ }).click()
  await expect(page).toHaveURL(/problem=offline/)
  await expect(attention.getByText('Offline', { exact: true }).first()).toBeVisible()
  await expect(attention.getByRole('listitem').filter({ hasText: 'Degraded' })).toHaveCount(0)

  // The register: status chips and filters above the table, kept in the URL
  await lists.getByRole('link', { name: /All stations/ }).click()
  await expect(page).toHaveURL(/view=all/)
  const table = page.getByRole('table', { name: /Stations/ })
  await expect(table.getByRole('link', { name: 'JM-KIN-001' })).toBeVisible()
  await expect(table.getByRole('link', { name: 'TT-POS-001' })).toBeVisible()
  await expect(table.getByRole('columnheader', { name: 'Organization' })).toBeVisible()
  await checkA11y(page, '/stations?view=all')

  await page.getByRole('group', { name: 'Filter by status' }).getByRole('button', { name: /^Offline/ }).click()
  await expect(page).toHaveURL(/status=offline/)
  await expect(table.getByRole('link', { name: 'JM-BLU-003' })).toBeVisible()
  await expect(table.getByRole('link', { name: 'JM-KIN-001' })).toHaveCount(0)

  await page.getByRole('group', { name: 'Filter by status' }).getByRole('button', { name: /^All/ }).click()
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

test('A client sees only their organization’s stations, with no actions to take @STN-5', async ({ watched: page }) => {
  await logIn(page, 'client.a1@example.org')
  await page.goto('/stations')

  await expect(page.getByRole('link', { name: NEXT_STEP })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Report a problem' })).toBeVisible()
  await checkA11y(page, '/stations (client)')

  await page.getByRole('navigation', { name: 'Station lists' }).getByRole('link', { name: /All stations/ }).click()
  const table = page.getByRole('table', { name: /Stations/ })
  await expect(table.getByRole('link', { name: 'JM-KIN-001' })).toBeVisible()
  await expect(table.getByRole('link', { name: /^TT-/ })).toHaveCount(0)
  await expect(table.getByRole('columnheader', { name: 'Organization' })).toHaveCount(0)

  await table.getByRole('link', { name: 'JM-KIN-001' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Kingston Harbour' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Calibration' })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Configurations' })).toHaveCount(0)
  await checkA11y(page, '/stations/:id (client)')

  // Another organization's station and a missing one look the same (ADR-16)
  await page.goto('/stations/01900000-0000-7000-8000-000000000000')
  await expect(page.getByText('We can’t find this station.')).toBeVisible()
})

test('A technician adds a station with the essentials, then completes it @STN-1 @STN-2', async ({ watched: page }) => {
  const code = `E2E-${Date.now().toString(36).toUpperCase()}`
  await logIn(page, 'tech1@example.org')
  await page.goto('/stations')
  await page.getByRole('link', { name: 'New station' }).click()
  await expect(page).toHaveURL(/\/stations\/new/)
  await expect(page.getByRole('heading', { level: 1, name: 'New station' })).toBeVisible()
  await expect(page.getByRole('application', { name: /^Map\./ })).toBeVisible()
  await checkA11y(page, '/stations/new')
  await page.emulateMedia({ colorScheme: 'dark' })
  await checkA11y(page, '/stations/new (dark)')
  await page.emulateMedia({ colorScheme: 'light' })

  // An empty form says what is missing, on each field
  await page.getByRole('button', { name: 'Add station' }).click()
  await expect(page.getByText('Enter the station’s name')).toBeVisible()
  await expect(page.getByText('Choose the owner organization')).toBeVisible()

  // A click on the map puts the pin and fills the fields
  await page.getByRole('application', { name: /^Map\./ }).click({ position: { x: 200, y: 160 } })
  await expect(page.getByLabel('Latitude', { exact: true })).not.toHaveValue('')

  await page.getByLabel('Code', { exact: true }).fill(code.toLowerCase())
  await page.getByLabel('Name', { exact: true }).fill('E2E Test Station')
  await page.getByLabel('Owner organization').click()
  await page.getByRole('option', { name: 'Organization A' }).click()
  await page.getByLabel('Country').fill('Jamaica') // a long list: type to find it
  await page.getByRole('option', { name: 'Jamaica' }).click()
  await expect(page.getByLabel('Time zone')).toHaveValue('America/Jamaica') // a one-zone country
  await page.getByLabel('Latitude', { exact: true }).fill('18.0123')
  await page.getByLabel('Longitude', { exact: true }).fill('-76.8')

  // Another station has the code
  await page.getByLabel('Code', { exact: true }).fill('JM-KIN-001')
  await page.getByRole('button', { name: 'Add station' }).click()
  await expect(page.getByText('Another station has this code. Use a different one.')).toBeVisible()

  await page.getByLabel('Code', { exact: true }).fill(code.toLowerCase())
  await page.getByRole('button', { name: 'Add station' }).click()
  await expect(page).toHaveURL(/\/stations\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('heading', { level: 1, name: 'E2E Test Station' })).toBeVisible()
  await expect(page.getByText(code, { exact: true }).first()).toBeVisible() // saved in capitals

  // The rest on the full form: a parameter and the name; the owner is fixed
  await page.getByRole('link', { name: 'Edit' }).click()
  await expect(page).toHaveURL(/\/edit/)
  await expect(page.getByLabel('Owner organization')).toHaveAttribute('readonly', '')
  await expect(page.getByRole('application', { name: /^Map\./ })).toBeVisible()
  await checkA11y(page, '/stations/:id/edit')
  await page.getByLabel('Add a parameter').fill('soil_t')
  await page.getByLabel('Add a parameter').press('Enter')
  await page.getByLabel('Name', { exact: true }).fill('E2E Test Station East')

  // Leaving with a change asks first; staying keeps it
  await page.getByRole('button', { name: 'Cancel' }).first().click()
  await expect(page.getByRole('alertdialog', { name: 'Leave without saving?' })).toBeVisible()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue('E2E Test Station East')

  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'E2E Test Station East' })).toBeVisible()
  await expect(page.getByText('SOIL_T').first()).toBeVisible()
  await expect(page).not.toHaveURL(/\/edit/)
})

test('Viewers and clients do not get the station forms @STN-1 @STN-2', async ({ watched: page }) => {
  await logIn(page, 'viewer@example.org')
  await page.goto('/stations?view=all')
  await expect(page.getByRole('table', { name: /Stations/ })).toBeVisible()
  await expect(page.getByRole('link', { name: 'New station' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: NEXT_STEP })).toHaveCount(0)
  await page.goto('/stations/new')
  await expect(page).toHaveURL(/\/stations$/) // back to the list
})

test('On a phone the attention rows stack, with large next steps @STN-5 @phone', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/stations')
  const row = page.getByRole('list', { name: 'Stations that need attention' }).getByRole('listitem').filter({ hasText: 'JM-BLU-003' })
  const step = row.getByRole('link', { name: NEXT_STEP })
  await expect(step).toBeVisible()
  expect((await step.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  await checkA11y(page, '/stations (phone)')
})
