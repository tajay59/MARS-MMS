import { claimedRequest, logIn, staffPage, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Visits, W10 (PRD VIS-1 to VIS-4, VIS-9, VIS-11; AFD J5 steps 3 to 5b), on the demo seed. A client
  asks about two stations, an admin approves, a technician claims and plans a visit with a colleague
  as lead and a different owner for each station; the client sees the dates and the names and no
  notes; the lead starts it, each owner arrives and leaves their own station, and the lead ends it
  saying another visit is needed, which sends the request back to Assigned.
*/

test('A technician plans a visit with a colleague as lead, and the lead runs it @REQ-VIS-1 @J5', async ({ watched: tech1, browser }) => {
  const title = unique('No readings')
  const path = await claimedRequest(browser, title)

  // Tech 1 plans it: Tech 2 leads, and each owns one station
  await logIn(tech1, 'tech1@example.org')
  await tech1.goto(path)
  await expect(tech1.getByRole('button', { name: 'Schedule visit' })).toBeVisible()
  await tech1.getByRole('button', { name: 'Schedule visit' }).click()
  const dialog = tech1.getByRole('dialog', { name: 'Schedule visit' })
  await expect(dialog.getByRole('list', { name: 'Attending' }).getByText('Tech 1')).toBeVisible()
  await checkA11y(tech1, '/requests/:id (schedule visit)')
  await dialog.getByRole('button', { name: 'Add person' }).click()
  await tech1.getByRole('menuitem', { name: /Tech 2/ }).click()
  await tech1.keyboard.press('Escape')
  await dialog.getByRole('button', { name: 'Make Tech 2 the lead' }).click()
  await expect(dialog.getByRole('button', { name: 'Tech 2 is the lead' })).toBeVisible()
  await dialog.getByRole('combobox', { name: 'Owner of Kingston Harbour' }).click({ force: true })
  await tech1.getByRole('option', { name: /^Tech 1/ }).click()
  await dialog.getByRole('combobox', { name: 'Owner of Montego Bay Airport' }).click({ force: true })
  await tech1.getByRole('option', { name: /^Tech 2/ }).click()
  await dialog.getByLabel('Notes (optional)').fill('Bring the long ladder.')
  await dialog.getByRole('button', { name: 'Schedule visit' }).click()
  await expect(tech1.getByText(/VR-\d{4}-\d{4}-01 is planned\./)).toBeVisible()

  // The Visits tab lists it, and the request is Scheduled
  await expect(tech1.getByRole('tab', { name: /Visits/ })).toHaveAttribute('aria-selected', 'true')
  const row = tech1.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ })
  await expect(row.getByText('Tech 2')).toBeVisible()
  await expect(row.getByText('Planned')).toBeVisible()
  await expect(tech1.getByText('Scheduled', { exact: true }).first()).toBeVisible()
  await row.getByRole('link', { name: /VR-/ }).click()
  await expect(tech1).toHaveURL(/\/visits\/[\da-f-]{36}$/)
  const visitPath = new URL(tech1.url()).pathname
  await expect(tech1.getByText('Bring the long ladder.')).toBeVisible()
  await expect(tech1.getByRole('button', { name: 'Reschedule' })).toBeVisible()
  await expect(tech1.getByRole('button', { name: 'Cancel visit' })).toBeVisible()
  await checkA11y(tech1, '/visits/:id (planned)')

  // The client sees the dates and the names, no notes and no buttons
  const client = await staffPage(browser, 'client.a1@example.org')
  await client.goto(path)
  await client.getByRole('tab', { name: /Visits/ }).click()
  await expect(client.getByRole('row', { name: /VR-\d{4}-\d{4}-01/ }).getByText('Tech 2')).toBeVisible()
  await client.goto(visitPath)
  await expect(client.getByRole('heading', { level: 1, name: /VR-/ })).toBeVisible()
  await expect(client.getByText('Tech 1, Tech 2').first()).toBeVisible()
  await expect(client.getByText('Bring the long ladder.')).toHaveCount(0)
  for (const name of ['Reschedule', 'Cancel visit', 'Start visit', 'End visit', 'Change owner']) {
    await expect(client.getByRole('button', { name })).toHaveCount(0)
  }
  await checkA11y(client, '/visits/:id (client)')

  // ... and was told, in the app, with a link to the visit
  await client.goto('/notifications')
  const told = client.getByRole('link', { name: /Visit planned/ }).first()
  await expect(told).toBeVisible({ timeout: 30_000 })
  await expect(told).toHaveAttribute('href', visitPath)
  await client.context().close()

  // Only the lead's people may start: Tech 2 starts it, and the request is In progress
  const lead = await staffPage(browser, 'tech2@example.org')
  await lead.goto('/visits')
  await lead.getByRole('link', { name: /VR-\d{4}-\d{4}-01/ }).first().click()
  await lead.getByRole('button', { name: 'Start visit' }).click()
  await expect(lead.getByText('Visit started. The request is In progress.')).toBeVisible()
  const stations = lead.getByRole('table', { name: /Stations on this visit/ })
  await expect(stations.getByRole('row', { name: /Kingston Harbour/ }).getByText(/Only they can arrive here/)).toBeVisible()
  await stations.getByRole('row', { name: /Montego Bay Airport/ }).getByRole('button', { name: 'Arrive' }).click()
  await expect(lead.getByText('Arrival recorded.')).toBeVisible()
  await expect(stations.getByRole('row', { name: /Kingston Harbour/ }).getByRole('button', { name: 'Arrive' })).toHaveCount(0)
  await checkA11y(lead, '/visits/:id (started)')

  // Tech 1 owns Kingston Harbour: arrives and leaves it, and has no Arrive on the other
  await tech1.goto(visitPath)
  const mine = tech1.getByRole('table', { name: /Stations on this visit/ })
  await expect(mine.getByRole('row', { name: /Montego Bay Airport/ }).getByRole('button', { name: 'Depart' })).toHaveCount(0)
  await mine.getByRole('row', { name: /Kingston Harbour/ }).getByRole('button', { name: 'Arrive' }).click()
  await expect(tech1.getByText('Arrival recorded.')).toBeVisible()
  await mine.getByRole('row', { name: /Kingston Harbour/ }).getByRole('button', { name: 'Depart' }).click()
  await expect(tech1.getByText('Departure recorded.')).toBeVisible()

  // The lead ends it: another visit is needed, so the request goes back to Assigned
  await lead.reload()
  await lead.getByRole('button', { name: 'End visit' }).click()
  const end = lead.getByRole('dialog', { name: 'End visit' })
  await end.getByRole('button', { name: 'Yes' }).click()
  await end.getByRole('button', { name: 'End visit' }).click()
  await expect(end.getByText('Say what work remains')).toBeVisible()
  await end.getByLabel('What work remains').fill('Replace the solar panel at Montego Bay.')
  await end.getByRole('button', { name: 'End visit' }).click()
  await expect(lead.getByText(/Visit ended\. The request is back to Assigned/)).toBeVisible()
  await expect(lead.getByText('Replace the solar panel at Montego Bay.')).toBeVisible()
  await lead.goto(path)
  await expect(lead.getByText('Assigned', { exact: true }).first()).toBeVisible()
  await lead.context().close()
})

test('A planned visit is rescheduled, an owner changed, and the visit cancelled @REQ-VIS-2 @J5', async ({ watched: page, browser }) => {
  const title = unique('Logger reset')
  const path = await claimedRequest(browser, title)

  await logIn(page, 'tech1@example.org')
  await page.goto(path)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  const dialog = page.getByRole('dialog', { name: 'Schedule visit' })
  await dialog.getByRole('button', { name: 'Add person' }).click()
  await page.getByRole('menuitem', { name: /Tech 2/ }).click()
  await page.keyboard.press('Escape')
  await dialog.getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/is planned\./)).toBeVisible()
  await page.getByRole('row', { name: /VR-/ }).getByRole('link').click()

  await page.getByRole('button', { name: 'Reschedule' }).click()
  const reschedule = page.getByRole('dialog', { name: 'Reschedule visit' })
  await reschedule.getByLabel('Ends').fill('2099-01-02T10:00')
  await reschedule.getByLabel('Starts').fill('2099-01-02T08:00')
  await checkA11y(page, '/visits/:id (reschedule)')
  await reschedule.getByRole('button', { name: 'Reschedule' }).click()
  await expect(page.getByText('Visit rescheduled. Everyone is told.')).toBeVisible()
  await expect(page.getByText(/Fri 2 Jan, 08:00 to 10:00/)).toBeVisible()

  await page.getByRole('row', { name: /Kingston Harbour/ }).getByRole('button', { name: 'Change owner' }).click()
  const owner = page.getByRole('dialog', { name: 'Change owner' })
  await owner.getByRole('combobox', { name: 'New owner' }).click({ force: true })
  await page.getByRole('option', { name: /Tech 2/ }).click()
  await owner.getByRole('button', { name: 'Change owner' }).click()
  await expect(page.getByText('Owner changed. Both people are told.')).toBeVisible()
  await expect(page.getByRole('row', { name: /Kingston Harbour/ }).getByText('Tech 2')).toBeVisible()

  await page.getByRole('button', { name: 'Cancel visit' }).click()
  const cancel = page.getByRole('dialog', { name: /Cancel visit/ })
  await cancel.getByLabel('Reason (optional)').fill('Storm warning')
  await cancel.getByRole('button', { name: 'Cancel visit' }).click()
  await expect(page.getByText('Visit cancelled. Everyone is told.')).toBeVisible()
  await expect(page.getByText('This visit was cancelled.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start visit' })).toHaveCount(0)
  await page.goto(path)
  await expect(page.getByText('Assigned', { exact: true }).first()).toBeVisible()
})

test('Visits on a phone: cards, a sheet, and the stations as cards @REQ-VIS-1 @phone', async ({ watched: page, browser }) => {
  const title = unique('Mast lamp')
  const path = await claimedRequest(browser, title)

  await logIn(page, 'tech1@example.org')
  await page.goto(path)
  await page.getByRole('button', { name: 'Schedule visit' }).click()
  const sheet = page.getByRole('dialog', { name: 'Schedule visit' })
  await expect(sheet).toBeVisible()
  await checkA11y(page, '/requests/:id (schedule visit sheet)')
  await sheet.getByRole('button', { name: 'Schedule visit' }).click()
  await expect(page.getByText(/is planned\./)).toBeVisible()

  await page.goto('/visits')
  await expect(page.getByRole('list', { name: 'Visits' }).getByRole('link', { name: new RegExp(title) })).toBeVisible()
  await checkA11y(page, '/visits (phone)')
  await page.getByRole('list', { name: 'Visits' }).getByRole('link', { name: new RegExp(title) }).click()
  await expect(page.getByRole('list', { name: 'Stations' }).getByText('Owned by you').first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start visit' })).toBeVisible()
  await checkA11y(page, '/visits/:id (phone)')
})
