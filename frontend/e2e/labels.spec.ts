import type { Page } from '@playwright/test'
import { checkA11y, expect, seedPassword, submitPaced, test } from './support'

/*
  Station labels, scanning and the map (PRD QR-1 to QR-7, MAP-1 to MAP-3; AFD §5.3), on the
  operations demo seed. The camera itself is not tested here: headless Chromium has none, so the
  scanner's decoding is covered by Vitest (a drawn code is read back) and its look by the real
  phones (W7 exit check). What a scan *opens*, `/s/:token`, is the same page either way.
*/

async function logIn (page: Page, email: string, next?: string): Promise<void> {
  await page.goto(next ? `/login?next=${encodeURIComponent(next)}` : '/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(next ? new RegExp(`${next.replaceAll('/', String.raw`\/`)}$`) : /\/dashboard$/)
}

/** Opens a station from the list and returns its id and QR token, as the page received them. */
async function stationOf (page: Page, code: string): Promise<{ id: string, token: string }> {
  await page.goto('/stations')
  const [response] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'GET' && /\/api\/v1\/stations\/[\da-f-]{36}$/.test(r.url())),
    page.getByRole('table', { name: /Stations/ }).getByRole('link', { name: code }).click(),
  ])
  const body = await response.json() as { id: string, qr_token: string }
  return { id: body.id, token: body.qr_token }
}

test('A label opens its station, a replaced one says so, and a client sees only their own @QR-2 @QR-3 @QR-4 @QR-7', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  const own = await stationOf(page, 'JM-KIN-001') // Organization A
  const other = await stationOf(page, 'TT-POS-001') // Organization B

  // The station page shows the label's code, and the admin can replace it
  const blue = await stationOf(page, 'JM-BLU-003')
  await expect(page.getByRole('heading', { name: 'QR label' })).toBeVisible()
  await expect(page.getByRole('img', { name: /QR code for/ })).toBeVisible()
  await checkA11y(page, '/stations/:id (QR label)')

  await page.goto(`/s/${blue.token}`)
  await expect(page).toHaveURL(new RegExp(`/stations/${blue.id}$`))

  await page.getByRole('button', { name: 'Replace the label' }).click()
  const dialog = page.getByRole('dialog', { name: /Replace the label for/ })
  await expect(dialog).toContainText('The label on the station will stop working.')
  const replaced = page.waitForResponse(r => r.url().endsWith('/qr/regenerate'))
  await dialog.getByRole('button', { name: 'Replace the label' }).click()
  const fresh = (await (await replaced).json() as { qr_token: string }).qr_token
  expect(fresh).not.toBe(blue.token)
  await expect(page.getByText('Replaced just now. Print the new label.')).toBeVisible()

  // The old label says it was replaced; the new one opens the station
  await page.goto(`/s/${blue.token}`)
  await expect(page.getByRole('heading', { name: 'This code is no longer valid' })).toBeVisible()
  await checkA11y(page, '/s/:token (replaced)')
  await page.goto(`/s/${fresh}`)
  await expect(page).toHaveURL(new RegExp(`/stations/${blue.id}$`))

  // A code nobody has is not found
  await page.goto('/s/not-a-real-token-123')
  await expect(page.getByRole('heading', { name: 'We can’t find that station' })).toBeVisible()

  // Signed out, the label goes to the login page and comes back to the station afterwards
  await page.context().clearCookies()
  await page.goto(`/s/${own.token}`)
  await expect(page).toHaveURL(/\/login/)
  await page.getByLabel('Email').fill('client.a1@example.org')
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(new RegExp(`/stations/${own.id}$`))
  // A client has no label card: the server leaves the token out (rule 6)
  await expect(page.getByRole('heading', { name: 'QR label' })).toHaveCount(0)

  // Another organization's label looks like a missing one (ADR-16)
  await page.goto(`/s/${other.token}`)
  await expect(page.getByRole('heading', { name: 'We can’t find that station' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Scan another label' })).toHaveCount(0) // clients have no scanner
})

test('A technician finds a station by typing its code on /scan @QR-2', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/scan')

  // The camera is asked for only after a plain explanation
  await expect(page.getByRole('heading', { name: 'Scan a station label' })).toBeVisible()
  await checkA11y(page, '/scan')
  await page.getByRole('button', { name: 'Turn on the camera' }).click()
  // Headless Chromium has no camera: the page says so and offers the code field
  await expect(page.getByRole('heading', { name: /The camera/ })).toBeVisible()
  await checkA11y(page, '/scan (no camera)')

  await page.getByRole('button', { name: 'Enter the station code' }).click()
  await page.getByLabel('Station code').fill('jm-kin')
  const results = page.getByRole('region', { name: 'Matching stations' })
  await expect(results.getByRole('link', { name: 'JM-KIN-001' })).toBeVisible()
  await checkA11y(page, '/scan (typing a code)')
  await results.getByRole('link', { name: 'JM-KIN-001' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Kingston Harbour' })).toBeVisible()

  // A code the label scanner reads is a MARS-MMS address: anything else is refused before it gets that far
  await page.goto('/scan?mode=code')
  await page.getByLabel('Station code').fill('zzz-nothing')
  await expect(page.getByText('No match')).toBeVisible()
})

test.describe('map', () => {
  test('Stations appear on the map and open from it @MAP-1 @MAP-2', async ({ watched: page }) => {
    // The basemap is a file on our own host, read in byte ranges (W7-9). With the extract in
    // infra/tiles the answer is 206; CI has none (404), and the map still works on a blank
    // background. Either way the page asked in ranges and the CSP let it.
    const tileRange = page.waitForResponse(response => response.url().includes('/tiles/') && response.request().headers().range !== undefined)
    await logIn(page, 'tech1@example.org')

    // One station by the address, so it is not folded into a cluster
    await page.goto('/map?q=JM-KIN-001')
    const marker = page.getByRole('button', { name: /^Kingston Harbour, JM-KIN-001, / })
    await expect(marker).toBeVisible()
    await expect(page.getByRole('link', { name: 'OpenStreetMap' })).toBeVisible() // the attribution stays visible
    expect([206, 404]).toContain((await tileRange).status())
    await expect(page.getByText('Several stations: zoom in')).toBeVisible()
    await checkA11y(page, '/map')

    await marker.click()
    await expect(page.getByText('Open station')).toBeVisible()
    await page.getByRole('link', { name: 'Open station' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Kingston Harbour' })).toBeVisible()
  })

  test('A client sees only their organization’s stations on the map @MAP-3', async ({ watched: page }) => {
    await logIn(page, 'client.a1@example.org')
    await page.goto('/map')
    await expect(page.getByRole('heading', { level: 1, name: 'Map' })).toBeVisible()
    await expect(page.getByLabel('Organization')).toHaveCount(0)
    await expect(page.getByText(/of \d+ stations shown/)).toBeVisible()
    await expect(page.getByRole('button', { name: /TT-POS-001/ })).toHaveCount(0)
  })
})

test('An admin makes a sheet of labels @QR-6', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await page.goto('/admin/stations-tools')
  await expect(page.getByRole('heading', { level: 1, name: 'QR labels' })).toBeVisible()

  await page.getByRole('checkbox', { name: /JM-KIN-001/ }).check()
  await page.getByRole('checkbox', { name: /TT-POS-001/ }).check()
  await expect(page.getByText('2 selected of')).toBeVisible()
  await expect(page.getByText('1 page · 10 labels to a page · 98 × 55 mm')).toBeVisible()
  await page.getByLabel('Contact phone (optional)').fill('+1 876 555 0100')
  await checkA11y(page, '/admin/stations-tools')

  await page.getByRole('button', { name: 'Make label sheet' }).click()
  const open = page.getByRole('link', { name: 'Open PDF' })
  await expect(open).toBeVisible({ timeout: 60_000 })
  await expect(open).toHaveAttribute('href', /^https:\/\/files\.mms\.localhost\//)
  await expect(page.getByText(/Station labels · 1 page · 2 labels/)).toBeVisible()

  // A technician has no label tool: it looks like a page that does not exist
  await page.context().clearCookies()
  await logIn(page, 'tech1@example.org')
  await page.goto('/admin/stations-tools')
  await expect(page.getByRole('heading', { name: 'QR labels' })).toHaveCount(0)
})

test('The scanner and a scanned label fit the field shell on a phone @phone @QR-2', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/scan')
  // The field shell: its own top bar and the bottom bar, with Scan current
  await expect(page.getByRole('heading', { level: 1, name: 'Scan' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Field' }).getByRole('link', { name: 'Scan' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('button', { name: 'Turn on the camera' })).toBeVisible()
  await checkA11y(page, '/scan (phone)')

  await page.goto('/s/not-a-real-token-123')
  await expect(page.getByRole('heading', { name: 'We can’t find that station' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Scan another label' })).toBeVisible()
  await checkA11y(page, '/s/:token (phone)')
})
