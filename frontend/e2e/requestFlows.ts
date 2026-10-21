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

/** A small, valid PDF: media checks the first bytes against the name. */
export function pdf (text: string): Buffer {
  return Buffer.from(`%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n% ${text}\ntrailer<</Root 1 0 R>>\n%%EOF\n`)
}
