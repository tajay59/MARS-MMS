import type { Page } from '@playwright/test'
import { checkA11y, expect, seedPassword, submitPaced, test } from './support'

/*
  Admin › Organizations (PRD ORG-1, ORG-4), from the approved "AWS-MMS Organizations screen"
  mock-up: an admin adds an organization, finds it, edits it, is told when a name is taken,
  deactivates it and reactivates it. Each run makes its own organization (names are unique).
*/

const ADMIN = 'admin@example.org'

test.describe.configure({ mode: 'serial' })
test.setTimeout(120_000)

async function signIn (page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ADMIN)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)
}

test('An admin adds, edits, deactivates and reactivates an organization @ORG-1 @ORG-4', async ({ watched: page }) => {
  const name = `E2E Water Board ${Date.now().toString(36)}`
  const drawer = page.getByRole('complementary', { name: /./ }).filter({ has: page.getByRole('button', { name: 'Close' }) })

  await signIn(page)
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: /^Admin/ }).click()
  await page.getByRole('navigation', { name: 'Admin pages' }).getByRole('link', { name: 'Organizations' }).click()
  await expect(page).toHaveURL(/\/admin\/organizations$/)
  await expect(page.getByRole('heading', { name: 'Organizations', level: 1 })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Active/ })).toHaveAttribute('aria-pressed', 'true')
  await checkA11y(page, '/admin/organizations')

  // New: the name and the country are needed
  await page.getByRole('button', { name: 'New organization' }).click()
  await expect(drawer.getByRole('heading', { name: 'New organization' })).toBeVisible()
  await drawer.getByRole('button', { name: 'Add organization' }).click()
  await expect(drawer.getByText('Enter the organization’s name')).toBeVisible()
  await expect(drawer.getByText('Choose the country')).toBeVisible()
  await checkA11y(page, '/admin/organizations (new)')

  await drawer.getByLabel('Name', { exact: true }).fill(name)
  await drawer.getByLabel('Short name (optional)').fill('EWB')
  await drawer.getByLabel('Country').fill('Jamai')
  await page.getByRole('option', { name: 'Jamaica' }).click()
  await drawer.getByLabel('Contact email (optional)').fill('office@example.org')
  await drawer.getByRole('button', { name: 'Add organization' }).click()
  await expect(page.getByText(`${name} added.`)).toBeVisible()

  // Found by its short name; its stations are one link away
  await page.getByLabel('Search organizations').fill('ewb')
  const row = page.getByRole('row').filter({ hasText: name })
  await expect(row).toHaveCount(1)
  await expect(row.getByText('Jamaica')).toBeVisible()
  await expect(row.getByRole('link', { name: `Stations of ${name}` })).toHaveAttribute('href', /\/stations\?org=/)

  // Edit: a phone number; the same name as another organization is refused on the field
  await row.getByRole('button', { name }).click()
  await expect(drawer.getByRole('heading', { name })).toBeVisible()
  await expect(drawer.getByText('Active · No people yet')).toBeVisible()
  await drawer.getByLabel('Phone (optional)').fill('+1 876 555 0100')
  await drawer.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText(`${name} saved.`)).toBeVisible()

  await page.getByRole('button', { name: 'New organization' }).click()
  await drawer.getByLabel('Name', { exact: true }).fill(name)
  await drawer.getByLabel('Country').fill('Jamai')
  await page.getByRole('option', { name: 'Jamaica' }).click()
  await drawer.getByRole('button', { name: 'Add organization' }).click()
  await expect(drawer.getByText('An organization with this name already exists')).toBeVisible()

  // Closing with something typed asks first
  await drawer.getByRole('button', { name: 'Cancel' }).click()
  const leave = page.getByRole('alertdialog', { name: 'Leave without saving?' })
  await leave.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByLabel('Name', { exact: true })).toHaveValue(name)
  await drawer.getByRole('button', { name: 'Cancel' }).click()
  await leave.getByRole('button', { name: 'Leave' }).click()
  await expect(leave).toBeHidden()

  // Deactivate: the danger button only in the final confirm, which names it
  await row.getByRole('button', { name }).click()
  await drawer.getByRole('button', { name: `Deactivate ${name}` }).click()
  const confirm = page.getByRole('dialog', { name: `Deactivate ${name}?` })
  await expect(confirm.getByText('Nobody can sign in for it until you reactivate it.')).toBeVisible()
  await checkA11y(page, '/admin/organizations (deactivate)')
  await confirm.getByRole('button', { name: 'Deactivate', exact: true }).click()
  await expect(page.getByText(`${name} is deactivated. Its people are signed out.`)).toBeVisible()
  await expect(row).toHaveCount(0)

  // Under Inactive, in dark too, then back to active
  await page.getByRole('button', { name: /^Inactive/ }).click()
  await expect(page).toHaveURL(/status=inactive/)
  await expect(row.getByText('Inactive')).toBeVisible()
  await page.emulateMedia({ colorScheme: 'dark' })
  await checkA11y(page, '/admin/organizations?status=inactive (dark)')
  await page.emulateMedia({ colorScheme: 'light' })

  await row.getByRole('button', { name }).click()
  await drawer.getByRole('button', { name: `Reactivate ${name}` }).click()
  await expect(page.getByText(`${name} is active again.`)).toBeVisible()
  await expect(row).toHaveCount(0)
})

test('On a phone the rows are cards and the form fills the screen @ORG-1 @phone', async ({ watched: page }) => {
  await signIn(page)
  await page.goto('/admin/organizations')
  await expect(page.getByRole('heading', { name: 'Organizations', level: 1 })).toBeVisible()
  await expect(page.getByRole('table')).toHaveCount(0)
  await page.getByRole('button', { name: 'New organization' }).click()
  await expect(page.getByRole('heading', { name: 'New organization' })).toBeVisible()
  await checkA11y(page, '/admin/organizations (phone, new)')
})
