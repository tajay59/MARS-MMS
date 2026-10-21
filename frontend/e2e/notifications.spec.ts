import type { Browser, Page } from '@playwright/test'
import { logIn, submitRequest, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Notifications and live pages, W9 slice 3 (PRD NOT-1, NOT-2, NOT-5; TRD §3.5, §13.4), on the demo
  seed with the real Kafka, platform consumer and WebSocket behind Nginx. Each test makes its own
  requests with a title no other run uses.
*/

const LIVE = { timeout: 30_000 }

async function staffPage (browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext({ ignoreHTTPSErrors: true })).newPage()
  await logIn(page, email)
  return page
}

async function connected (page: Page): Promise<void> {
  // The list page says "Live" once the socket has said ready
  await page.goto('/notifications')
  await expect(page.getByText('Live', { exact: true })).toBeVisible(LIVE)
}

test('An admin hears of a new request as it is made, and opening it reads it @NOT-1 @NOT-2', async ({ watched: client, browser }) => {
  const admin = await staffPage(browser, 'admin@example.org')
  await connected(admin)
  await admin.goto('/dashboard')

  const title = unique('Logger offline')
  await logIn(client, 'client.a1@example.org')
  await submitRequest(client, title)

  // The toast says it, the bell counts it, the list holds it
  await expect(admin.getByText(title).first()).toBeVisible(LIVE)
  await expect(admin.getByRole('link', { name: /^Notifications, \d+ unread$/ })).toBeVisible()
  await admin.goto('/notifications')
  const row = admin.getByRole('link', { name: new RegExp(title) })
  await expect(row).toBeVisible()
  await expect(row.getByText('Unread')).toBeVisible()
  await checkA11y(admin, '/notifications')

  await row.click()
  await expect(admin).toHaveURL(/\/requests\/[\da-f-]{36}$/)
  await expect(admin.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await admin.goto('/notifications')
  await expect(admin.getByRole('link', { name: new RegExp(title) }).getByText('Unread')).toHaveCount(0)
  await admin.context().close()
})

test('Mark all as read clears the count @NOT-2', async ({ watched: page, browser }) => {
  const admin = await staffPage(browser, 'admin@example.org')
  await connected(admin)
  const title = unique('Antenna damaged')
  await logIn(page, 'client.a1@example.org')
  await submitRequest(page, title)
  await expect(admin.getByRole('link', { name: new RegExp(title) })).toBeVisible(LIVE)
  await admin.getByRole('button', { name: 'Mark all as read' }).click()
  await expect(admin.getByRole('button', { name: 'Mark all as read' })).toHaveCount(0)
  await expect(admin.getByRole('link', { name: /^Notifications$/ })).toBeVisible()
  await admin.reload()
  await expect(admin.getByRole('link', { name: new RegExp(title) })).toBeVisible()
  await expect(admin.getByRole('button', { name: 'Mark all as read' })).toHaveCount(0) // still read after a reload
  await admin.context().close()
})

test('An open request follows a claim without a reload @NOT-5', async ({ watched: client, browser }) => {
  const title = unique('Wind vane stuck')
  await logIn(client, 'client.a1@example.org')
  const path = await submitRequest(client, title)

  const admin = await staffPage(browser, 'admin@example.org')
  await admin.goto(path)
  await admin.getByRole('button', { name: 'Approve' }).click()
  await expect(admin.getByText('In the queue', { exact: true })).toBeVisible()
  // The client's open page learns it was approved
  await expect(client.getByText('Approved', { exact: true }).first()).toBeVisible(LIVE)

  const tech = await staffPage(browser, 'tech1@example.org')
  await tech.goto('/queue')
  await tech.getByRole('table', { name: /waiting for someone/ }).getByRole('row', { name: new RegExp(title) }).getByRole('button', { name: 'Claim' }).click()
  await expect(tech.getByText(/You claimed/)).toBeVisible()

  // Both open pages show who has it, with no reload
  await expect(admin.getByText('On it: Tech 1.')).toBeVisible(LIVE)
  await expect(client.getByText('Assigned to Tech 1.')).toBeVisible(LIVE)
  // The client was told, the technician (who did it) was not
  await client.goto('/notifications')
  await expect(client.getByRole('link', { name: /A technician is on it/ }).first()).toBeVisible(LIVE)
  await tech.goto('/notifications')
  await expect(tech.getByRole('link', { name: /Tech 1 claimed/ })).toHaveCount(0)
  await admin.context().close()
  await tech.context().close()
})

test('A comment appears in the other person’s open thread, and an internal one never reaches the client @NOT-5 @REQ-10', async ({ watched: client, browser }) => {
  const title = unique('Modem offline')
  await logIn(client, 'client.a1@example.org')
  const path = await submitRequest(client, title)
  await client.goto(`${path}?tab=comments`)
  await expect(client.getByText('No comments yet.')).toBeVisible()

  const admin = await staffPage(browser, 'admin@example.org')
  await admin.goto(`${path}?tab=comments`)
  await admin.getByLabel('Write a comment').fill('We will look at it today.')
  await admin.getByRole('button', { name: 'Post', exact: true }).click()
  await expect(client.getByText('We will look at it today.')).toBeVisible(LIVE)
  await expect(client.getByRole('tab', { name: /^Comments/ })).toContainText('1')

  // An internal note: staff pages get it, the client's page and list get nothing
  await admin.getByRole('switch', { name: 'Internal' }).check({ force: true })
  await admin.getByLabel('Write a comment').fill('Staff only: ask for a quote.')
  await admin.getByRole('button', { name: 'Post', exact: true }).click()
  await expect(admin.getByText('Staff only: ask for a quote.')).toBeVisible()
  await admin.waitForTimeout(3000) // long enough for the event to have gone round
  await expect(client.getByText('Staff only')).toHaveCount(0)
  await expect(client.getByRole('tab', { name: /^Comments/ })).toContainText('1')
  await client.goto('/notifications')
  await expect(client.getByText('Internal comment')).toHaveCount(0)
  await admin.context().close()
})

test('On a phone the Me tab shows there is something unread @phone @NOT-1', async ({ watched: page, browser }) => {
  await logIn(page, 'admin@example.org')
  await page.goto('/dashboard')

  const client = await staffPage(browser, 'client.a1@example.org')
  const title = unique('Rain gauge')
  await submitRequest(client, title)
  await client.context().close()

  // The bar says so, the menu has the count, and the page lists it
  await expect(page.getByRole('button', { name: /^Me\s*,.*\d\+? unread$/ })).toBeVisible(LIVE)
  await page.getByRole('button', { name: /^Me/ }).click()
  await page.getByRole('menuitem', { name: /^Notifications \(\d+\+?\)$/ }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Notifications' })).toBeVisible()
  await expect(page.getByRole('link', { name: new RegExp(title) })).toBeVisible()
  await checkA11y(page, '/notifications (phone)')
})
