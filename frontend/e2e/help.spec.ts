import { checkA11y, expect, test } from './support'

/*
  The client guide (W23-5): public, linked from the Log in page and a client's invitation email.
  Needs no seed users, so it is part of the staging smoke run.
*/

test('the client guide opens from the Log in page, signed out @smoke @W23-5', async ({ watched: page }) => {
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
  await page.goto('/login')
  await page.getByRole('link', { name: 'Read the client guide' }).click()
  await expect(page).toHaveURL(/\/help\/client$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Looking after your weather stations with us' })).toBeVisible()
  await expect(page).toHaveTitle(/^Client guide/)

  // Every request status is explained, with its chip
  const table = page.getByRole('table')
  for (const status of ['Submitted', 'Client Review', 'Closed', 'Cancelled']) {
    await expect(table.getByText(status, { exact: true })).toBeVisible()
  }

  // The contents on the dark side go to a section and mark it as the one being read
  const contents = page.getByRole('navigation', { name: 'Guide contents' })
  await contents.getByRole('link', { name: 'Review and sign off' }).click()
  await expect(page).toHaveURL(/#review$/)
  await expect(page.getByRole('heading', { level: 2, name: /Review and sign off/ })).toBeInViewport()
  await expect(contents.getByRole('link', { name: 'Review and sign off' })).toHaveAttribute('aria-current', 'location')

  await checkA11y(page, '/help/client')
  await expect(page.getByRole('link', { name: 'Log in' })).toBeVisible()
})

test('the client guide on a phone: contents in a disclosure @smoke @phone @W23-5', async ({ watched: page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/help/client#stations')
  await expect(page.getByRole('heading', { level: 2, name: /Your stations/ })).toBeInViewport()

  await page.getByText('Contents', { exact: true }).click()
  await page.getByRole('link', { name: 'Add your own report' }).click()
  await expect(page.getByRole('heading', { level: 2, name: /Add your own report/ })).toBeInViewport()
  const noSideScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(noSideScroll).toBe(true)
})
