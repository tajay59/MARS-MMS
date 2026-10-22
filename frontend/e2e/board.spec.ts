import type { Locator, Page } from '@playwright/test'
import { claimedRequest, logIn, pdf, staffPage, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  The visit board (PRD VIS-5, VIS-7, VIS-11; W11-16 to W11-35; the approved Stitch boards). A
  technician starts a visit and fills in a station's board: a Note with a photo, a Task ticked to
  complete, another left open, and a Config with a Python file and a PDF, each file opened in the
  sheet, never in a new tab. Ending the visit warns about the open task. The client then sees the
  shared elements only.
*/

/** A picture drawn in the browser, as a phone would hand over a JPEG. */
async function photo (page: Page, text: string): Promise<{ name: string, mimeType: string, buffer: Buffer }> {
  const base64 = await page.evaluate(label => {
    const canvas = document.createElement('canvas')
    canvas.width = 640
    canvas.height = 480
    const context = canvas.getContext('2d')!
    context.fillStyle = '#2a6f97'
    context.fillRect(0, 0, 640, 480)
    context.fillStyle = '#ffffff'
    context.font = '48px sans-serif'
    context.fillText(label, 40, 240)
    return canvas.toDataURL('image/jpeg', 0.9).split(',', 2)[1]
  }, text)
  return { name: `${text.toLowerCase().replaceAll(' ', '-')}.jpg`, mimeType: 'image/jpeg', buffer: Buffer.from(base64, 'base64') }
}

/** Tech 1 plans a visit to both stations (leading, owning both), and starts it. Returns its path. */
async function startedVisit (page: Page, browser: Parameters<typeof claimedRequest>[0], title: string): Promise<string> {
  const path = await claimedRequest(browser, title)
  await logIn(page, 'tech1@example.org')
  await page.goto(path)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  await page.getByRole('dialog', { name: 'Schedule visit' }).getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/VR-\d{4}-\d{4}-01 is planned\./)).toBeVisible()
  await page.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ }).getByRole('link', { name: /VR-/ }).click()
  await expect(page).toHaveURL(/\/visits\/[\da-f-]{36}$/)
  await page.getByRole('button', { name: 'Start visit' }).click()
  await expect(page.getByText('Visit started. The request is In progress.')).toBeVisible()
  return new URL(page.url()).pathname
}

/** Opens Add and picks a kind; returns the new element's sheet. */
async function add (page: Page, kind: string): Promise<Locator> {
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.getByRole('menuitem', { name: new RegExp(`^${kind}`) }).click()
  const sheet = page.getByRole('dialog', { name: new RegExp(`New ${kind.toLowerCase()}`) })
  await expect(sheet).toBeVisible()
  return sheet
}

/** Gives the sheet a title and waits until the server has it; the sheet is then named by it. */
async function titled (page: Page, sheet: Locator, title: string): Promise<Locator> {
  await sheet.getByLabel('Title', { exact: true }).fill(title)
  const named = page.getByRole('dialog', { name: title })
  await expect(named.getByText(/Saved · /)).toBeVisible({ timeout: 15_000 })
  return named
}

/** A sticky note on the board, by its title. */
function note (page: Page, title: string): Locator {
  return page.getByRole('listitem').filter({ has: page.getByRole('button', { name: title, exact: true }) })
}

/** Opens a file from the sheet; it shows once media has checked it, which can take a while. */
async function opensInPlace (open: Locator, shows: Locator): Promise<void> {
  await open.click()
  await expect(shows).toBeVisible({ timeout: 120_000 })
}

test('A technician fills in a station’s board and the client sees what was shared @REQ-VIS-5 @REQ-VIS-7 @REQ-VIS-11 @J6', async ({ watched: page, browser }) => {
  test.setTimeout(300_000)
  const visitPath = await startedVisit(page, browser, unique('Modem offline'))

  // An empty board, for the station the technician owns
  await expect(page.getByRole('heading', { level: 2, name: 'Board' })).toBeVisible()
  await expect(page.getByText('Nothing recorded at this station yet')).toBeVisible()

  // A note with a photo, which opens in the sheet
  let sheet = await titled(page, await add(page, 'Note'), 'Water inside the enclosure')
  await sheet.getByLabel('Description (optional)').fill('Desiccant used up. The seal is cracked on the hinge side.')
  await sheet.getByRole('region', { name: 'Photos and video' }).locator('input[type=file]').setInputFiles(await photo(page, 'Seal'))
  await expect(sheet.getByRole('button', { name: /Open photo: seal\.jpg/ })).toBeVisible({ timeout: 90_000 })
  await checkA11y(page, '/visits/:id (note sheet)')
  await sheet.getByRole('button', { name: /Open photo: seal\.jpg/ }).click()
  await expect(sheet.getByRole('img', { name: /Photo 1 of 1/ })).toBeVisible()
  await sheet.getByRole('button', { name: 'Water inside the enclosure' }).click() // Back
  await sheet.getByRole('button', { name: 'Done' }).click()
  await expect(note(page, 'Water inside the enclosure')).toContainText('1 photo')
  await expect(note(page, 'Water inside the enclosure')).toContainText('Staff only')
  await expect(note(page, 'Water inside the enclosure')).toContainText('Note')

  // A task ticked to complete
  sheet = await titled(page, await add(page, 'Task'), 'Replace the RH sensor')
  for (const item of ['Fit the spare, serial V-23044', 'Check the reading against the reference']) {
    await sheet.getByLabel('New item').fill(item)
    await sheet.getByRole('button', { name: 'Add item' }).click()
  }
  await sheet.getByRole('checkbox', { name: 'Fit the spare, serial V-23044' }).check()
  await sheet.getByRole('checkbox', { name: 'Check the reading against the reference' }).check()
  await expect(sheet.getByText('Complete')).toBeVisible({ timeout: 15_000 })
  await checkA11y(page, '/visits/:id (task sheet)')
  await sheet.getByRole('button', { name: 'Done' }).click()
  await expect(note(page, 'Replace the RH sensor')).toContainText('Complete')

  // Another task left open
  sheet = await titled(page, await add(page, 'Task'), 'Check the solar charge controller')
  await sheet.getByLabel('New item').fill('Battery voltage at noon')
  await sheet.getByRole('button', { name: 'Add item' }).click()
  await expect(sheet.getByText(/Saved · /)).toBeVisible()
  await sheet.getByRole('button', { name: 'Done' }).click()

  // A Config with a Python file and a PDF, both read in the sheet
  sheet = await titled(page, await add(page, 'Config'), 'Logger program 4.2')
  const after = sheet.getByRole('region', { name: 'After' })
  await after.locator('input[type=file]').setInputFiles([
    { name: 'rh_offset.py', mimeType: 'text/x-python', buffer: Buffer.from('# RH offset for the HMP155 on channel 3\nOFFSET = -1.2\n') },
    { name: 'wiring.pdf', mimeType: 'application/pdf', buffer: pdf('RH channel wiring') },
  ])
  await expect(after.getByRole('button', { name: /^PY rh_offset\.py/ })).toBeVisible({ timeout: 90_000 })
  await expect(after.getByRole('button', { name: /^PDF wiring\.pdf/ })).toBeVisible({ timeout: 90_000 })
  await opensInPlace(after.getByRole('button', { name: /^PY rh_offset\.py/ }), sheet.getByText('OFFSET = -1.2'))
  await checkA11y(page, '/visits/:id (text file in the sheet)')
  await sheet.getByRole('button', { name: 'Logger program 4.2' }).click() // Back
  await opensInPlace(after.getByRole('button', { name: /^PDF wiring\.pdf/ }), sheet.getByRole('img', { name: 'Page 1 of 1' }))
  await sheet.getByRole('button', { name: 'Logger program 4.2' }).click()
  await sheet.getByRole('button', { name: 'Done' }).click()

  // The filters count each kind
  await expect(page.getByRole('button', { name: 'Tasks 2' })).toBeVisible()
  await page.getByRole('button', { name: 'Config 1' }).click()
  await expect(note(page, 'Water inside the enclosure')).toHaveCount(0)
  await expect(note(page, 'Logger program 4.2')).toBeVisible()
  await page.getByRole('button', { name: 'All 4' }).click()
  await checkA11y(page, '/visits/:id (board)')

  // Ending warns about the open task, and goes ahead anyway
  await page.getByRole('button', { name: 'End visit' }).click()
  const end = page.getByRole('dialog', { name: 'End visit' })
  await expect(end.getByText('1 task is not complete.')).toBeVisible()
  await expect(end.getByRole('list', { name: 'Tasks not complete' })).toContainText('Check the solar charge controller')
  await end.getByRole('button', { name: 'End anyway' }).click()
  await expect(page.getByText(/ended/i).first()).toBeVisible()

  // The client sees the shared tasks, not the note or the configuration files
  const client = await staffPage(browser, 'client.a1@example.org')
  await client.goto(visitPath)
  await expect(note(client, 'Replace the RH sensor')).toContainText('Complete')
  await expect(note(client, 'Check the solar charge controller')).toContainText('0 of 1')
  await expect(note(client, 'Water inside the enclosure')).toHaveCount(0)
  await expect(note(client, 'Logger program 4.2')).toHaveCount(0)
  await expect(client.getByRole('button', { name: 'Add', exact: true })).toHaveCount(0)
  await checkA11y(client, '/visits/:id (client board)')
  await client.context().close()
})

test('The board on a phone: one column, a floating Add and a sheet that fills the screen @REQ-VIS-5 @phone', async ({ watched: page, browser }) => {
  test.setTimeout(240_000)
  const title = unique('Rain gauge')
  const path = await claimedRequest(browser, title)
  await logIn(page, 'tech1@example.org')
  await page.goto(path)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  await page.getByRole('dialog', { name: 'Schedule visit' }).getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/is planned\./)).toBeVisible()
  await page.goto('/visits')
  await page.getByRole('list', { name: 'Visits' }).getByRole('link', { name: new RegExp(title) }).click()
  await page.getByRole('button', { name: 'Start visit' }).click()
  await expect(page.getByText('Visit started. The request is In progress.')).toBeVisible()

  // The kinds come up from the bottom
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  const kinds = page.getByRole('dialog', { name: 'Add to the board' })
  await expect(kinds).toBeVisible()
  await checkA11y(page, '/visits/:id (add sheet, phone)')
  await kinds.getByRole('button', { name: /^Task/ }).click()

  // The task fills the screen
  const sheet = await titled(page, page.getByRole('dialog', { name: 'New task' }), 'Clean the rain gauge funnel')
  const box = await sheet.boundingBox()
  expect(box?.width).toBeGreaterThanOrEqual(page.viewportSize()!.width - 1)
  await sheet.getByLabel('New item').fill('Clear the funnel and the filter')
  await sheet.getByRole('button', { name: 'Add item' }).click()
  await sheet.getByRole('checkbox', { name: 'Clear the funnel and the filter' }).check()
  await expect(sheet.getByText('Complete')).toBeVisible({ timeout: 15_000 })
  await checkA11y(page, '/visits/:id (task sheet, phone)')
  await sheet.getByRole('button', { name: 'Done' }).click()
  await expect(note(page, 'Clean the rain gauge funnel')).toContainText('Complete')
})
