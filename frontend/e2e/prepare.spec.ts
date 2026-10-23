import type { Browser, Page } from '@playwright/test'
import { claimedRequest, logIn, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Prepare for field (OFF-1, AFD J5 step 4; W13-9 to W13-14): a technician sets the device PIN the
  first time, the visit's bundle and files go onto the phone, and the visit reads "Ready offline".
  Kingston Harbour gets a configuration version and a document of its own here, so the download has
  real files from the SeaweedFS host to fetch.
*/

/** A small, valid PDF: media checks the first bytes against the name. */
function pdf (text: string): Buffer {
  return Buffer.from(`%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n% ${text}\ntrailer<</Root 1 0 R>>\n%%EOF\n`)
}

async function openKingston (page: Page, tab: string): Promise<void> {
  await page.goto('/stations')
  await page.getByRole('table', { name: /Stations/ }).getByRole('link', { name: 'JM-KIN-001' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Kingston Harbour' })).toBeVisible()
  await page.getByRole('tab', { name: tab }).click()
}

/** Tech 1 gives Kingston Harbour a configuration version and a manual. */
async function stationFiles (page: Page, run: string): Promise<void> {
  await openKingston(page, 'Configurations')
  await page.getByRole('button', { name: 'New version' }).click()
  const dialog = page.getByRole('dialog', { name: 'New configuration version' })
  await dialog.getByTestId('config-files').setInputFiles([
    { name: `logger-${run}.cfg`, mimeType: 'text/plain', buffer: Buffer.from(`program ${run}`) },
    { name: 'network.json', mimeType: 'text/plain', buffer: Buffer.from('{"apn":"one"}') },
  ])
  await expect(dialog.getByText(/ · ready$/)).toHaveCount(2, { timeout: 60_000 })
  await dialog.getByLabel('What changed').fill(`For the field ${run}`)
  await dialog.getByRole('button', { name: /^Save version/ }).click()
  await expect(dialog).toBeHidden()

  await page.getByRole('tab', { name: 'Documents' }).click()
  await page.getByRole('button', { name: 'Upload document' }).click()
  const upload = page.getByRole('dialog', { name: 'Upload a document' })
  await upload.getByTestId('document-file').setInputFiles({ name: `manual-${run}.pdf`, mimeType: 'application/pdf', buffer: pdf('manual') })
  await upload.getByLabel('Title').fill(`Logger manual ${run}`)
  await upload.getByRole('button', { name: 'Upload', exact: true }).click()
  await expect(upload).toBeHidden()
}

/** A planned visit to both stations, owned by Tech 1. Returns its path. */
async function plannedVisit (page: Page, browser: Browser, title: string): Promise<string> {
  const path = await claimedRequest(browser, title)
  await page.goto(path)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  await page.getByRole('dialog', { name: 'Schedule visit' }).getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/VR-\d{4}-\d{4}-01 is planned\./)).toBeVisible()
  await page.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ }).getByRole('link', { name: /VR-/ }).click()
  await expect(page).toHaveURL(/\/visits\/[\da-f-]{36}$/)
  return new URL(page.url()).pathname
}

/** What the phone holds, read straight from IndexedDB. */
async function onPhone (page: Page): Promise<{ bundles: { visit_id: string, ready: boolean, files_done: number, files_total: number }[], files: { name: string, size: number, required: boolean, blobSize: number }[] }> {
  return page.evaluate(async () => {
    const open = indexedDB.open('aws-mms')
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      open.addEventListener('success', () => resolve(open.result))
      open.addEventListener('error', () => reject(open.error))
    })
    const all = (name: string) => new Promise<any[]>((resolve, reject) => {
      const request = db.transaction(name).objectStore(name).getAll()
      request.addEventListener('success', () => resolve(request.result))
      request.addEventListener('error', () => reject(request.error))
    })
    const bundles = (await all('bundles')).map(b => ({ visit_id: b.visit_id, ready: b.ready, files_done: b.files_done, files_total: b.files_total }))
    const files = (await all('files')).map(f => ({ name: f.name, size: f.size, required: f.required, blobSize: (f.blob as Blob).size }))
    db.close()
    return { bundles, files }
  })
}

test('A technician prepares a visit: the PIN, the files, then Ready offline @OFF-1 @AUTH-12 @J5', async ({ watched: page, browser }) => {
  const run = Date.now().toString(36)
  await logIn(page, 'tech1@example.org')
  await stationFiles(page, run)
  const path = await plannedVisit(page, browser, unique('Prepare'))

  const panel = page.getByRole('region', { name: 'Prepare for field' })
  await expect(panel).toBeVisible()
  await expect(panel.getByText('Always included')).toBeVisible()
  // The manual is listed with its size, ticked because it is small
  await expect(panel.getByRole('checkbox', { name: new RegExp(String.raw`manual-${run}\.pdf`) })).toBeChecked()
  await checkA11y(page, '/visits/:id (prepare)')

  // The first time, the phone asks for a PIN, then goes on to download
  await panel.getByRole('button', { name: 'Prepare for field' }).click()
  const pin = page.getByRole('dialog', { name: 'Set a PIN for this phone' })
  await pin.getByLabel('PIN', { exact: true }).fill('4729')
  await pin.getByRole('button', { name: 'Continue' }).click()
  await page.getByLabel('Repeat the PIN').fill('4729')
  await page.getByRole('button', { name: 'Save PIN' }).click()

  await expect(panel.getByText('Ready offline')).toBeVisible({ timeout: 60_000 })
  await expect(panel.getByText(/Prepared today\./)).toBeVisible()
  await checkA11y(page, '/visits/:id (ready offline)')

  const held = await onPhone(page)
  expect(held.bundles).toHaveLength(1)
  expect(held.bundles[0]).toMatchObject({ ready: true })
  const names = held.files.map(f => f.name)
  expect(names).toEqual(expect.arrayContaining([`logger-${run}.cfg`, 'network.json', `manual-${run}.pdf`]))
  expect(held.files.filter(f => f.required).map(f => f.name).toSorted()).toEqual([`logger-${run}.cfg`, 'network.json'].toSorted())
  for (const file of held.files) {
    expect(file.size).toBeGreaterThan(0)
    expect(file.blobSize).toBe(file.size)
  }

  // It is still there after a reload (it comes from the phone, not the server)
  await page.reload()
  await expect(page.getByRole('region', { name: 'Prepare for field' }).getByText('Ready offline')).toBeVisible()

  // Taking in changes is a button, and a second run leaves the same files
  await page.getByRole('button', { name: 'Update offline copy' }).click()
  await expect(page.getByRole('button', { name: 'Update offline copy' })).toBeEnabled({ timeout: 60_000 })
  expect((await onPhone(page)).files).toHaveLength(held.files.length)
  expect(path).toMatch(/\/visits\//)
})

test('Files that cannot be fetched leave the visit not ready, and Try again finishes it @OFF-1', async ({ watched: page, browser }) => {
  const run = Date.now().toString(36)
  await logIn(page, 'tech1@example.org')
  await stationFiles(page, run)
  await plannedVisit(page, browser, unique('Prepare again'))

  // The files host is out of reach; the server is not
  await page.route('https://files.mms.localhost/**', route => route.abort())
  const panel = page.getByRole('region', { name: 'Prepare for field' })
  await panel.getByRole('button', { name: 'Prepare for field' }).click()
  const pin = page.getByRole('dialog', { name: 'Set a PIN for this phone' })
  await pin.getByLabel('PIN', { exact: true }).fill('4729')
  await pin.getByRole('button', { name: 'Continue' }).click()
  await page.getByLabel('Repeat the PIN').fill('4729')
  await page.getByRole('button', { name: 'Save PIN' }).click()

  await expect(panel.getByText('The configuration files did not all arrive. Try again.')).toBeVisible({ timeout: 60_000 })
  await expect(panel.getByText('Ready offline')).toHaveCount(0)
  expect((await onPhone(page)).bundles[0]).toMatchObject({ ready: false })

  await page.unroute('https://files.mms.localhost/**')
  await panel.getByRole('button', { name: 'Try again' }).click()
  await expect(panel.getByText('Ready offline')).toBeVisible({ timeout: 60_000 })
  expect((await onPhone(page)).bundles[0]).toMatchObject({ ready: true })
})
