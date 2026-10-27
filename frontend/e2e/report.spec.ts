import type { Browser, Page } from '@playwright/test'
import { claimedRequest, logIn, staffPage, startVisit, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  The visit report's first draft (PRD RPT-1, RPT-3; W16-14 to W16-16). A technician ends a visit;
  the report service makes a draft record from `visit.ended` and draws its PDF by itself; the
  visit page shows the Report section, Preview opens the PDF in the sheet (never a new tab), and a
  client sees no Report section at all. Needs the report and report-worker containers.
*/

/** A page at desktop size, even in the phone project: the planning steps use the tables of the wide layout. */
async function deskPage (browser: Browser): Promise<Page> {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 800 }, isMobile: false, hasTouch: false })
  return context.newPage()
}

test('A technician ends a visit and previews the draft report, and a client sees none @REQ-RPT-1 @REQ-RPT-3 @J7', async ({ browser }) => {
  test.setTimeout(300_000)
  const page = await deskPage(browser)
  const path = await claimedRequest(browser, unique('Report check'))

  await logIn(page, 'tech1@example.org')
  await page.goto(path)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  await page.getByRole('dialog', { name: 'Schedule visit' }).getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/VR-\d{4}-\d{4}-01 is planned\./)).toBeVisible()
  await page.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ }).getByRole('link', { name: /VR-/ }).click()
  await expect(page).toHaveURL(/\/visits\/[\da-f-]{36}$/)
  const visitPath = new URL(page.url()).pathname

  // Before the visit has ended there is no report to show
  await startVisit(page)
  await expect(page.getByText('Visit started. The request is In progress.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Report', exact: true })).toHaveCount(0)

  await page.getByRole('button', { name: 'End visit' }).click()
  await page.getByRole('dialog', { name: 'End visit' }).getByRole('button', { name: 'End visit' }).click()
  await expect(page.getByText(/ended/i).first()).toBeVisible()

  // The draft is made by itself: first on its way, then ready with its page count
  const report = page.getByRole('region', { name: 'Report' })
  await expect(report).toBeVisible()
  await expect(report.getByText(/VR-\d{4}-\d{4}-01/)).toBeVisible({ timeout: 60_000 })
  await expect(report.getByText('Draft ready')).toBeVisible({ timeout: 180_000 })
  await expect(report.getByText(/\d+ pages?\./)).toBeVisible()
  await checkA11y(page, '/visits/:id (ended, draft report ready)')

  // Preview opens the PDF in the sheet, page by page, and the sheet closes again
  await report.getByRole('button', { name: 'Preview' }).click()
  const sheet = page.getByRole('dialog', { name: /Draft VR-/ })
  await expect(sheet.getByRole('img', { name: /Page 1 of/ })).toBeVisible({ timeout: 60_000 })
  await expect(sheet.getByRole('link', { name: 'Download' })).toBeVisible()
  await checkA11y(page, '/visits/:id (draft report preview)')
  await sheet.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()

  // The client has no report section, whatever the visit shows them
  const client = await staffPage(browser, 'client.a1@example.org')
  await client.goto(visitPath)
  await expect(client.getByRole('heading', { level: 1, name: /VR-/ })).toBeVisible()
  await expect(client.getByRole('heading', { name: 'Report', exact: true })).toHaveCount(0)
  await client.context().close()
  await page.context().close()
})
