import type { APIRequestContext, Page } from '@playwright/test'
import { randomBytes } from 'node:crypto'
import { claimedRequest, logIn, staffPage, unique } from './requestFlows'
import { checkA11y, expect, seedPassword, test } from './support'

/*
  Photos and video on a visit, the work record read on the visit page, and a unit made from the
  field flagged for review (W11 slice 4; PRD VIS-5, VIS-7, SEN-5, MED-1, MED-2). A technician
  plans and starts a visit, adds a photo and a short video to a station, sees them processed,
  captions and hides one; the owner's work record (written through the API, since the phone screens
  that fill it in are W12) is read on the page; ending the visit puts its sensor swap in the
  inventory, and the unit it created for an unknown serial shows Needs review until an admin clears it.
*/

/** A UUIDv7, as the browser makes them (rule 9). */
function uuid7 (): string {
  const hex = Date.now().toString(16).padStart(12, '0')
  const random = randomBytes(10).toString('hex')
  const variant = ((Number.parseInt(random[3], 16) & 0x3) | 0x8).toString(16)
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-7${random.slice(0, 3)}-${variant}${random.slice(4, 7)}-${random.slice(7, 19)}`
}

async function apiAs (playwright: { request: { newContext: (options: object) => Promise<APIRequestContext> } }, baseURL: string, email: string): Promise<APIRequestContext> {
  const anonymous = await playwright.request.newContext({ baseURL, ignoreHTTPSErrors: true })
  const login = await anonymous.post('/api/v1/auth/login', { data: { email, password: seedPassword() } })
  expect(login.ok(), await login.text()).toBe(true)
  const { access_token: token } = await login.json() as { access_token: string }
  await anonymous.dispose()
  return playwright.request.newContext({ baseURL, ignoreHTTPSErrors: true, extraHTTPHeaders: { Authorization: `Bearer ${token}` } })
}

/** A picture drawn in the browser, as a phone would hand over a JPEG. */
async function photo (page: Page, text: string): Promise<{ name: string, mimeType: string, buffer: Buffer }> {
  const base64 = await page.evaluate(label => {
    const canvas = document.createElement('canvas')
    canvas.width = 640
    canvas.height = 480
    const context = canvas.getContext('2d')!
    const gradient = context.createLinearGradient(0, 0, 640, 480)
    gradient.addColorStop(0, '#2a6f97')
    gradient.addColorStop(1, '#a9c4d0')
    context.fillStyle = gradient
    context.fillRect(0, 0, 640, 480)
    context.fillStyle = '#ffffff'
    context.font = '48px sans-serif'
    context.fillText(label, 40, 240)
    return canvas.toDataURL('image/jpeg', 0.9).split(',', 2)[1]
  }, text)
  return { name: `${text.toLowerCase().replaceAll(' ', '-')}.jpg`, mimeType: 'image/jpeg', buffer: Buffer.from(base64, 'base64') }
}

/** A two-second clip recorded from a canvas: WebM, which the media service accepts and converts. */
async function clip (page: Page): Promise<{ name: string, mimeType: string, buffer: Buffer }> {
  const base64 = await page.evaluate(async () => {
    const canvas = document.createElement('canvas')
    canvas.width = 320
    canvas.height = 240
    const context = canvas.getContext('2d')!
    const recorder = new MediaRecorder(canvas.captureStream(15), { mimeType: 'video/webm' })
    const chunks: Blob[] = []
    recorder.addEventListener('dataavailable', event => chunks.push(event.data))
    const stopped = new Promise<void>(resolve => recorder.addEventListener('stop', () => resolve()))
    recorder.start()
    for (let frame = 0; frame < 30; frame++) {
      context.fillStyle = `hsl(${frame * 12}, 70%, 50%)`
      context.fillRect(0, 0, 320, 240)
      await new Promise(resolve => setTimeout(resolve, 66))
    }
    recorder.stop()
    await stopped
    const reader = new FileReader()
    const done = new Promise<string>(resolve => reader.addEventListener('load', () => resolve(String(reader.result))))
    reader.readAsDataURL(new Blob(chunks, { type: 'video/webm' }))
    return (await done).split(',', 2)[1]
  })
  return { name: 'walk-round.webm', mimeType: 'video/webm', buffer: Buffer.from(base64, 'base64') }
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

test('A technician adds a photo and a video to a station, and the swap lands in the inventory @REQ-VIS-5 @REQ-SEN-5 @J6', async ({ watched: page, browser, playwright, baseURL }) => {
  test.setTimeout(240_000)
  const visitPath = await startedVisit(page, browser, unique('Modem offline'))
  const visitId = visitPath.split('/').pop()!

  // The page offers photos and video for each station, with nothing in them yet
  const media = page.locator('section[aria-labelledby="vm-h"]')
  await expect(page.getByRole('heading', { level: 2, name: 'Photos and video' })).toBeVisible()
  await expect(page.getByText('Photos and video are shared with the client when the visit ends.')).toBeVisible()
  const kingston = media.locator('[data-station]').filter({ hasText: 'Kingston Harbour' })
  await expect(kingston.getByText('No photos or video here yet.')).toBeVisible()

  // A photo for Before, and a short video for After
  await kingston.getByRole('button', { name: 'Add photo or video' }).click()
  const add = page.getByRole('dialog', { name: 'Add to Kingston Harbour' })
  await expect(add).toBeVisible()
  await checkA11y(page, '/visits/:id (add photo or video)')
  await add.getByRole('button', { name: 'Before' }).click()
  await page.locator('input[type=file][multiple]').setInputFiles(await photo(page, 'Mast base'))
  await expect(kingston.getByRole('button', { name: /Open photo: mast-base\.jpg/ })).toBeVisible({ timeout: 90_000 })

  await kingston.getByRole('button', { name: 'Add photo or video' }).click()
  await page.getByRole('dialog', { name: 'Add to Kingston Harbour' }).getByRole('button', { name: 'After' }).click()
  await page.locator('input[type=file][multiple]').setInputFiles(await clip(page))
  // The clip goes up, is checked and converted by the worker; its thumbnail then appears
  await expect(kingston.getByRole('button', { name: /Open video: walk-round\.webm/ })).toBeVisible({ timeout: 180_000 })
  await expect(kingston.getByRole('region', { name: 'Before, 1' })).toBeVisible()
  await expect(kingston.getByRole('region', { name: 'After, 1' })).toBeVisible()
  await expect(page.getByText('2 files')).toBeVisible()

  // A caption, and hiding one from the client and showing it again
  await kingston.getByRole('button', { name: 'More for mast-base.jpg' }).click()
  await page.getByRole('menuitem', { name: 'Edit caption' }).click()
  const caption = page.getByRole('dialog', { name: 'Caption' })
  await caption.getByLabel('What the picture shows (optional)').fill('Mast base, guy wire north')
  await caption.getByRole('button', { name: 'Save' }).click()
  await expect(kingston.getByText('Mast base, guy wire north')).toBeVisible()

  await kingston.getByRole('button', { name: 'More for Mast base, guy wire north' }).click()
  await page.getByRole('menuitem', { name: 'Hide from client' }).click()
  await expect(kingston.getByText('Hidden from client')).toBeVisible()
  await checkA11y(page, '/visits/:id (photos and video)')
  await kingston.getByRole('button', { name: 'More for Mast base, guy wire north' }).click()
  await page.getByRole('menuitem', { name: 'Show to client' }).click()
  await expect(kingston.getByText('Hidden from client')).toHaveCount(0)

  // The owner's record is written by the phone screens in W12; here it goes in through the API
  const api = await apiAs(playwright, baseURL!, 'tech1@example.org')
  const visit = await (await api.get(`/api/v1/visits/${visitId}`)).json() as {
    stations: { station_id: string, station_name: string, work: { version: number, checklist: { item_id: string, result: string | null, note: string | null, ad_hoc: boolean, label: string }[] } | null }[]
  }
  const station = visit.stations.find(s => s.station_name === 'Kingston Harbour')!
  const installed = await (await api.get('/api/v1/sensor-units', { params: { station_id: station.station_id, status: 'installed', limit: 50 } })).json() as {
    items: { serial: string, parameter: string | null, model: { id: string } }[]
  }
  const old = installed.items.find(u => u.parameter)!
  const serial = `E2E-${randomBytes(3).toString('hex').toUpperCase()}`
  const saved = await api.put(`/api/v1/visits/${visitId}/stations/${station.station_id}/work`, {
    data: {
      base_version: station.work?.version ?? 0,
      device_id: 'e2e',
      condition_on_arrival: { status: 'degraded', notes: 'Water in the enclosure.' },
      // The template's rows as they were (none in the demo data), and one the technician added
      checklist: [
        ...(station.work?.checklist ?? []).map(row => ({
          item_id: row.item_id, ad_hoc: row.ad_hoc, label: row.ad_hoc ? row.label : undefined, result: 'ok',
        })),
        { item_id: uuid7(), ad_hoc: true, label: 'Check the enclosure seal', result: 'issue', note: 'Seal is cracked.' },
      ],
      sensor_actions: [{
        id: uuid7(), action: 'replace', parameter: old.parameter, sensor_model_id: old.model.id,
        old_serial: old.serial, new_serial: serial, removal_reason: 'faulty',
      }],
      parts_used: [{ id: uuid7(), description: 'Desiccant pack', quantity: 2 }],
      issues_found: [{ id: uuid7(), description: 'Cracked seal', severity: 'high' }],
      condition_on_departure: { status: 'operational' },
      notes: 'Left a spare seal kit with the harbour office.',
    },
  })
  expect(saved.ok(), await saved.text()).toBe(true)
  await api.dispose()

  // The record reads as sentences; the swap is still a draft until the visit ends
  await page.reload()
  const record = page.locator('section[aria-labelledby="wr-h"]')
  await expect(record.getByRole('heading', { level: 2, name: 'Work record' })).toBeVisible()
  await expect(record.getByText('Added on the visit')).toBeVisible()
  await expect(record.getByText('Check the enclosure seal')).toBeVisible()
  await expect(record.getByText('Seal is cracked.')).toBeVisible()
  await expect(record.getByText('Cracked seal')).toBeVisible()
  await expect(record.getByText('2 × Desiccant pack')).toBeVisible()
  await expect(record.getByText(`Replaced`)).toBeVisible()
  await expect(record.getByText(serial)).toBeVisible()
  await expect(record.getByText('Draft')).toBeVisible()
  await checkA11y(page, '/visits/:id (work record)')

  // Ending the visit puts the swap in the inventory
  await page.getByRole('button', { name: 'End visit' }).click()
  const end = page.getByRole('dialog', { name: 'End visit' })
  await end.getByRole('button', { name: 'End visit' }).click()
  await expect(page.getByText('Visit ended.')).toBeVisible()
  await expect(record.getByText('In the inventory')).toBeVisible()
  // ... and a client does not see the photos, the video or the record on the page
  const client = await staffPage(browser, 'client.a1@example.org')
  await client.goto(visitPath)
  await expect(client.getByRole('heading', { level: 1, name: /VR-/ })).toBeVisible()
  await expect(client.getByRole('heading', { name: 'Photos and video' })).toHaveCount(0)
  await expect(client.getByRole('heading', { name: 'Work record' })).toHaveCount(0)
  await client.context().close()

  // The unit made for the unknown serial shows Needs review, in the list and on its model
  const admin = await staffPage(browser, 'admin@example.org')
  await admin.goto('/sensors?review=1')
  const list = admin.getByRole('list', { name: 'Units that need review' })
  const row = list.getByRole('listitem').filter({ hasText: serial })
  await expect(row).toBeVisible()
  await expect(row.getByText('Needs review')).toBeVisible()
  await expect(admin.getByRole('button', { name: /Needs review/ })).toHaveAttribute('aria-pressed', 'true')
  await row.getByRole('link', { name: serial }).click()
  await expect(admin.getByText(`${serial} needs a check.`)).toBeVisible()
  await checkA11y(admin, '/sensors (needs review)')

  // Leave the demo data as found: a correction that removes the swap puts the old unit back and
  // removes the unit it made (W11-7). It has to come before anyone edits that unit, which would
  // refuse it (sensor_changed_later)
  const owner = await apiAs(playwright, baseURL!, 'tech1@example.org')
  const ended = await (await owner.get(`/api/v1/visits/${visitId}`)).json() as { stations: { station_id: string, work: { version: number, sensor_actions: unknown[] } }[] }
  const work = ended.stations.find(s => s.station_id === station.station_id)!.work
  expect(work.sensor_actions).toHaveLength(1)
  const undone = await owner.put(`/api/v1/visits/${visitId}/stations/${station.station_id}/work`, { data: { base_version: work.version, sensor_actions: [] } })
  expect(undone.ok(), await undone.text()).toBe(true)
  const after = await (await owner.get('/api/v1/sensor-units', { params: { station_id: station.station_id, status: 'installed', limit: 50 } })).json() as { items: { serial: string }[] }
  expect(after.items.map(u => u.serial)).toContain(old.serial)
  expect(after.items.map(u => u.serial)).not.toContain(serial)
  await owner.dispose()
  await admin.goto('/sensors?review=1')
  await expect(list.getByText(serial)).toHaveCount(0)

  // An admin flags a unit and clears it again with "Mark as reviewed"
  const staff = await apiAs(playwright, baseURL!, 'admin@example.org')
  const found = await (await staff.get('/api/v1/sensor-units', { params: { q: old.serial, limit: 5 } })).json() as { items: { id: string, serial: string, version: number }[] }
  const unit = found.items.find(u => u.serial === old.serial)!
  const flagged = await staff.patch(`/api/v1/sensor-units/${unit.id}`, { data: { version: unit.version, needs_review: true } })
  expect(flagged.ok(), await flagged.text()).toBe(true)
  await staff.dispose()
  await admin.goto('/sensors?review=1')
  await list.getByRole('listitem').filter({ hasText: old.serial }).getByRole('link', { name: old.serial }).click()
  await expect(admin.getByText(`${old.serial} needs a check.`)).toBeVisible()
  await admin.getByRole('button', { name: 'Mark as reviewed' }).click()
  await expect(admin.getByText(`${old.serial} needs a check.`)).toHaveCount(0)
  await admin.goto('/sensors?review=1')
  await expect(list.getByText(old.serial)).toHaveCount(0)
  await admin.context().close()
})
