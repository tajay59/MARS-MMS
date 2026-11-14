import type { Browser, Page } from '@playwright/test'
import { claimedRequest, logIn, staffPage, startVisit, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Journey J7 to its end (PRD RPT-2, RPT-4 to RPT-6; W17). A technician ends a visit, edits the
  report, signs it with a drawn signature and finalizes it; the PDF is made and the request moves
  on; the client reads and downloads the final report; an admin reopens it and the client sees no
  report until the corrected one is final. Needs the report, report-worker and operations
  containers, and a rebuilt frontend.
*/

async function deskPage (browser: Browser): Promise<Page> {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 900 }, isMobile: false, hasTouch: false })
  return context.newPage()
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

test('A technician edits, signs and finalizes the report, and the client reads it @REQ-RPT-2 @REQ-RPT-4 @REQ-RPT-5 @REQ-RPT-6 @J7', async ({ browser }) => {
  test.setTimeout(420_000)
  const page = await deskPage(browser)
  const path = await claimedRequest(browser, unique('Sign check'))

  await logIn(page, 'tech1@example.org')
  await page.goto(path)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  await page.getByRole('dialog', { name: 'Schedule visit' }).getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/VR-\d{4}-\d{4}-01 is planned\./)).toBeVisible()
  await page.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ }).getByRole('link', { name: /VR-/ }).click()
  await expect(page).toHaveURL(/\/visits\/[\da-f-]{36}$/)
  const visitPath = new URL(page.url()).pathname

  await startVisit(page)
  await expect(page.getByText('Visit started. The request is In progress.')).toBeVisible()
  await page.getByRole('button', { name: 'End visit' }).click()
  await page.getByRole('dialog', { name: 'End visit' }).getByRole('button', { name: 'End visit' }).click()

  // The draft, then the way into the report page
  const section = page.getByRole('region', { name: 'Report' })
  await expect(section.getByText('Draft ready')).toBeVisible({ timeout: 240_000 })
  await section.getByRole('link', { name: 'Edit and sign' }).click()
  await expect(page).toHaveURL(/\/visit-reports\/[\da-f-]{36}$/)
  const reportPath = new URL(page.url()).pathname
  await expect(page.getByRole('heading', { level: 1, name: 'Visit report' })).toBeVisible()

  // Edit: the text saves by itself
  await page.getByLabel('What was done, in a few sentences').fill('Replaced the funnel and levelled the gauge.')
  await expect(page.getByText(/Saved \d/)).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('What was done, in a few sentences')).toHaveValue('Replaced the funnel and levelled the gauge.')
  await checkA11y(page, '/visit-reports/:id (draft)')

  // Finalize waits for the lead's signature
  await expect(page.getByRole('button', { name: 'Finalize' })).toBeDisabled()

  // Sign with a drawn signature; the name, a drawing and the attestation are all needed
  await page.getByRole('button', { name: 'Sign', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Sign the report' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Sign', exact: true }).click()
  await expect(dialog.getByText('Draw your signature, or use your typed name.')).toBeVisible()
  await drawSignature(page)
  await dialog.getByRole('button', { name: 'Sign', exact: true }).click()
  await expect(dialog.getByText('Tick the box to confirm.')).toBeVisible()
  await checkA11y(page, '/visit-reports/:id (sign dialog)')
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Sign', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('img', { name: /Drawn signature of/ })).toBeVisible()

  // An edit after signing clears the signature, and signing again works
  await page.getByLabel('What was done, in a few sentences').fill('Replaced the funnel, levelled the gauge and checked the mast.')
  await expect(page.getByText(/Cleared at/)).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('button', { name: 'Finalize' })).toBeDisabled()
  await page.getByRole('button', { name: 'Sign again' }).click()
  // Without a drawing the typed name can stand as the signature (keyboard and screen reader users)
  await dialog.getByRole('button', { name: 'Use my typed name as my signature' }).click()
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Sign', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('img', { name: /Drawn signature of/ })).toBeVisible()

  // Finalize: the PDF is made by the worker and the report becomes final
  await page.getByRole('button', { name: 'Finalize' }).click()
  const confirm = page.getByRole('dialog', { name: 'Finalize this report?' })
  await checkA11y(page, '/visit-reports/:id (finalize dialog)')
  await confirm.getByRole('button', { name: 'Finalize' }).click()
  await expect(page.getByText('Final v1').first()).toBeVisible({ timeout: 180_000 })
  await expect(page.getByRole('button', { name: 'Download PDF' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reopen for correction' })).toHaveCount(0) // the technician is not an admin
  await expect(page.getByLabel('What was done, in a few sentences')).toHaveJSProperty('readOnly', true)
  await checkA11y(page, '/visit-reports/:id (final)')

  // The client reads and downloads the final report on the visit
  const client = await staffPage(browser, 'client.a1@example.org')
  await client.goto(visitPath)
  const clientReport = client.getByRole('region', { name: 'Report' })
  await expect(clientReport.getByText('Final v1')).toBeVisible({ timeout: 30_000 })
  await clientReport.getByRole('button', { name: 'Open report' }).click()
  const sheet = client.getByRole('dialog', { name: /Report VR-/ })
  await expect(sheet.getByRole('img', { name: /Page 1 of/ })).toBeVisible({ timeout: 60_000 })
  await checkA11y(client, '/visits/:id (client, final report)')
  await sheet.getByRole('button', { name: 'Close' }).click()
  await client.getByRole('button', { name: 'Download PDF' }).click()

  // An admin reopens it for correction; the client is told a corrected report is on its way
  const admin = await staffPage(browser, 'admin@example.org')
  await admin.goto(reportPath)
  await expect(admin.getByText('Final v1').first()).toBeVisible()
  await admin.getByRole('button', { name: 'Reopen for correction' }).click()
  const reopen = admin.getByRole('dialog', { name: 'Reopen for correction' })
  await reopen.getByRole('button', { name: 'Reopen' }).click()
  await expect(reopen.getByText('Give a reason of 5 to 500 characters.')).toBeVisible()
  await reopen.getByLabel('Reason').fill('The recommendation was missing its priority.')
  await reopen.getByRole('button', { name: 'Reopen' }).click()
  await expect(admin).not.toHaveURL(reportPath)
  await expect(admin.getByText('Draft v2').first()).toBeVisible()
  await expect(admin.getByText('This is a correction of an earlier version.')).toBeVisible()
  await expect(admin.getByRole('link', { name: 'Superseded v1' })).toBeVisible()

  await client.reload()
  await expect(client.getByRole('heading', { level: 1, name: /VR-/ })).toBeVisible()
  const waiting = client.getByRole('region', { name: 'Report' })
  await expect(waiting.getByText('A corrected report is on its way.')).toBeVisible()
  await expect(waiting.getByRole('button', { name: 'Open report' })).toHaveCount(0)
  await checkA11y(client, '/visits/:id (client, correction in progress)')

  await client.context().close()
  await admin.context().close()
  await page.context().close()
})
