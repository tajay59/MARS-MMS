import { logIn, submitRequest, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

// The audit log and the History tab (PRD AUD-4 to AUD-6; AFD J10; decisions W19-1, W19-2, W19-4).
// The trail is written by a consumer after each change, so a step that expects a new record
// looks again until it arrives.

test('An admin searches the audit log, opens a record and exports the search @REQ-AUD-4 @J10', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await page.goto('/admin/audit')
  await expect(page.getByRole('heading', { level: 1, name: 'Audit log' })).toBeVisible()
  await expect(page.getByText(/records match, newest first/)).toBeVisible()

  // A filter is in the address, so a link shares the search
  await page.getByLabel('Action').fill('auth.login_succeeded')
  await expect(page).toHaveURL(/action=auth\.login_succeeded/)
  const rows = page.getByRole('region', { name: 'Audit records' }).getByRole('row')
  await expect(rows.nth(1)).toContainText('auth.login_succeeded')

  // A record opens in full, with its place in the chain
  await rows.nth(1).getByRole('button').click()
  await expect(page).toHaveURL(/seq=\d+/)
  await expect(page.getByRole('heading', { name: /^Record [\d,]+$/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Chain' })).toBeVisible()
  await expect(page.getByText('Before it', { exact: true })).toBeVisible()
  await checkA11y(page, '/admin/audit (record open)')
  await page.getByRole('button', { name: 'Close the record' }).click()
  await expect(page).not.toHaveURL(/seq=/)

  // The search is exported as a file, and the export says it is recorded
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV' }).click()
  expect((await download).suggestedFilename()).toMatch(/^audit-log-\d{8}\.csv$/)
  await expect(page.getByText(/This export is recorded in the audit log\./)).toBeVisible()
})

test('An admin checks the integrity of the chain @REQ-AUD-5 @J10', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await page.goto('/admin/audit')
  await page.getByRole('button', { name: 'Check integrity' }).click()
  // The platform takes a queued check within seconds and the page follows it
  await expect(page.getByText('The chain is intact.')).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText(/Checked .* by (Admin|the nightly check)/)).toBeVisible()
})

test('Only an admin opens the audit log @REQ-AUD-4 @NFR-6', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/admin/audit')
  // It looks like a missing page to anyone who is not an admin (AFD §5.2)
  await expect(page.getByText('We can’t find that page')).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: 'Audit log' })).toHaveCount(0)
})

test('Staff read a station History and a client has no such tab @REQ-AUD-6 @NFR-6 @J10', async ({ watched: page, browser }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/stations')
  await page.getByRole('link', { name: /JM-KIN-001/ }).first().click()
  await page.getByRole('tab', { name: 'History' }).click()
  await expect(page).toHaveURL(/tab=history/)
  await expect(page.getByText(/Staff only\. This lists who changed what and when/)).toBeVisible()
  // The old and new values are for admins: a technician has no link to the full record
  await expect(page.getByRole('link', { name: /Open in audit log/ })).toHaveCount(0)
  await checkA11y(page, '/stations/:id?tab=history')

  const clientContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const client = await clientContext.newPage()
  await logIn(client, 'client.a1@example.org')
  await client.goto('/stations')
  await client.getByRole('link', { name: /JM-KIN-001/ }).first().click()
  await expect(client.getByRole('tab', { name: 'Overview' })).toBeVisible()
  await expect(client.getByRole('tab', { name: 'History' })).toHaveCount(0)
  await clientContext.close()
})

test('A request shows every change to staff, with who did it, and an admin can open the record @REQ-AUD-6 @J10', async ({ watched: page, browser }) => {
  const client = await (await browser.newContext({ ignoreHTTPSErrors: true })).newPage()
  await logIn(client, 'client.a1@example.org')
  const path = await submitRequest(client, unique('Rain gauge reads zero'))
  await client.context().close()

  await logIn(page, 'admin@example.org')
  await page.goto(`${path}?tab=history`)
  await expect(page.getByRole('heading', { name: 'Every change' })).toBeVisible()
  // The consumer writes the record a moment after the request is made
  await expect(async () => {
    await page.reload()
    await expect(page.getByText('created the request').first()).toBeVisible({ timeout: 4000 })
  }).toPass({ timeout: 45_000 })
  await expect(page.getByRole('link', { name: /Open in audit log/ }).first()).toBeVisible()
  await page.getByRole('link', { name: /Open in audit log/ }).first().click()
  await expect(page).toHaveURL(/\/admin\/audit\?seq=\d+/)
})
