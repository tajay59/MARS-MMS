import type { Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { expect, seedPassword, submitPaced } from './support'

// Steps the requests journeys share (requests.spec.ts, staffing.spec.ts).

export async function logIn (page: Page, email: string): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)
}

export const unique = (what: string): string => `${what} ${randomUUID().slice(0, 8)}`

/** Fills the new-request form as a client would and submits it; returns the page's URL path. */
export async function submitRequest (page: Page, title: string, options: { category?: string, priority?: string } = {}): Promise<string> {
  await page.goto('/requests/new')
  await expect(page.getByRole('heading', { level: 1, name: 'New request' })).toBeVisible()
  await page.getByLabel('Which stations is this about?').fill('JM-KIN-001')
  await page.getByRole('option', { name: /JM-KIN-001/ }).click()
  await expect(page.getByRole('list', { name: 'Chosen stations' }).getByText('JM-KIN-001')).toBeVisible()
  await page.getByLabel('Title', { exact: true }).fill(title)
  await page.getByLabel('Description', { exact: true }).fill('The gauge stopped sending readings on Saturday.')
  if (options.category) {
    await page.getByRole('button', { name: options.category, exact: true }).click()
  }
  if (options.priority) {
    await page.getByRole('button', { name: options.priority, exact: true }).click()
  }
  await page.getByRole('button', { name: 'Submit request' }).click()
  await expect(page).toHaveURL(/\/requests\/[\da-f-]{36}$/)
  return new URL(page.url()).pathname
}
