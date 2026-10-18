import type { Page } from '@playwright/test'
import { checkA11y, expect, seedPassword, submitPaced, test } from './support'

/*
  Documents, configuration versions, the sensor catalogue and the calibration due list (PRD DOC-1
  to DOC-4, CFG-1 to CFG-3, CAL-4), on the operations demo seed. Files go through the real media
  service and the SeaweedFS files host: the journey shows a technician uploading and a client
  downloading only what was shared.
*/

async function logIn (page: Page, email: string): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)
}

/** A small, valid PDF: media checks the first bytes against the name. */
function pdf (text: string): Buffer {
  return Buffer.from(`%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n% ${text}\ntrailer<</Root 1 0 R>>\n%%EOF\n`)
}

async function openStation (page: Page, tab: string): Promise<void> {
  await page.goto('/stations')
  await page.getByRole('table', { name: /Stations/ }).getByRole('link', { name: 'JM-KIN-001' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Kingston Harbour' })).toBeVisible()
  await page.getByRole('tab', { name: tab }).click()
}

test('A technician uploads documents and a client downloads only the shared one @DOC-2 @DOC-3 @DOC-4', async ({ watched: page, browser }) => {
  const run = Date.now().toString(36)
  const shared = `Site drawing ${run}`
  const hidden = `Wiring ${run}`

  await logIn(page, 'tech1@example.org')
  await openStation(page, 'Documents')
  await expect(page.getByRole('heading', { name: 'This station’s documents' })).toBeVisible()
  await checkA11y(page, '/stations/:id (documents)')

  // A document starts staff-only; the switch shares it with the owner organization (DOC-4)
  await page.getByRole('button', { name: 'Upload document' }).click()
  const dialog = page.getByRole('dialog', { name: 'Upload a document' })
  await expect(dialog.getByRole('button', { name: 'Upload', exact: true })).toBeDisabled()
  await dialog.getByTestId('document-file').setInputFiles({ name: `site-${run}.pdf`, mimeType: 'application/pdf', buffer: pdf('shared') })
  await dialog.getByLabel('Title').fill(shared)
  await dialog.getByLabel('Version label').fill('Rev C')
  await expect(dialog.getByRole('switch', { name: /^Show to / })).not.toBeChecked()
  await dialog.getByRole('switch', { name: /^Show to / }).click({ force: true })
  await checkA11y(page, 'upload dialog')
  await dialog.getByRole('button', { name: 'Upload', exact: true }).click()
  await expect(dialog).toBeHidden()

  const table = page.getByRole('table', { name: /Documents for Kingston Harbour/ })
  const sharedRow = table.getByRole('row', { name: new RegExp(shared) })
  await expect(sharedRow).toBeVisible()
  await expect(sharedRow.getByText('Rev C')).toBeVisible()
  await expect(sharedRow.getByText('Shown to Organization A')).toBeVisible()
  // Media's checks finish in a few seconds: then the file can be downloaded
  await expect(sharedRow.getByRole('button', { name: `Download ${shared}` })).toBeVisible({ timeout: 60_000 })

  // A second one, left staff-only
  await page.getByRole('button', { name: 'Upload document' }).click()
  await dialog.getByTestId('document-file').setInputFiles({ name: `wiring-${run}.pdf`, mimeType: 'application/pdf', buffer: pdf('hidden') })
  await dialog.getByLabel('Title').fill(hidden)
  await dialog.getByRole('button', { name: 'Upload', exact: true }).click()
  await expect(dialog).toBeHidden()
  const hiddenRow = table.getByRole('row', { name: new RegExp(hidden) })
  await expect(hiddenRow.getByText('Staff only')).toBeVisible()
  await expect(hiddenRow.getByRole('button', { name: `Download ${hidden}` })).toBeVisible({ timeout: 60_000 })

  // A client of the owner organization sees the shared document, and not the other
  const clientContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const client = await clientContext.newPage()
  await logIn(client, 'client.a1@example.org')
  await openStation(client, 'Documents')
  const clientTable = client.getByRole('table', { name: /Documents for Kingston Harbour/ })
  await expect(clientTable.getByRole('row', { name: new RegExp(shared) })).toBeVisible()
  await expect(clientTable.getByRole('row', { name: new RegExp(hidden) })).toHaveCount(0)
  await expect(clientTable.getByRole('columnheader', { name: 'Who sees it' })).toHaveCount(0)
  await expect(client.getByRole('button', { name: 'Upload document' })).toHaveCount(0)
  await expect(client.getByRole('tab', { name: 'Configurations' })).toHaveCount(0)
  await checkA11y(client, '/stations/:id (documents, client)')

  // The tab is opened in the click and pointed at the ten-minute link once it arrives. Headless
  // Chromium has no PDF viewer, so the file may end as a download: the request is what is checked.
  const [request] = await Promise.all([
    clientContext.waitForEvent('request', r => r.url().startsWith('https://files.')),
    client.waitForEvent('popup'),
    clientTable.getByRole('button', { name: 'Download' }).first().click(),
  ])
  expect(new URL(request.url()).searchParams.has('X-Amz-Signature')).toBe(true)
  await clientContext.close()
})

test('A technician saves configuration versions and compares them @CFG-1 @CFG-2 @CFG-3', async ({ watched: page }) => {
  const run = Date.now().toString(36)
  await logIn(page, 'tech1@example.org')
  await openStation(page, 'Configurations')
  await expect(page.getByRole('heading', { name: 'Configuration versions' })).toBeVisible()

  async function save (files: { name: string, text: string }[], notes: string): Promise<void> {
    await page.getByRole('button', { name: 'New version' }).click()
    const dialog = page.getByRole('dialog', { name: 'New configuration version' })
    await dialog.getByTestId('config-files').setInputFiles(files.map(f => ({ name: f.name, mimeType: 'text/plain', buffer: Buffer.from(f.text) })))
    for (const f of files) {
      await expect(dialog.getByText(f.name, { exact: true })).toBeVisible()
    }
    await expect(dialog.getByText(/ · ready$/)).toHaveCount(files.length, { timeout: 60_000 })
    await dialog.getByLabel('What changed').fill(notes)
    await expect(dialog.getByRole('button', { name: /^Save version/ })).toBeEnabled()
    await dialog.getByRole('button', { name: /^Save version/ }).click()
    await expect(dialog).toBeHidden()
  }

  // The same names in every run: only the contents tell versions apart
  await save([{ name: 'logger.cr1x', text: `program ${run} a` }, { name: 'network.json', text: '{"apn":"one"}' }], `First ${run}`)
  await expect(page.getByRole('heading', { level: 3, name: /^Version \d+$/ })).toBeVisible()
  await save([{ name: 'logger.cr1x', text: `program ${run} b` }, { name: 'alerts.csv', text: 'a,b\n1,2\n' }], `Second ${run}`)

  const heading = page.getByRole('heading', { level: 3, name: /^Version \d+$/ })
  await expect(page.getByText(`Second ${run}`).first()).toBeVisible()
  await expect(heading).toBeVisible()

  // Against the version before: one changed, one added, one dropped
  const table = page.getByRole('table', { name: /Files in version \d+ compared with version \d+/ })
  await expect(table.getByRole('row', { name: /logger\.cr1x/ }).getByText('Changed')).toBeVisible()
  await expect(table.getByRole('row', { name: /alerts\.csv/ }).getByText('Added')).toBeVisible()
  await expect(table.getByRole('row', { name: /network\.json/ }).getByText('Removed')).toBeVisible()
  await checkA11y(page, '/stations/:id (configurations)')
})

test('Staff browse the sensor catalogue and the calibration due list @CAL-4 @DOC-1', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/sensors')
  await expect(page.getByRole('heading', { level: 1, name: 'Sensors' })).toBeVisible()
  const models = page.getByRole('list', { name: 'Sensor models' })
  await expect(models.getByRole('link').first()).toBeVisible()
  await checkA11y(page, '/sensors')

  await models.getByRole('link').first().click()
  await expect(page.getByRole('heading', { name: 'Datasheets and manuals' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /^Units of this model/ })).toBeVisible()
  await checkA11y(page, '/sensors/:id')

  await page.goto('/calibration')
  await expect(page.getByRole('heading', { level: 1, name: 'Calibration due' })).toBeVisible()
  await expect(page.getByRole('table', { name: /overdue or due for calibration/ })
    .or(page.getByText(/Nothing is overdue or due/))).toBeVisible()
  await checkA11y(page, '/calibration')
})

test('A client cannot open the staff pages @DOC-1', async ({ watched: page }) => {
  await logIn(page, 'client.a1@example.org')
  // A page the role can't use looks like a missing one (AFD §5.2)
  for (const path of ['/sensors', '/calibration']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: 'We can’t find that page' })).toBeVisible()
  }
})

test('On a phone the documents are a list and the upload is a sheet @phone @DOC-3', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/stations')
  await page.getByRole('list', { name: 'Stations' }).or(page.getByRole('table', { name: /Stations/ })).getByRole('link', { name: /JM-KIN-001|Kingston Harbour/ }).first().click()
  await page.getByRole('tab', { name: 'Documents' }).click()
  await expect(page.getByRole('list', { name: 'Documents for Kingston Harbour' })).toBeVisible()
  await page.getByRole('button', { name: 'Upload document' }).click()
  const sheet = page.getByRole('dialog', { name: 'Upload a document' })
  await expect(sheet).toBeVisible()
  const box = await sheet.boundingBox()
  const viewport = page.viewportSize()!
  // A sheet rising from the bottom edge, inside the screen
  expect(box!.y + box!.height).toBeGreaterThan(viewport.height - 4)
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width)
  await checkA11y(page, 'upload sheet (phone)')
})
