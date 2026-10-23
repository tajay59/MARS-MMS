import type { Page } from '@playwright/test'
import { goInApp } from './offlineFlows'
import { claimedRequest, logIn, staffPage, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Needs attention (AFD §6, TRD §7.4; PRD OFF-7, OFF-11; W14): while a technician's phone is offline
  with a prepared visit, an admin gives one of its stations to a colleague. When the signal returns
  the phone's start applies, its arrival at that station comes back as `not_owner`, and the phone
  keeps its copy: the person exports it, says they are done with it, and the work that waited
  behind it goes up. Chromium only: it needs the real service worker (F6).
*/

async function outboxCount (page: Page): Promise<number> {
  return page.evaluate(async () => {
    const open = indexedDB.open('aws-mms')
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      open.addEventListener('success', () => resolve(open.result))
      open.addEventListener('error', () => reject(open.error))
    })
    const count = await new Promise<number>((resolve, reject) => {
      const request = db.transaction('outbox').objectStore('outbox').count()
      request.addEventListener('success', () => resolve(request.result))
      request.addEventListener('error', () => reject(request.error))
    })
    db.close()
    return count
  })
}

test('A station given away while the phone is offline comes back as a conflict that is exported and done with @OFF-7 @OFF-11 @J6', async ({ watched: page, browser, context }) => {
  test.setTimeout(360_000)
  const title = unique('Conflict visit')
  const request = await claimedRequest(browser, title)

  // Tech 1 plans the visit with Tech 2 attending, so there is someone to give a station to
  await logIn(page, 'tech1@example.org')
  await page.goto(request)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  const schedule = page.getByRole('dialog', { name: 'Schedule visit' })
  await schedule.getByRole('button', { name: 'Add person' }).click()
  await page.getByRole('menuitem', { name: /Tech 2/ }).click()
  await page.keyboard.press('Escape')
  await schedule.getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/VR-\d{4}-\d{4}-01 is planned\./)).toBeVisible()
  await page.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ }).getByRole('link', { name: /VR-/ }).click()
  await expect(page).toHaveURL(/\/visits\/[\da-f-]{36}$/)
  const path = new URL(page.url()).pathname

  // Prepare it (the first time asks for a PIN), then lose the signal at the station
  const panel = page.getByRole('region', { name: 'Prepare for field' })
  const boxes = panel.getByRole('checkbox')
  for (let i = 0; i < await boxes.count(); i++) {
    if (await boxes.nth(i).isChecked()) {
      await boxes.nth(i).uncheck()
    }
  }
  await panel.getByRole('button', { name: 'Prepare for field' }).click()
  await page.getByLabel('PIN', { exact: true }).fill('4729')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByLabel('Repeat the PIN').fill('4729')
  await page.getByRole('button', { name: 'Save PIN' }).click()
  await expect(panel.getByText('Ready offline')).toBeVisible({ timeout: 60_000 })
  await goInApp(page, `${path}/field`)
  await context.setOffline(true)

  await page.getByRole('button', { name: 'Start visit' }).click()
  await page.getByRole('button', { name: /^Arrive at Kingston Harbour/ }).click()
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.getByRole('menuitem', { name: /^Note/ }).click()
  await page.getByRole('dialog', { name: /New note/ }).getByLabel('Title', { exact: true }).fill('Water inside the enclosure')
  const named = page.getByRole('dialog', { name: 'Water inside the enclosure' })
  await expect(named.getByText(/Saved · /)).toBeVisible({ timeout: 15_000 })
  await named.getByRole('button', { name: 'Done' }).click()

  // Meanwhile the admin gives Kingston Harbour to Tech 2, and is warned about the phone
  const admin = await staffPage(browser, 'admin@example.org')
  await admin.goto(path)
  await admin.getByRole('row', { name: /Kingston Harbour/ }).getByRole('button', { name: 'Change owner' }).click()
  const owner = admin.getByRole('dialog', { name: 'Change owner' })
  await expect(owner.getByText('This visit is prepared on Tech 1’s phone.')).toBeVisible()
  // The dialog is still fading in when it first shows: click until the list opens
  await expect(async () => {
    await owner.getByRole('combobox', { name: 'New owner' }).click({ force: true })
    await expect(admin.getByRole('option', { name: /^Tech 2/ })).toBeVisible({ timeout: 1000 })
  }).toPass({ timeout: 15_000 })
  await admin.getByRole('option', { name: /^Tech 2/ }).click()
  await owner.getByRole('button', { name: 'Change owner' }).click()
  await expect(admin.getByText('Owner changed. Both people are told.')).toBeVisible()
  await admin.context().close()

  // The signal returns: the start applies, the arrival is refused, and the phone keeps its copy
  await context.setOffline(false)
  await goInApp(page, '/sync')
  await expect(page.getByRole('heading', { name: 'Needs attention' })).toBeVisible({ timeout: 60_000 })
  const card = page.getByRole('article').filter({ hasText: 'Owner changed' })
  await expect(card).toContainText('Your work on it is saved on this phone')
  await expect(page.getByRole('status').filter({ hasText: 'thing needs you' })).toBeVisible()
  await checkA11y(page, '/sync (needs attention)')

  // Export writes the person's own copy out as a file
  await card.getByRole('button', { name: 'Export' }).click()
  const sheet = page.getByRole('dialog', { name: 'Export your work' })
  await expect(sheet).toBeVisible()
  await expect(sheet.getByText('Written work', { exact: true })).toBeVisible()
  await checkA11y(page, '/sync (export)')
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    sheet.getByRole('button', { name: 'Save to this phone' }).click(),
  ])
  expect(download.suggestedFilename()).toMatch(/^VR-\d{4}-\d{4}-01-JM-KIN-001-\d{4}-\d{2}-\d{2}\.json$/)

  // Nothing is removed until the person says so, and then what waited behind it goes up
  await sheet.getByRole('button', { name: 'Back' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Done with this' }).click()
  await page.getByRole('dialog', { name: 'Remove it from this phone?' }).getByRole('button', { name: 'Remove' }).click()
  await expect(page.getByRole('heading', { name: 'Needs attention' })).toHaveCount(0, { timeout: 30_000 })
  await expect.poll(() => outboxCount(page), { timeout: 60_000, intervals: [1000] }).toBe(0)
  await expect(page.getByText('All synced')).toBeVisible()
})
