import { logIn, submitRequest, unique } from './requestFlows'
import { checkA11y, expect, mailTo, test } from './support'

/*
  Email preferences and the emails that follow notifications, W9 slice 4 (PRD NOT-1, NOT-4;
  Appendix B), on the demo seed with Mailpit and the real platform consumer and sender.
*/

test('Each role sees only the emails it can get, and a choice sticks @NOT-4', async ({ watched: page }) => {
  await logIn(page, 'admin@example.org')
  await page.goto('/profile')
  const section = page.getByRole('region', { name: 'My profile' })
  await expect(section.getByRole('switch', { name: 'A client submits a request' })).toBeVisible()
  await expect(section.getByRole('switch', { name: 'Weekly digest of calibrations due' })).toBeChecked()
  await expect(section.getByLabel('Account emails')).toBeDisabled()
  await checkA11y(page, '/profile (email preferences)')

  const digest = section.getByRole('switch', { name: 'Weekly digest of calibrations due' })
  await digest.uncheck({ force: true })
  await expect(page.getByText('Saved', { exact: true })).toBeVisible()
  await page.reload()
  await expect(digest).not.toBeChecked()
  await digest.check({ force: true }) // put it back for the next run
  await expect(page.getByText('Saved', { exact: true })).toBeVisible()
})

test('A client sees their two and none of the staff ones @NOT-4', async ({ watched: page }) => {
  await logIn(page, 'client.a1@example.org')
  await page.goto('/profile')
  await expect(page.getByRole('switch', { name: 'Your request is approved or denied' })).toBeChecked()
  await expect(page.getByRole('switch', { name: 'A request is cancelled' })).toBeChecked()
  await expect(page.getByRole('switch', { name: 'A client submits a request' })).toHaveCount(0)
  await expect(page.getByRole('switch', { name: 'Weekly digest of calibrations due' })).toHaveCount(0)
})

test('A new request is emailed to the admins, with a link to it @NOT-1', async ({ watched: page }) => {
  const title = unique('Mailbox check')
  await logIn(page, 'client.a1@example.org')
  await submitRequest(page, title)
  const mail = await mailTo('admin@example.org', title)
  expect(mail.Text).toContain('Open the request')
  expect(mail.Text).toMatch(/https:\/\/[^/\s]+\/requests\/[\da-f-]{36}/)
})
