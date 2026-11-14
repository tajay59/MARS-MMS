import { logIn } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  The W13 storage check (risk R4; pwa skill testing.md §5) and the diagnostics block on /sync:
  test files go into the phone's store, survive a reload, and read back with the same fingerprint.
  The real check, 50 photos and 3 videos across a phone restart, is done by hand on a phone.
*/

test('Test files are kept across a reload and read back unchanged @R4 @OFF-3', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/sync')
  const diagnostics = page.getByRole('region', { name: 'This phone', exact: true })
  await expect(diagnostics).toBeVisible()
  await expect(diagnostics.getByText(/version \d/)).toBeVisible()
  await expect(diagnostics.getByText('Offline PIN')).toBeVisible()
  await expect(diagnostics.getByText('Device ID')).toBeVisible()
  await checkA11y(page, '/sync (this phone)')

  await diagnostics.getByRole('link', { name: 'Storage check' }).click()
  await expect(page.getByRole('heading', { name: 'Storage check' })).toBeVisible()

  // Three photos and a video of a few hundred kilobytes each
  const file = (name: string, mimeType: string, size: number) => ({ name, mimeType, buffer: Buffer.alloc(size, name.length) })
  await page.getByTestId('storage-check-files').setInputFiles([
    file('a.jpg', 'image/jpeg', 300_000),
    file('b.jpg', 'image/jpeg', 200_000),
    file('c.jpg', 'image/jpeg', 100_000),
    file('clip.mp4', 'video/mp4', 900_000),
  ])
  const held = page.getByRole('region', { name: 'Stored on this phone', exact: true })
  await expect(held.locator('dd').nth(0)).toHaveText('3', { timeout: 30_000 })
  await expect(held.locator('dd').nth(1)).toHaveText('1')
  await checkA11y(page, '/sync/storage-check')

  await page.getByRole('button', { name: 'Verify' }).click()
  await expect(page.getByText('All 4 match')).toBeVisible()

  // "Restart": the page and the app start again, the files are still there and still match
  await page.reload()
  await expect(page.getByRole('region', { name: 'Stored on this phone', exact: true }).locator('dd').nth(0)).toHaveText('3')
  await page.getByRole('button', { name: 'Verify' }).click()
  await expect(page.getByText('All 4 match')).toBeVisible()

  // Taking the test files away leaves nothing behind
  await page.getByRole('button', { name: 'Remove test files' }).click()
  await expect(page.getByRole('region', { name: 'Stored on this phone', exact: true }).locator('dd').nth(0)).toHaveText('0')
  await expect(page.getByRole('button', { name: 'Verify' })).toBeDisabled()
})
