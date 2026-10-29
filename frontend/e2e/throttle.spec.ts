import { expect, test } from './support'

// The gateway limits the public auth requests to 10 a minute (TRD §2.1). A person who meets the
// limit is told to wait, not that the server failed, and it is safe to send again. The limit is
// stubbed here so the journey does not depend on how many requests came before it.

const THROTTLED = {
  status: 429,
  contentType: 'application/problem+json',
  body: JSON.stringify({ type: 'about:blank', title: 'Too many requests', status: 429, code: 'rate_limited', detail: 'Too many requests' }),
}

test('A throttled reset link request says to wait @AUTH-8', async ({ watched: page }) => {
  await page.route('**/api/v1/auth/password-reset/request', route => route.fulfill(THROTTLED))
  await page.goto('/forgot-password')
  await page.getByLabel('Email').fill('someone@example.org')
  await page.getByRole('button', { name: 'Send link', exact: true }).click()
  await expect(page.getByText('Too many attempts. Wait a minute, then try again.')).toBeVisible()
  await expect(page.getByText('Something went wrong on our side')).toHaveCount(0)
})

test('A throttled new password says to wait and keeps what was typed @AUTH-8', async ({ watched: page }) => {
  await page.route('**/api/v1/auth/password-reset/confirm', route => route.fulfill(THROTTLED))
  await page.goto('/reset-password/not-a-real-token')
  await page.getByLabel('New password').fill('a long and fresh password')
  await page.getByLabel('Type it again').fill('a long and fresh password')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByText('Too many attempts. Wait a minute, then try again.')).toBeVisible()
  await expect(page.getByLabel('New password')).toHaveValue('a long and fresh password')
})
