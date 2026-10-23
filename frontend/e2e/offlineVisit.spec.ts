import type { Locator, Page } from '@playwright/test'
import { goInApp, plannedVisit } from './offlineFlows'
import { logIn, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  J6, offline (AFD J6; PRD OFF-2, OFF-5 to OFF-8; W14): a technician prepares a visit, loses the
  signal, starts it, arrives, records a note with a photo, leaves and ends the visit, all on the
  phone. When the signal returns the work goes up by itself, once, and the phone lets the visit go.
  Chromium only: it needs the real service worker (F6).
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
  return { name: `${text.toLowerCase()}.jpg`, mimeType: 'image/jpeg', buffer: Buffer.from(base64, 'base64') }
}

/** What is on the phone, straight from IndexedDB. */
async function held (page: Page): Promise<{ outbox: number, bundles: number, blobs: number, elements: number }> {
  return page.evaluate(async () => {
    const open = indexedDB.open('aws-mms')
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      open.addEventListener('success', () => resolve(open.result))
      open.addEventListener('error', () => reject(open.error))
    })
    const count = (name: string) => new Promise<number>((resolve, reject) => {
      const request = db.transaction(name).objectStore(name).count()
      request.addEventListener('success', () => resolve(request.result))
      request.addEventListener('error', () => reject(request.error))
    })
    const out = { outbox: await count('outbox'), bundles: await count('bundles'), blobs: await count('blobs'), elements: await count('visits') }
    db.close()
    return out
  })
}

async function untickDocuments (panel: Locator): Promise<void> {
  const boxes = panel.getByRole('checkbox')
  const count = await boxes.count()
  for (let i = 0; i < count; i++) {
    if (await boxes.nth(i).isChecked()) {
      await boxes.nth(i).uncheck()
    }
  }
}

test('A visit is recorded with no signal and goes up once when the signal returns @OFF-2 @OFF-5 @OFF-7 @OFF-8 @J6', async ({ watched: page, browser, context }) => {
  test.setTimeout(360_000)
  await logIn(page, 'tech1@example.org')
  const path = await plannedVisit(page, browser, unique('Offline visit'))

  // At the office, with signal: prepare (the first time asks for a PIN)
  const panel = page.getByRole('region', { name: 'Prepare for field' })
  await untickDocuments(panel)
  await panel.getByRole('button', { name: 'Prepare for field' }).click()
  await page.getByLabel('PIN', { exact: true }).fill('4729')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByLabel('Repeat the PIN').fill('4729')
  await page.getByRole('button', { name: 'Save PIN' }).click()
  await expect(panel.getByText('Ready offline')).toBeVisible({ timeout: 60_000 })

  // At the station: the signal is gone
  await goInApp(page, `${path}/field`)
  await context.setOffline(true)
  await page.getByRole('button', { name: 'Start visit' }).click()
  await expect(page.getByRole('button', { name: /^Arrive at Kingston Harbour/ })).toBeVisible()
  await checkA11y(page, '/visits/:id/field (started, no signal)')
  await page.getByRole('button', { name: /^Arrive at Kingston Harbour/ }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Board' })).toBeVisible()

  // A note with a photo, kept on the phone
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.getByRole('menuitem', { name: /^Note/ }).click()
  const sheet = page.getByRole('dialog', { name: /New note/ })
  await sheet.getByLabel('Title', { exact: true }).fill('Water inside the enclosure')
  const named = page.getByRole('dialog', { name: 'Water inside the enclosure' })
  await expect(named.getByText(/Saved · /)).toBeVisible({ timeout: 15_000 })
  await named.getByRole('region', { name: 'Photos and video' }).locator('input[type=file]').setInputFiles(await photo(page, 'Seal'))
  await expect(named.getByText('On phone')).toBeVisible({ timeout: 30_000 })
  await checkA11y(page, '/visits/:id/field (note with a photo, no signal)')
  await named.getByRole('button', { name: 'Done' }).click()
  const card = page.getByRole('listitem').filter({ has: page.getByRole('button', { name: 'Water inside the enclosure', exact: true }) })
  await expect(card).toContainText('Not saved yet')
  await expect(card).toContainText('1 photo')

  // Leave the station and end the visit
  await page.getByRole('button', { name: /^Depart from Kingston Harbour/ }).click()
  const left = await held(page)
  expect(left.outbox).toBeGreaterThanOrEqual(5) // start, arrive, create, media, depart
  expect(left.blobs).toBe(1)
  await page.getByRole('button', { name: 'End visit' }).click()
  const end = page.getByRole('dialog', { name: 'End visit' })
  await end.getByRole('button', { name: 'End visit' }).click()
  await expect(page).toHaveURL(/\/sync$/)

  // Nothing left the phone yet
  expect((await held(page)).outbox).toBeGreaterThanOrEqual(6)

  // The signal returns: it all goes up by itself, and the phone lets the visit go
  await context.setOffline(false)
  await expect.poll(async () => (await held(page)).outbox, { timeout: 120_000, intervals: [1000] }).toBe(0)
  await expect.poll(async () => held(page), { timeout: 30_000 }).toMatchObject({ bundles: 0, blobs: 0, elements: 0 })

  // The server has one visit, ended, with one note and its photo, however many times it was sent
  await page.goto(path)
  await expect(page.getByText('Ended', { exact: true }).first()).toBeVisible()
  const board = page.getByRole('listitem').filter({ has: page.getByRole('button', { name: 'Water inside the enclosure', exact: true }) })
  await expect(board).toHaveCount(1)
  await expect(board).toContainText('1 photo')
  await expect(board).not.toContainText('Not saved yet')
})
