import type { Browser, Page } from '@playwright/test'
import { logIn, submitRequest, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  The queue, assigning, claiming and releasing, W9 (PRD REQ-7; AFD J4 steps 3 to 4, J5 steps 1 and 2),
  on the demo seed. Each test makes its own request with a title no other run uses.
*/

/** A client submits a request and an admin approves it: it is in the queue. Returns its path. */
async function approvedRequest (browser: Browser, title: string): Promise<string> {
  const client = await (await browser.newContext({ ignoreHTTPSErrors: true })).newPage()
  await logIn(client, 'client.a1@example.org')
  const path = await submitRequest(client, title)
  await client.context().close()

  const admin = await (await browser.newContext({ ignoreHTTPSErrors: true })).newPage()
  await logIn(admin, 'admin@example.org')
  await admin.goto(path)
  await admin.getByRole('button', { name: 'Approve' }).click()
  await expect(admin.getByText('Request approved. It is now in the queue.')).toBeVisible()
  await admin.context().close()
  return path
}

async function staffPage (browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext({ ignoreHTTPSErrors: true })).newPage()
  await logIn(page, email)
  return page
}

test('An admin assigns two technicians and the client sees their names @REQ-7 @J4', async ({ watched: client, browser }) => {
  const title = unique('Logger offline')
  await logIn(client, 'client.a1@example.org')
  const path = await submitRequest(client, title)

  const admin = await staffPage(browser, 'admin@example.org')
  await admin.goto(path)
  await admin.getByRole('button', { name: 'Approve' }).click()
  await expect(admin.getByText('In the queue', { exact: true })).toBeVisible()

  await admin.getByRole('button', { name: 'Assign staff' }).click()
  const dialog = admin.getByRole('dialog', { name: 'Assign staff' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('checkbox', { name: /Tech 1/ })).toBeVisible()
  await expect(dialog.getByText(/open requests?/).first()).toBeVisible()
  await checkA11y(admin, '/requests/:id (assign dialog)')
  const assign = dialog.getByRole('button', { name: 'Assign', exact: true })
  await expect(assign).toBeDisabled() // nobody chosen yet
  await dialog.getByRole('checkbox', { name: /Tech 1/ }).check()
  await dialog.getByRole('checkbox', { name: /Tech 2/ }).check()
  await dialog.getByRole('button', { name: 'Assign 2 people' }).click()
  await expect(admin.getByText(/is assigned to Tech 1 and Tech 2\./)).toBeVisible()
  await expect(admin.getByText('On it: Tech 1 and Tech 2.')).toBeVisible()
  await expect(admin.getByRole('button', { name: 'Change staff' })).toBeVisible()
  await expect(admin.getByRole('button', { name: 'Unassign' })).toBeVisible()
  await admin.getByRole('tab', { name: 'History' }).click()
  await expect(admin.getByRole('table', { name: /Status history/ }).getByText('Assigned to Tech 1, Tech 2')).toBeVisible()
  await admin.context().close()

  // The client sees who is on it, and has no staffing buttons
  await client.goto(path)
  await expect(client.getByText('A technician is on it')).toBeVisible()
  await expect(client.getByText('Assigned to Tech 1 and Tech 2.')).toBeVisible()
  for (const name of ['Claim', 'Assign staff', 'Change staff', 'Unassign', 'Release to queue']) {
    await expect(client.getByRole('button', { name })).toHaveCount(0)
  }
})

test('A technician claims from the queue, lets go, and another takes it @REQ-7 @J5', async ({ watched: page, browser }) => {
  const title = unique('Wind vane stuck')
  const path = await approvedRequest(browser, title)

  await logIn(page, 'tech1@example.org')
  await page.goto('/queue')
  await expect(page.getByRole('heading', { level: 1, name: 'Queue' })).toBeVisible()
  const table = page.getByRole('table', { name: /waiting for someone/ })
  const row = table.getByRole('row', { name: new RegExp(title) })
  await expect(row).toBeVisible()
  await expect(row.getByRole('button', { name: 'Assign' })).toHaveCount(0) // admins assign; a technician claims
  await checkA11y(page, '/queue')

  await row.getByRole('button', { name: 'Claim' }).click()
  await expect(page.getByText(/You claimed MR-\d{4}-\d{4}\. Admins have been told\./)).toBeVisible()
  await expect(row).toHaveCount(0)

  // On the request page: assigned to them, with a way back
  await page.goto(path)
  await expect(page.getByText('On it: Tech 1.')).toBeVisible()
  await page.getByRole('button', { name: 'Release to queue' }).click()
  await expect(page.getByText(/is back in the queue\./)).toBeVisible()
  await expect(page.getByText('In the queue', { exact: true })).toBeVisible()
  await page.goto('/queue')
  await expect(table.getByRole('row', { name: new RegExp(title) })).toBeVisible()

  // Another technician takes it, and the first has nothing to release
  const other = await staffPage(browser, 'tech2@example.org')
  await other.goto('/queue')
  await other.getByRole('table', { name: /waiting for someone/ }).getByRole('row', { name: new RegExp(title) }).getByRole('button', { name: 'Claim' }).click()
  await expect(other.getByText(/You claimed/)).toBeVisible()
  await other.context().close()
  await page.goto(path)
  await expect(page.getByText('On it: Tech 2.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Release to queue' })).toHaveCount(0)
})

test('A lost race says who got there first @REQ-7', async ({ watched: page, browser }) => {
  const title = unique('Solar panel')
  await approvedRequest(browser, title)

  await logIn(page, 'tech1@example.org')
  await page.goto('/queue')
  const row = page.getByRole('table', { name: /waiting for someone/ }).getByRole('row', { name: new RegExp(title) })
  await expect(row).toBeVisible()

  // Tech 2 claims it while Tech 1's page still shows it
  const other = await staffPage(browser, 'tech2@example.org')
  await other.goto('/queue')
  await other.getByRole('table', { name: /waiting for someone/ }).getByRole('row', { name: new RegExp(title) }).getByRole('button', { name: 'Claim' }).click()
  await expect(other.getByText(/You claimed/)).toBeVisible()
  await other.context().close()

  await row.getByRole('button', { name: 'Claim' }).click()
  await expect(page.getByText('Tech 2 claimed it first.')).toBeVisible()
  await expect(row).toHaveCount(0) // the queue reloaded
})

test('Clients and viewers have no queue @REQ-7 @NFR-6', async ({ watched: page, browser }) => {
  await logIn(page, 'client.a1@example.org')
  await page.goto('/queue')
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()

  const viewer = await staffPage(browser, 'viewer@example.org')
  await viewer.goto('/queue')
  await expect(viewer.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  await viewer.context().close()
})

test('On a phone the queue is cards and claiming asks first @phone @REQ-7', async ({ watched: page, browser }) => {
  const title = unique('Antenna damaged')
  await approvedRequest(browser, title)

  await logIn(page, 'tech1@example.org')
  await page.goto('/queue')
  const card = page.getByRole('list', { name: /waiting for someone/ }).getByRole('listitem').filter({ hasText: title })
  await expect(card).toBeVisible()
  await expect(page.getByRole('table')).toHaveCount(0)
  await checkA11y(page, '/queue (phone)')

  await card.getByRole('button', { name: 'Claim' }).click()
  const sheet = page.getByRole('dialog', { name: 'Claim this request?' })
  await expect(sheet).toBeVisible()
  await sheet.getByRole('button', { name: 'Not now' }).click()
  await expect(card).toBeVisible() // nothing was claimed

  await card.getByRole('button', { name: 'Claim' }).click()
  await page.getByRole('dialog', { name: 'Claim this request?' }).getByRole('button', { name: 'Claim request' }).click()
  await expect(page.getByText(/You claimed MR-/)).toBeVisible()
  await expect(card).toHaveCount(0)
})
