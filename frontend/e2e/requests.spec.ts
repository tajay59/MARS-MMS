import { logIn, submitRequest, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Maintenance requests, W8 (PRD REQ-1, REQ-2, REQ-5, REQ-6, REQ-8, REQ-11, REQ-15; AFD J3, J4), on the
  operations demo seed: Organization A's stations are in Jamaica, B's in Trinidad and Tobago. Each
  test makes its own requests with a title no other run uses, so the list can grow between runs.
*/

test('A client reports a problem and watches it @REQ-1 @REQ-4 @REQ-8 @J3', async ({ watched: page }) => {
  await logIn(page, 'client.a1@example.org')
  const title = unique('Rain gauge not reporting')
  await page.goto('/requests')
  await expect(page.getByRole('heading', { level: 1, name: 'Requests' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Report a problem' }).first()).toBeVisible()

  await page.getByRole('link', { name: 'Report a problem' }).first().click()
  await expect(page).toHaveURL(/\/requests\/new$/)
  await checkA11y(page, '/requests/new')

  // The form says what is missing, and goes no further
  await page.getByRole('button', { name: 'Submit request' }).click()
  await expect(page.getByText('Pick at least one station').first()).toBeVisible()
  await expect(page.getByText('Add a title').first()).toBeVisible()
  await expect(page).toHaveURL(/\/requests\/new$/)

  await submitRequest(page, title, { category: 'Power', priority: 'High' })
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await expect(page.getByText(/MR-\d{4}-\d{4}/).first()).toBeVisible() // REQ-4
  await expect(page.getByText('Submitted', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Waiting for approval')).toBeVisible()
  await expect(page.getByText('High', { exact: true }).first()).toBeVisible()
  // A client may change or cancel it, never approve it
  await expect(page.getByRole('link', { name: 'Edit' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel request' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Deny' })).toHaveCount(0)
  await checkA11y(page, '/requests/:id (client, submitted)')

  await page.getByRole('tab', { name: 'History' }).click()
  await expect(page).toHaveURL(/tab=history/)
  await expect(page.getByRole('table', { name: /Status history/ }).getByText('Submitted')).toBeVisible()

  // It is in their list, and nobody else's
  await page.goto('/requests')
  await expect(page.getByRole('table', { name: /Requests/ }).getByRole('cell', { name: title })).toBeVisible()
})

test('An admin approves a request and the client sees it @REQ-5 @REQ-6 @J4', async ({ watched: page, browser }) => {
  const title = unique('Annual inspection')
  await logIn(page, 'client.a1@example.org')
  const path = await submitRequest(page, title, { category: 'Inspection' })

  const adminContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const admin = await adminContext.newPage()
  await logIn(admin, 'admin@example.org')
  await admin.goto('/requests?status=submitted')
  const row = admin.getByRole('table', { name: /Requests/ }).getByRole('row', { name: new RegExp(title) })
  await expect(row).toBeVisible()
  await expect(admin.getByRole('table', { name: /Requests/ }).getByRole('columnheader', { name: 'Organization' })).toBeVisible()
  await row.getByRole('link').first().click()
  await expect(admin.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await expect(admin.getByText('Waiting for approval')).toBeVisible()
  await checkA11y(admin, '/requests/:id (admin, submitted)')

  await admin.getByRole('button', { name: 'Approve' }).click()
  await expect(admin.getByText('Request approved. It is now in the queue.')).toBeVisible()
  await expect(admin.getByText('Approved', { exact: true }).first()).toBeVisible()
  await expect(admin.getByRole('button', { name: 'Approve' })).toHaveCount(0) // done: no second approve
  await admin.getByRole('tab', { name: 'History' }).click()
  await expect(admin.getByRole('table', { name: /Status history/ }).getByRole('row')).toHaveCount(3) // header and two changes
  await adminContext.close()

  await page.goto(path)
  await expect(page.getByText('Approved', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('It is waiting for a technician to take it on.')).toBeVisible()
})

test('Denying needs a reason, and the client reads it @REQ-6', async ({ watched: page, browser }) => {
  const title = unique('Move the station')
  await logIn(page, 'client.a1@example.org')
  const path = await submitRequest(page, title, { category: 'Relocation' })

  const adminContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const admin = await adminContext.newPage()
  await logIn(admin, 'admin@example.org')
  await admin.goto(path)
  await admin.getByRole('button', { name: 'Deny', exact: true }).click()
  const dialog = admin.getByRole('dialog', { name: /Deny request MR-/ })
  await expect(dialog).toBeVisible()
  await checkA11y(admin, '/requests/:id (deny dialog)')
  await dialog.getByRole('button', { name: 'Deny request' }).click()
  await expect(dialog.getByText('Say why')).toBeVisible() // required
  await dialog.getByLabel('Reason').fill('This station is outside the maintenance contract.')
  await dialog.getByRole('button', { name: 'Deny request' }).click()
  await expect(admin.getByText('Request denied. The client can see your reason.')).toBeVisible()
  await expect(admin.getByText('Denied', { exact: true }).first()).toBeVisible()
  await adminContext.close()

  await page.goto(path)
  await expect(page.getByText(/^Denied/).first()).toBeVisible()
  await expect(page.getByText('Reason: This station is outside the maintenance contract.')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Edit' })).toHaveCount(0) // a denied request is done
  await expect(page.getByRole('button', { name: 'Cancel request' })).toHaveCount(0)
})

test('A client edits and then cancels their request @REQ-11', async ({ watched: page }) => {
  const title = unique('Battery dropping')
  await logIn(page, 'client.a1@example.org')
  await submitRequest(page, title, { category: 'Power' })

  await page.getByRole('link', { name: 'Edit' }).click()
  await expect(page).toHaveURL(/\/edit$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Edit request' })).toBeVisible()
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue(title)
  await page.getByLabel('Title', { exact: true }).fill(`${title} (urgent)`)
  await page.getByRole('button', { name: 'Urgent', exact: true }).click()
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Changes saved.')).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: `${title} (urgent)` })).toBeVisible()
  await expect(page.getByText('Urgent', { exact: true }).first()).toBeVisible()

  await page.getByRole('button', { name: 'Cancel request' }).click()
  const dialog = page.getByRole('dialog', { name: /Cancel request MR-/ })
  await expect(dialog).toBeVisible()
  await dialog.getByLabel('Reason (optional)').fill('The fault fixed itself.')
  await dialog.getByRole('button', { name: 'Cancel request' }).click()
  await expect(page.getByText('Request cancelled.')).toBeVisible()
  await expect(page.getByText('Cancelled', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Reason: The fault fixed itself.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel request' })).toHaveCount(0)
})

test('An admin raises a request for an organization and it starts approved @REQ-2', async ({ watched: page }) => {
  const title = unique('Planned calibration')
  await logIn(page, 'admin@example.org')
  await page.goto('/requests')
  await page.getByRole('link', { name: 'New request' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'New request' })).toBeVisible()
  await expect(page.getByLabel('Which stations is this about?')).toBeDisabled() // choose the organization first
  // The pane keeps its Requests tab marked on the form
  await expect(page.getByRole('navigation', { name: /pages/ }).getByRole('link', { name: 'Requests' })).toHaveAttribute('aria-current', 'page')

  await page.getByLabel('Raise this request for').fill('Organization A')
  await page.getByRole('option', { name: 'Organization A' }).click()
  await page.getByLabel('Which stations is this about?').fill('JM-KIN-001')
  await page.getByRole('option', { name: /JM-KIN-001/ }).click()
  await page.getByLabel('Title', { exact: true }).fill(title)
  await page.getByLabel('Description', { exact: true }).fill('Planned calibration before the rainy season.')
  await checkA11y(page, '/requests/new (admin)')
  await page.getByRole('button', { name: 'Create request' }).click()
  await expect(page).toHaveURL(/\/requests\/[\da-f-]{36}$/)
  await expect(page.getByText('Approved', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Cancel request' })).toBeVisible()
})

test('Technicians and viewers read requests and change nothing @NFR-6 @REQ-5', async ({ watched: page, browser }) => {
  const title = unique('Modem offline')
  await logIn(page, 'client.a1@example.org')
  const path = await submitRequest(page, title)

  for (const email of ['tech1@example.org', 'viewer@example.org']) {
    const context = await browser.newContext({ ignoreHTTPSErrors: true })
    const staff = await context.newPage()
    await logIn(staff, email)
    await staff.goto('/requests')
    await expect(staff.getByRole('link', { name: 'New request' })).toHaveCount(0)
    await expect(staff.getByRole('link', { name: 'Report a problem' })).toHaveCount(0)
    await staff.goto(path)
    await expect(staff.getByRole('heading', { level: 1, name: title })).toBeVisible()
    for (const name of ['Approve', 'Deny', 'Cancel request']) {
      await expect(staff.getByRole('button', { name })).toHaveCount(0)
    }
    await expect(staff.getByRole('link', { name: 'Edit' })).toHaveCount(0)
    await staff.goto('/requests/new')
    // They can't make one: the page is not found for them, as for any page their role lacks
    await expect(staff.getByRole('heading', { name: 'Page not found' })).toBeVisible()
    await context.close()
  }
})

test('A client never sees another organization’s request @NFR-6 @REQ-8', async ({ watched: page, browser }) => {
  const title = unique('Tobago coast')
  // Organization B's client makes a request
  const bContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const b = await bContext.newPage()
  await logIn(b, 'client.b1@example.org')
  await b.goto('/requests/new')
  await b.getByLabel('Which stations is this about?').fill('TT-')
  await b.getByRole('option').first().click()
  await b.getByLabel('Title', { exact: true }).fill(title)
  await b.getByLabel('Description', { exact: true }).fill('The anemometer is loose.')
  await b.getByRole('button', { name: 'Submit request' }).click()
  await expect(b).toHaveURL(/\/requests\/[\da-f-]{36}$/)
  const path = new URL(b.url()).pathname
  await bContext.close()

  await logIn(page, 'client.a1@example.org')
  await page.goto('/requests')
  await expect(page.getByRole('table', { name: /Requests/ })).toBeVisible()
  await expect(page.getByText(title)).toHaveCount(0)
  await page.goto(path)
  await expect(page.getByText('We can’t find this request.')).toBeVisible()
  await expect(page.getByText(title)).toHaveCount(0)
})

test('The list filters and keeps them in the address @REQ-15', async ({ watched: page }) => {
  const title = unique('Wind sensor stuck')
  await logIn(page, 'client.a1@example.org')
  await submitRequest(page, title, { category: 'Fault', priority: 'Urgent' })
  await page.goto('/requests')
  const table = page.getByRole('table', { name: /Requests/ })
  await expect(table.getByRole('cell', { name: title })).toBeVisible()
  await checkA11y(page, '/requests')

  await page.getByRole('button', { name: /^Submitted/ }).click()
  await expect(page).toHaveURL(/status=submitted/)
  await expect(table.getByRole('cell', { name: title })).toBeVisible()
  await page.getByRole('button', { name: /^Approved/ }).click()
  await expect(page).toHaveURL(/status=approved/)
  await expect(table.getByRole('cell', { name: title })).toHaveCount(0)
  await page.getByRole('button', { name: /^All/ }).click()
  await page.getByRole('searchbox', { name: /Search requests/ }).fill(title)
  await expect(table.getByRole('row')).toHaveCount(2) // the header and the one match
  await expect(table.getByText('Urgent')).toBeVisible() // High and Urgent show in the list

  // A shared link keeps the filters
  await page.goto(`/requests?q=${encodeURIComponent(title)}&status=submitted`)
  await expect(page.getByRole('searchbox', { name: /Search requests/ })).toHaveValue(title)
  await expect(table.getByRole('cell', { name: title })).toBeVisible()
})

test('On a phone the requests are cards and the actions sit under the title @phone @REQ-8 @REQ-11', async ({ watched: page }) => {
  const title = unique('Phone request')
  await logIn(page, 'client.a1@example.org')
  await submitRequest(page, title, { category: 'Communications' })
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Edit' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel request' })).toBeVisible()
  await checkA11y(page, '/requests/:id (phone)')

  await page.goto('/requests')
  const list = page.getByRole('list', { name: 'Requests' })
  await expect(list.getByRole('link', { name: title })).toBeVisible()
  await expect(page.getByRole('table')).toHaveCount(0)
  await checkA11y(page, '/requests (phone)')

  await list.getByRole('link', { name: title }).click()
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
  const overflows = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(overflows).toBe(false)
})
