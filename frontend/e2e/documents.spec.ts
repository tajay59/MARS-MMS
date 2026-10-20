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

test('Technicians add and edit sensor models and units, and viewers cannot @SEN-1 @SEN-2', async ({ watched: page, browser }) => {
  const run = Date.now().toString(36)
  const name = `T-${run}`
  const serial = `SN-${run}`

  await logIn(page, 'tech1@example.org')
  await page.goto('/sensors')

  // Add a model: the form asks for what the server needs, then opens the new model
  await page.getByRole('button', { name: 'Add a model' }).click()
  const model = page.getByRole('dialog', { name: 'Add a sensor model' })
  await model.getByRole('button', { name: 'Add model' }).click()
  await expect(model.getByText('Enter the make')).toBeVisible()
  await expect(model.getByText('Enter the model')).toBeVisible()
  await model.getByLabel('Make').fill('Testco')
  await model.getByLabel('Model', { exact: true }).fill(name)
  await model.getByLabel(/Parameters it measures/).fill('at, rh')
  await model.getByLabel(/Parameters it measures/).press('Enter')
  // Every code in a typed or pasted list is added, not only the last
  await expect(model.getByRole('list', { name: /Parameters it measures/ }).getByText('AT', { exact: true })).toBeVisible()
  await expect(model.getByRole('list', { name: /Parameters it measures/ }).getByText('RH')).toBeVisible()
  await model.getByLabel(/Calibrate every/).fill('365')
  await checkA11y(page, 'model dialog')
  await model.getByRole('button', { name: 'Add model' }).click()
  await expect(model).toBeHidden()
  await expect(page.getByRole('heading', { level: 1, name: `Testco ${name}` })).toBeVisible()
  await expect(page.getByText('calibrate every 365 days')).toBeVisible()

  // The same make and model again is refused on the field; leaving asks first
  await page.getByRole('button', { name: 'Add a model' }).click()
  await model.getByLabel('Make').fill('Testco')
  await model.getByLabel('Model', { exact: true }).fill(name)
  await model.getByRole('button', { name: 'Add model' }).click()
  await expect(model.getByText(`Testco ${name} is already in the catalogue.`)).toBeVisible()
  await model.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('alertdialog', { name: 'Leave without saving?' })).toBeVisible()
  await page.getByRole('button', { name: 'Leave', exact: true }).click()
  await expect(model).toBeHidden()

  // Edit it: Save waits for a change
  await page.getByRole('button', { name: 'Edit model' }).click()
  const edit = page.getByRole('dialog', { name: `Edit Testco ${name}` })
  await expect(edit.getByRole('button', { name: 'Save' })).toBeDisabled()
  await edit.getByLabel(/Calibrate every/).fill('180')
  await edit.getByRole('button', { name: 'Save' }).click()
  await expect(edit).toBeHidden()
  await expect(page.getByText('calibrate every 180 days')).toBeVisible()

  // Add a unit; the same serial twice is refused on the field
  await expect(page.getByText('No units of this model are registered yet.')).toBeVisible()
  await page.getByRole('button', { name: 'Add a unit' }).click()
  const add = page.getByRole('dialog', { name: 'Add a unit' })
  await add.getByRole('button', { name: 'Add unit' }).click()
  await expect(add.getByText('Enter the serial number')).toBeVisible()
  await add.getByLabel('Serial number').fill(serial)
  await checkA11y(page, 'unit dialog')
  await add.getByRole('button', { name: 'Add unit' }).click()
  await expect(add).toBeHidden()
  const units = page.getByRole('table', { name: `Units of Testco ${name}` })
  await expect(units.getByRole('row', { name: new RegExp(serial) }).getByText('In stock')).toBeVisible()

  await page.getByRole('button', { name: 'Add a unit' }).click()
  await add.getByLabel('Serial number').fill(serial)
  await add.getByRole('button', { name: 'Add unit' }).click()
  await expect(add.getByText(`${serial} is already registered for this model.`)).toBeVisible()
  await add.getByRole('button', { name: 'Cancel' }).click()
  await page.getByRole('button', { name: 'Leave', exact: true }).click()
  await expect(add).toBeHidden()

  // Edit the unit from its row: put it in repair
  await page.getByRole('button', { name: `More for ${serial}` }).click()
  await page.getByRole('menuitem', { name: 'Edit unit' }).click()
  const unit = page.getByRole('dialog', { name: 'Edit unit' })
  await expect(unit.getByRole('button', { name: 'Save' })).toBeDisabled()
  await unit.getByLabel('Status').click({ force: true }) // the selected text sits over the input
  await page.getByRole('option', { name: 'In repair' }).click()
  await unit.getByRole('button', { name: 'Save' }).click()
  await expect(unit).toBeHidden()
  await expect(units.getByRole('row', { name: new RegExp(serial) }).getByText('In repair')).toBeVisible()

  // A viewer sees the catalogue and none of the buttons
  const viewerContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const viewer = await viewerContext.newPage()
  await logIn(viewer, 'viewer@example.org')
  await viewer.goto('/sensors')
  await expect(viewer.getByRole('heading', { level: 1, name: 'Sensors' })).toBeVisible()
  await expect(viewer.getByRole('button', { name: 'Add a model' })).toHaveCount(0)
  await viewer.getByRole('list', { name: 'Sensor models' }).getByRole('link', { name: `Testco ${name}` }).click()
  await expect(viewer.getByRole('heading', { name: /^Units of this model/ })).toBeVisible()
  await expect(viewer.getByRole('button', { name: 'Edit model' })).toHaveCount(0)
  await expect(viewer.getByRole('button', { name: 'Add a unit' })).toHaveCount(0)
  await expect(viewer.getByRole('button', { name: `More for ${serial}` })).toHaveCount(0)
  await viewerContext.close()
})

test('A technician edits a document’s details @DOC-4', async ({ watched: page }) => {
  const run = Date.now().toString(36)
  const title = `Mast layout ${run}`
  const renamed = `Mast layout, revised ${run}`

  await logIn(page, 'tech1@example.org')
  await openStation(page, 'Documents')
  await page.getByRole('button', { name: 'Upload document' }).click()
  const upload = page.getByRole('dialog', { name: 'Upload a document' })
  await upload.getByTestId('document-file').setInputFiles({ name: `mast-${run}.pdf`, mimeType: 'application/pdf', buffer: pdf('details') })
  await upload.getByLabel('Title').fill(title)
  await upload.getByRole('button', { name: 'Upload', exact: true }).click()
  await expect(upload).toBeHidden()

  const table = page.getByRole('table', { name: /Documents for Kingston Harbour/ })
  await expect(table.getByRole('row', { name: new RegExp(title) })).toBeVisible()
  await page.getByRole('button', { name: `More for ${title}` }).click()
  await page.getByRole('menuitem', { name: 'Edit details' }).click()
  const details = page.getByRole('dialog', { name: 'Edit details' })
  await expect(details.getByRole('button', { name: 'Save' })).toBeDisabled()

  // A title is required; leaving with a change asks first
  await details.getByLabel('Title').fill('')
  await details.getByRole('button', { name: 'Save' }).click()
  await expect(details.getByText('Enter a title')).toBeVisible()
  await details.getByLabel('Title').fill(renamed)
  await details.getByLabel('Type').click({ force: true }) // the selected text sits over the input
  await page.getByRole('option', { name: 'Installation' }).click()
  await checkA11y(page, 'document details dialog')
  await details.getByRole('button', { name: 'Save' }).click()
  await expect(details).toBeHidden()

  const row = table.getByRole('row', { name: new RegExp(renamed) })
  await expect(row).toBeVisible()
  await expect(row.getByText('Installation')).toBeVisible()
  await expect(table.getByRole('row', { name: new RegExp(`^${title}`) })).toHaveCount(0)
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

test('On a phone the model form is a sheet @phone @SEN-1', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/sensors')
  await page.getByRole('button', { name: 'Add a model' }).click()
  const sheet = page.getByRole('dialog', { name: 'Add a sensor model' })
  await expect(sheet).toBeVisible()
  const box = await sheet.boundingBox()
  const viewport = page.viewportSize()!
  // A sheet rising from the bottom edge, inside the screen, with its button still reachable
  expect(box!.y + box!.height).toBeGreaterThan(viewport.height - 4)
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width)
  await sheet.getByRole('button', { name: 'Add model' }).scrollIntoViewIfNeeded()
  await expect(sheet.getByRole('button', { name: 'Add model' })).toBeInViewport()
  await checkA11y(page, 'model sheet (phone)')
})

// A 1 x 1 PNG: media checks the first bytes against the name
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')

test('A technician adds a model with specifications and photos @SEN-1 @DOC-1', async ({ watched: page }) => {
  const run = Date.now().toString(36)
  const name = `P-${run}`

  await logIn(page, 'tech1@example.org')
  await page.goto('/sensors')
  await page.getByRole('button', { name: 'Add a model' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add a sensor model' })
  await dialog.getByLabel('Make').fill('Photoco')
  await dialog.getByLabel('Model', { exact: true }).fill(name)

  // A specification needs both its name and its value
  await dialog.getByRole('button', { name: 'Add a specification' }).click()
  await dialog.getByLabel('Specification 1 name').fill('Operating range')
  await dialog.getByRole('button', { name: 'Add model' }).click()
  await expect(dialog.getByText('Give each specification a name and a value')).toBeVisible()
  await dialog.getByLabel('Specification 1 value').fill('-80 to +60 °C')

  // Only PNG and JPEG pictures can be attached
  const photos = dialog.getByTestId('model-photo-input')
  await photos.setInputFiles({ name: `bad-${run}.webp`, mimeType: 'image/webp', buffer: PNG })
  await expect(dialog.getByText(`bad-${run}.webp isn’t a PNG or JPEG picture.`)).toBeVisible()
  await photos.setInputFiles({ name: `probe-${run}.png`, mimeType: 'image/png', buffer: PNG })
  await expect(dialog.getByRole('list', { name: 'Photos to attach' }).getByText(`probe-${run}.png`)).toBeVisible()
  await checkA11y(page, 'model dialog (specs and photos)')

  // Saving makes the model, then sends the photo and files it against it
  await dialog.getByRole('button', { name: 'Add model' }).click()
  await expect(dialog).toBeHidden({ timeout: 60_000 })
  await expect(page.getByRole('heading', { level: 1, name: `Photoco ${name}` })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Specifications' })).toBeVisible()
  await expect(page.getByText('Operating range')).toBeVisible()

  // Media's checks finish in a few seconds: then the photo is in the gallery
  const gallery = page.getByRole('group', { name: 'Photos of this model' })
  await expect(gallery.getByRole('figure', { name: 'Photo 1 of 1' })).toBeVisible({ timeout: 60_000 })
  await expect(gallery.getByRole('img', { name: `probe ${run}` })).toBeVisible()
  await checkA11y(page, '/sensors/:id (photos and specifications)')
})
