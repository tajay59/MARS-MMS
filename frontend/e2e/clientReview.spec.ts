import type { Browser, Page } from '@playwright/test'
import { claimedRequest, logIn, pdf, startVisit, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Journeys J8 and J9 (PRD REQ-12 to REQ-14, CRP-1 to CRP-4, RPT-8; W18 slice 5). A technician takes a
  request to Client Review; the client accepts it with a drawn signature (the request closes and the
  close-out report appears), or sends it back with a reason; and a client adds a PDF and an online
  form report. Needs the operations, report, report-worker, media, media-worker and platform
  containers, and a rebuilt frontend.
*/

// A 1 x 1 PNG: the form takes JPEG and PNG pictures, and media checks the first bytes
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')

async function deskPage (browser: Browser, email: string): Promise<Page> {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 900 }, isMobile: false, hasTouch: false })
  const page = await context.newPage()
  await logIn(page, email)
  return page
}

/** A technician plans, runs and ends a visit, signs and finalizes its report: the request is in Client Review. */
async function inClientReview (browser: Browser, title: string): Promise<string> {
  const path = await claimedRequest(browser, title)
  const tech = await deskPage(browser, 'tech1@example.org')
  await tech.goto(path)
  await tech.getByRole('button', { name: 'Schedule visit' }).click()
  await tech.getByRole('dialog', { name: 'Schedule visit' }).getByRole('button', { name: 'Schedule visit' }).click()
  await expect(tech.getByText(/VR-\d{4}-\d{4}-01 is planned\./)).toBeVisible()
  await tech.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ }).getByRole('link', { name: /VR-/ }).click()
  await expect(tech).toHaveURL(/\/visits\/[\da-f-]{36}$/)
  await startVisit(tech)
  await expect(tech.getByText('Visit started. The request is In progress.')).toBeVisible()
  await tech.getByRole('button', { name: 'End visit' }).click()
  await tech.getByRole('dialog', { name: 'End visit' }).getByRole('button', { name: 'End visit' }).click()
  const section = tech.getByRole('region', { name: 'Report' })
  await expect(section.getByText('Draft ready')).toBeVisible({ timeout: 240_000 })
  await section.getByRole('link', { name: 'Edit and sign' }).click()
  await expect(tech).toHaveURL(/\/visit-reports\/[\da-f-]{36}$/)
  await tech.getByLabel('What was done, in a few sentences').fill('Replaced the funnel and levelled the gauge.')
  await expect(tech.getByText(/Saved \d/)).toBeVisible()
  await tech.getByRole('button', { name: 'Sign', exact: true }).click()
  const dialog = tech.getByRole('dialog', { name: 'Sign the report' })
  await dialog.getByRole('button', { name: 'Use my typed name as my signature' }).click()
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Sign', exact: true }).click()
  await expect(dialog).toBeHidden()
  await tech.getByRole('button', { name: 'Finalize' }).click()
  await tech.getByRole('dialog', { name: 'Finalize this report?' }).getByRole('button', { name: 'Finalize' }).click()
  await expect(tech.getByText('Final v1').first()).toBeVisible({ timeout: 180_000 })
  await tech.context().close()
  return path
}

async function drawSignature (page: Page): Promise<void> {
  const pad = page.getByRole('img', { name: 'Your signature' })
  const box = await pad.boundingBox()
  expect(box).not.toBeNull()
  const { x, y, width, height } = box!
  await page.mouse.move(x + width * 0.15, y + height * 0.6)
  await page.mouse.down()
  await page.mouse.move(x + width * 0.35, y + height * 0.25, { steps: 8 })
  await page.mouse.move(x + width * 0.55, y + height * 0.7, { steps: 8 })
  await page.mouse.move(x + width * 0.8, y + height * 0.35, { steps: 8 })
  await page.mouse.up()
}

async function openReview (client: Page, path: string): Promise<void> {
  await client.goto(path)
  await expect(client.getByText('The work is done and ready for your review.')).toBeVisible()
  await client.getByRole('link', { name: 'Review and sign off' }).click()
  await expect(client).toHaveURL(/\/requests\/[\da-f-]{36}\/review$/)
  await expect(client.getByRole('heading', { level: 1, name: 'Review the work' })).toBeVisible()
}

test('A client reads the reports and accepts the work with a signature, and the close-out report appears @REQ-REQ-12 @REQ-REQ-13 @REQ-RPT-8 @J8', async ({ browser }) => {
  test.setTimeout(600_000)
  const path = await inClientReview(browser, unique('Accept check'))
  const client = await deskPage(browser, 'client.a1@example.org')
  await openReview(client, path)

  // What the client decides on: the final visit report, opened in the app's own sheet
  await expect(client.getByText('Final v1')).toBeVisible()
  await client.getByRole('button', { name: 'Open' }).first().click()
  const sheet = client.getByRole('dialog', { name: /VR-/ })
  await expect(sheet.getByRole('img', { name: /Page 1 of/ })).toBeVisible({ timeout: 60_000 })
  await sheet.getByRole('button', { name: 'Close' }).click()
  await checkA11y(client, '/requests/:id/review')

  // Accept needs the name, a drawing and the attestation
  await client.getByRole('button', { name: 'Accept work' }).click()
  const dialog = client.getByRole('dialog', { name: 'Accept the work' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Sign and accept' }).click()
  await expect(dialog.getByText('Draw your signature, or use your typed name.')).toBeVisible()
  await drawSignature(client)
  await dialog.getByRole('button', { name: 'Sign and accept' }).click()
  await expect(dialog.getByText('Tick the box to confirm.')).toBeVisible()
  await expect(dialog.getByText(/I confirm that the work described in the reports above has been completed/)).toBeVisible()
  await checkA11y(client, '/requests/:id/review (accept dialog)')
  await dialog.getByRole('checkbox').check()
  await dialog.getByLabel('Comment (optional)').fill('Thank you for the quick visit.')
  await dialog.getByRole('button', { name: 'Sign and accept' }).click()
  await expect(dialog).toBeHidden()
  await expect(client.getByText('Work accepted.').first()).toBeVisible()
  await expect(client.getByRole('button', { name: 'Accept work' })).toHaveCount(0)

  // The close-out report is made by the worker, and leads the Reports tab
  await client.getByRole('link', { name: 'See the reports' }).click()
  await expect(client).toHaveURL(/tab=reports/)
  await expect(client.getByText(/Closed\. Accepted by/)).toBeVisible()
  const closeout = client.getByRole('region', { name: 'Close-out report' })
  await expect(closeout.getByText('Final v1')).toBeVisible({ timeout: 180_000 })
  await expect(closeout.getByText(/CO-\d{4}-\d{4}/)).toBeVisible()
  await closeout.getByRole('button', { name: 'Open report' }).click()
  const pdfSheet = client.getByRole('dialog', { name: /CO-/ })
  await expect(pdfSheet.getByRole('img', { name: /Page 1 of/ })).toBeVisible({ timeout: 60_000 })
  await pdfSheet.getByRole('button', { name: 'Close' }).click()
  await checkA11y(client, '/requests/:id (Reports tab, closed)')

  // A second visit to the review page says why there is nothing to answer
  await client.goto(`${path}/review`)
  await expect(client.getByText('Work accepted.').first()).toBeVisible()
  await expect(client.getByRole('button', { name: 'Reject' })).toHaveCount(0)
  await client.context().close()
})

test('A client sends the work back with a reason and the technician has it again @REQ-REQ-13 @J8', async ({ browser }) => {
  test.setTimeout(600_000)
  const path = await inClientReview(browser, unique('Reject check'))
  const client = await deskPage(browser, 'client.a1@example.org')
  await openReview(client, path)

  await client.getByRole('button', { name: 'Reject' }).click()
  const dialog = client.getByRole('dialog', { name: 'Send the work back' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Send' }).click()
  await expect(dialog.getByText(/Tell them why, in at least 5 characters/)).toBeVisible()
  await checkA11y(client, '/requests/:id/review (reject dialog)')
  await dialog.getByLabel('Reason').fill('The photos of the mast are from another site.')
  await dialog.getByRole('button', { name: 'Send' }).click()
  await expect(dialog).toBeHidden()
  await expect(client.getByText('Sent back.')).toBeVisible()

  // The request is Assigned again, with the same technician, and the review page says so
  await client.goto(path)
  await expect(client.getByText('Assigned').first()).toBeVisible()
  await client.goto(`${path}/review`)
  await expect(client.getByText('You sent the work back.')).toBeVisible()
  await expect(client.getByRole('button', { name: 'Accept work' })).toHaveCount(0)
  await client.context().close()
})

test('A client adds a PDF report and an online form report, and staff read them @REQ-CRP-1 @REQ-CRP-2 @REQ-CRP-3 @REQ-CRP-4 @J9', async ({ browser }) => {
  test.setTimeout(420_000)
  const path = await claimedRequest(browser, unique('Client report check'))
  const run = Date.now().toString(36)
  const client = await deskPage(browser, 'client.a1@example.org')

  await client.goto(`${path}?tab=reports`)
  await expect(client.getByRole('heading', { name: 'Client reports' })).toBeVisible()
  await client.getByRole('link', { name: 'Add a client report' }).click()
  await expect(client).toHaveURL(/\/client-reports\/new$/)
  await checkA11y(client, '/requests/:id/client-reports/new (kind)')

  // A PDF report: the title and a PDF are needed, and the draft takes the PDF once media has checked it
  await client.getByRole('button', { name: /Upload a PDF/ }).click()
  await expect(client.getByText('Draft', { exact: true })).toBeVisible()
  await client.getByRole('button', { name: 'Submit' }).first().click()
  await expect(client.getByText('Give the report a title.')).toBeVisible()
  await client.getByLabel('Title').fill(`Rainfall totals ${run}`)
  await client.getByTestId('client-report-pdf').setInputFiles({ name: `rainfall-${run}.pdf`, mimeType: 'application/pdf', buffer: pdf('rainfall') })
  await expect(client.getByText(/Ready/)).toBeVisible({ timeout: 90_000 })
  await expect(client.getByText(/Saved at \d/)).toBeVisible()
  await checkA11y(client, '/requests/:id/client-reports/new (PDF)')
  await client.getByRole('button', { name: 'Submit' }).first().click()
  const confirm = client.getByRole('dialog', { name: 'Submit this report?' })
  await expect(confirm).toBeVisible()
  await confirm.getByRole('button', { name: 'Submit' }).click()
  await expect(client).toHaveURL(/tab=reports/)
  const list = client.getByRole('region', { name: 'Client reports' })
  await expect(list.getByText(`Rainfall totals ${run}`)).toBeVisible()
  await expect(list.getByRole('button', { name: 'Open' }).first()).toBeVisible()

  // An online form with a picture: saved as a draft, continued, then sent
  await client.getByRole('link', { name: 'Add a client report' }).click()
  await client.getByRole('button', { name: /Fill in the online form/ }).click()
  await client.getByLabel('Title').fill(`Gauge check ${run}`)
  await client.getByLabel('Summary').fill('Readings were steady apart from one gap.')
  await client.getByTestId('client-report-pictures').setInputFiles({ name: `gauge-${run}.png`, mimeType: 'image/png', buffer: PNG })
  await expect(client.getByText(`gauge-${run}.png`)).toBeVisible()
  await expect(client.getByText(/Saved at \d/)).toBeVisible({ timeout: 90_000 })
  await client.getByRole('button', { name: 'Save draft' }).click()
  await client.goto(`${path}?tab=reports`)
  const draft = client.getByRole('region', { name: 'Client reports' })
  await expect(draft.getByText(`Gauge check ${run}`)).toBeVisible()
  await draft.getByRole('link', { name: 'Continue draft' }).click()
  await expect(client.getByLabel('Title')).toHaveValue(`Gauge check ${run}`)
  await expect(client.getByLabel('Summary')).toHaveValue('Readings were steady apart from one gap.')
  await checkA11y(client, '/requests/:id/client-reports/:id (form draft)')

  // Another person sees no draft (it is private to its author)
  const tech = await deskPage(browser, 'tech1@example.org')
  await tech.goto(`${path}?tab=reports`)
  await expect(tech.getByRole('region', { name: 'Client reports' }).getByText(`Rainfall totals ${run}`)).toBeVisible()
  await expect(tech.getByText(`Gauge check ${run}`)).toHaveCount(0)
  await expect(tech.getByRole('link', { name: 'Add a client report' })).toHaveCount(0)

  await client.getByRole('button', { name: 'Submit' }).first().click()
  await client.getByRole('dialog', { name: 'Submit this report?' }).getByRole('button', { name: 'Submit' }).click()
  await expect(client).toHaveURL(/tab=reports/)
  const sent = client.getByRole('region', { name: 'Client reports' })
  await expect(sent.getByText(`Gauge check ${run}`)).toBeVisible()
  await expect(sent.getByRole('link', { name: 'Continue draft' })).toHaveCount(0) // sent: nothing changes it (CRP-4)

  // The PDF is made a moment after it is sent; then it opens
  await expect(sent.getByRole('button', { name: 'Open' }).nth(1)).toBeVisible({ timeout: 180_000 })
  await sent.getByRole('button', { name: 'Open' }).first().click()
  const sheet = client.getByRole('dialog', { name: new RegExp(`Gauge check ${run}`) })
  await expect(sheet.getByRole('img', { name: /Page 1 of/ })).toBeVisible({ timeout: 60_000 })
  await sheet.getByRole('button', { name: 'Close' }).click()

  // Staff read the sent form too
  await tech.reload()
  await expect(tech.getByRole('region', { name: 'Client reports' }).getByText(`Gauge check ${run}`)).toBeVisible()
  await tech.context().close()
  await client.context().close()
})
