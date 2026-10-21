import type { Browser, Page } from '@playwright/test'
import { logIn, pdf, submitRequest, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Comments and PDF attachments, W9 slice 2 (PRD REQ-3, REQ-9, REQ-10; AFD J3 step 5), on the demo
  seed with the real media service and files host. The exit check at the API level is in
  operations' tests; here a person sees it: a client never finds an internal comment or its file.
*/

async function staffPage (browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext({ ignoreHTTPSErrors: true })).newPage()
  await logIn(page, email)
  return page
}

async function openComments (page: Page, path: string): Promise<void> {
  await page.goto(`${path}?tab=comments`)
  await expect(page.getByRole('tab', { name: /^Comments/ })).toHaveAttribute('aria-selected', 'true')
}

/** Types a comment, optionally attaches a PDF and waits until it is checked, then posts. */
async function post (page: Page, text: string, options: { file?: string, internal?: boolean } = {}): Promise<void> {
  if (options.internal) {
    await page.getByRole('switch', { name: 'Internal' }).check({ force: true })
  }
  await page.getByLabel('Write a comment').fill(text)
  if (options.file) {
    await page.getByTestId('attachment-file').setInputFiles({ name: options.file, mimeType: 'application/pdf', buffer: pdf(options.file) })
    await expect(page.getByRole('list', { name: 'Files to attach' }).getByText(/Ready/)).toBeVisible({ timeout: 60_000 })
  }
  await page.getByRole('button', { name: 'Post', exact: true }).click()
  await expect(page.getByLabel('Write a comment')).toHaveValue('')
}

test('A client and a technician talk, with files, and an internal note stays internal @REQ-9 @REQ-10 @REQ-3 @J3', async ({ watched: client, browser }) => {
  const title = unique('Logger offline')
  await logIn(client, 'client.a1@example.org')
  const path = await submitRequest(client, title)
  await openComments(client, path)
  await expect(client.getByText('No comments yet.')).toBeVisible()
  await expect(client.getByRole('switch', { name: 'Internal' })).toHaveCount(0) // clients have no such switch

  const run = Date.now().toString(36)
  await post(client, 'The logger stopped sending on Tuesday.', { file: `storm-${run}.pdf` })
  const thread = client.getByRole('list', { name: /Comments, oldest first/ })
  await expect(thread.getByText('The logger stopped sending on Tuesday.')).toBeVisible()
  await expect(thread.getByRole('button', { name: new RegExp(`storm-${run}.pdf`) })).toBeVisible()
  await expect(client.getByRole('tab', { name: /^Comments/ })).toContainText('1')

  // Staff reply in the open, then leave a note with a file that is for staff only
  const tech = await staffPage(browser, 'tech1@example.org')
  await openComments(tech, path)
  await expect(tech.getByText('The logger stopped sending on Tuesday.')).toBeVisible()
  await post(tech, 'I can go on Thursday.')
  await post(tech, 'Bring the spare modem. The client pays for the antenna.', { file: `quote-${run}.pdf`, internal: true })
  const internal = tech.getByRole('listitem').filter({ hasText: 'Bring the spare modem' })
  await expect(internal.getByText('Internal, not visible to the client')).toBeVisible()
  await expect(internal.getByRole('button', { name: new RegExp(`quote-${run}.pdf`) })).toBeVisible()
  await checkA11y(tech, '/requests/:id (comments, staff, internal)')

  // The client sees the reply and nothing of the note: not its words, its file or its count
  await openComments(client, path)
  await expect(client.getByText('I can go on Thursday.')).toBeVisible()
  await expect(client.getByText('Bring the spare modem')).toHaveCount(0)
  await expect(client.getByText(`quote-${run}.pdf`)).toHaveCount(0)
  await expect(client.getByText(/Internal/)).toHaveCount(0)
  await expect(client.getByRole('tab', { name: /^Comments/ })).toContainText('2')
  await checkA11y(client, '/requests/:id (comments, client)')
  await tech.context().close()
})

test('The author can change a comment for a few minutes @REQ-9', async ({ watched: page }) => {
  const title = unique('Wind vane stuck')
  await logIn(page, 'client.a1@example.org')
  const path = await submitRequest(page, title)
  await openComments(page, path)
  await post(page, 'First thought.')
  const item = page.getByRole('listitem').filter({ hasText: 'First thought.' })
  await expect(item.getByRole('button', { name: /^Edit · \d+ minutes? left$/ })).toBeVisible()
  await item.getByRole('button', { name: /^Edit/ }).click()
  await page.getByLabel('Your comment').fill('Second thought.')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  const edited = page.getByRole('listitem').filter({ hasText: 'Second thought.' })
  await expect(edited.getByText('edited')).toBeVisible()
  await expect(page.getByText('First thought.')).toHaveCount(0)
})

test('A request is submitted with a PDF and staff open it @REQ-3', async ({ watched: page, browser }) => {
  const title = unique('Site notes')
  const run = Date.now().toString(36)
  await logIn(page, 'client.a1@example.org')
  await page.goto('/requests/new')
  await page.getByLabel('Which stations is this about?').fill('JM-KIN-001')
  await page.getByRole('option', { name: /JM-KIN-001/ }).click()
  await page.getByLabel('Title', { exact: true }).fill(title)
  await page.getByLabel('Description', { exact: true }).fill('Notes are attached.')
  await page.getByTestId('attachment-file').setInputFiles([
    { name: `notes-${run}.pdf`, mimeType: 'application/pdf', buffer: pdf('notes') },
    { name: 'wiring.docx', mimeType: 'application/octet-stream', buffer: Buffer.from('x') },
  ])
  // A file that cannot be attached says so and stops the submit until it is removed
  await expect(page.getByText('Only PDF files can be attached.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Submit request' })).toBeDisabled()
  await checkA11y(page, '/requests/new (attachments)')
  await page.getByRole('button', { name: 'Remove wiring.docx' }).click()
  await expect(page.getByRole('list', { name: 'Files to attach' }).getByText(/Ready/)).toBeVisible({ timeout: 60_000 })
  await page.getByRole('button', { name: 'Submit request' }).click()
  await expect(page).toHaveURL(/\/requests\/[\da-f-]{36}$/)
  const path = new URL(page.url()).pathname
  await expect(page.getByRole('button', { name: new RegExp(`notes-${run}.pdf`) })).toBeVisible()

  const tech = await staffPage(browser, 'tech1@example.org')
  await tech.goto(path)
  await expect(tech.getByRole('button', { name: new RegExp(`notes-${run}.pdf`) })).toBeVisible()
  await tech.context().close()
})

test('A viewer reads the thread and cannot write @REQ-9 @NFR-6', async ({ watched: page, browser }) => {
  const title = unique('Modem offline')
  await logIn(page, 'client.a1@example.org')
  const path = await submitRequest(page, title)
  await openComments(page, path)
  await post(page, 'Hello from the client.')

  const viewer = await staffPage(browser, 'viewer@example.org')
  await openComments(viewer, path)
  await expect(viewer.getByText('Hello from the client.')).toBeVisible()
  await expect(viewer.getByLabel('Write a comment')).toHaveCount(0)
  await expect(viewer.getByRole('button', { name: 'Post', exact: true })).toHaveCount(0)
  await viewer.context().close()
})

test('On a phone the thread and composer fit @phone @REQ-9', async ({ watched: page }) => {
  const title = unique('Rain gauge')
  await logIn(page, 'client.a1@example.org')
  const path = await submitRequest(page, title)
  await openComments(page, path)
  await post(page, 'Posting from a phone.')
  await expect(page.getByText('Posting from a phone.')).toBeVisible()
  await checkA11y(page, '/requests/:id (comments, phone)')
})
