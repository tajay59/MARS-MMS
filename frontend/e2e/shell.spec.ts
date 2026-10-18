import { expect, seedPassword, submitPaced, test } from './support'

/*
  The app shell's rail (decision W4-9, W4-10): its CSS tooltips must follow the pointer, so at most
  one is open at a time, even after a fast sweep down the rail.
*/

test('A fast sweep down the rail leaves only the hovered tooltip open', async ({ watched: page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('admin@example.org')
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)

  const buttons = page.locator('[data-rail-button]')
  const count = await buttons.count()
  expect(count).toBeGreaterThan(2)

  // No pause between buttons: each leave lands inside the next tip's show delay
  for (let round = 0; round < 3; round++) {
    for (let index = 0; index < count; index++) {
      const box = await buttons.nth(index).boundingBox()
      await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
    }
  }
  await page.waitForTimeout(600)

  const open = await page.locator('[data-rail-button] > span[aria-hidden="true"]').evaluateAll(tips =>
    tips.filter(tip => getComputedStyle(tip).visibility !== 'hidden').length)
  expect(open).toBe(1)

  // Leaving the rail closes the last one too
  await page.mouse.move(600, 400)
  await expect.poll(() => page.locator('[data-rail-button] > span[aria-hidden="true"]').evaluateAll(tips =>
    tips.filter(tip => getComputedStyle(tip).visibility !== 'hidden').length)).toBe(0)
})
