import { logIn, unique } from './requestFlows'
import { checkA11y, expect, test } from './support'

/*
  Checklist templates, W10 (PRD VIS-8; AFD /admin/checklists): an admin makes a template, saves
  it again as a new version, reads an older one and saves it as the newest. Each run uses its own
  station type, so runs do not meet on the one-active-template-per-type rule.
*/

test('An admin makes a template, saves new versions and reads an older one @VIS-8', async ({ watched: page }) => {
  const name = unique('Site visit')
  const type = unique('TYPE').replaceAll(/\W/g, '-')
  await logIn(page, 'admin@example.org')
  await page.goto('/admin/checklists')
  await expect(page.getByRole('heading', { level: 1, name: 'Checklist templates' })).toBeVisible()
  await page.getByRole('link', { name: 'New template' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'New template' })).toBeVisible()

  // Nothing to save yet: no name, no station type
  const save = page.getByRole('button', { name: 'Save template' })
  await expect(save).toBeDisabled()
  await page.getByLabel('Name', { exact: true }).fill(name)
  await page.getByRole('combobox', { name: 'Station type' }).fill(type)
  await page.getByLabel('Item 1', { exact: true }).fill('Mast: guy wires, corrosion')
  await page.getByRole('button', { name: 'Add item' }).click()
  await page.getByLabel('Item 2', { exact: true }).fill('Battery voltage')
  await page.getByLabel('Help for item 2').fill('Note it')
  await checkA11y(page, '/admin/checklists/new')
  await expect(save).toBeEnabled()
  await save.click()
  await expect(page.getByText('Saved as version 1.')).toBeVisible()
  await expect(page).toHaveURL(/\/admin\/checklists\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
  await expect(page.getByText(/Version 1, saved/)).toBeVisible()
  await expect(page.getByRole('link', { name: new RegExp(name) })).toBeVisible() // in the pane

  // Move the second item up with the keyboard, then save version 2
  const saveVersion = page.getByRole('button', { name: 'Save version' })
  await expect(saveVersion).toBeDisabled()
  await page.getByRole('button', { name: /^Item 2\./ }).focus()
  await page.keyboard.press('ArrowUp')
  await expect(page.getByLabel('Item 1', { exact: true })).toHaveValue('Battery voltage')
  await expect(page.getByText('Changes not saved')).toBeVisible()
  await expect(page.getByText('Saving writes version 2.')).toBeVisible()
  await saveVersion.click()
  await expect(page.getByText('Saved as version 2.')).toBeVisible()
  await expect(page.getByText(/Version 2, saved/)).toBeVisible()
  await expect(page.getByText('Changes not saved')).toHaveCount(0)

  // Read version 1: read only, with a way back, and save it as the newest
  await page.getByRole('button', { name: 'Versions' }).click()
  await page.getByRole('list', { name: 'Versions' }).getByText('Version 1', { exact: true }).click()
  await expect(page.getByText('You are reading version 1.')).toBeVisible()
  await expect(page.getByLabel('Item 1', { exact: true })).toHaveValue('Mast: guy wires, corrosion')
  await expect(page.getByLabel('Item 1', { exact: true })).toHaveAttribute('readonly', '')
  await checkA11y(page, '/admin/checklists/:id?version=1')
  await page.getByRole('button', { name: 'Save as version 3' }).click()
  await expect(page.getByText('Saved as version 3.')).toBeVisible()
  await expect(page.getByLabel('Item 1', { exact: true })).toHaveValue('Mast: guy wires, corrosion')
  await expect(page).not.toHaveURL(/version=/)
})

test('Leaving with unsaved changes asks first, and a second template for the same type is refused @VIS-8', async ({ watched: page }) => {
  const type = unique('DUP').replaceAll(/\W/g, '-')
  await logIn(page, 'admin@example.org')
  await page.goto('/admin/checklists/new')
  await page.getByLabel('Name', { exact: true }).fill(unique('First'))
  await page.getByRole('combobox', { name: 'Station type' }).fill(type)
  await page.getByLabel('Item 1', { exact: true }).fill('One thing')
  await page.getByRole('button', { name: 'Save template' }).click()
  await expect(page.getByText('Saved as version 1.')).toBeVisible()

  await page.getByRole('link', { name: 'New template' }).click()
  await page.getByLabel('Name', { exact: true }).fill(unique('Second'))
  await page.getByRole('combobox', { name: 'Station type' }).fill(type)
  await page.getByLabel('Item 1', { exact: true }).fill('Another thing')
  await page.getByRole('button', { name: 'Save template' }).click()
  await expect(page.getByText(/already an active template/)).toBeVisible()

  // Typed things are not thrown away by a click on another template
  await page.getByRole('link', { name: /First/ }).first().click()
  const dialog = page.getByRole('alertdialog', { name: 'Leave without saving?' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Keep editing' }).click()
  await expect(page.getByLabel('Item 1', { exact: true })).toHaveValue('Another thing')
  await page.getByRole('link', { name: /First/ }).first().click()
  await dialog.getByRole('button', { name: 'Leave' }).click()
  await expect(page).toHaveURL(/\/admin\/checklists\/[0-9a-f-]{36}$/)
})

test('A technician cannot open the checklist templates @VIS-8 @NFR-6', async ({ watched: page }) => {
  await logIn(page, 'tech1@example.org')
  await page.goto('/admin/checklists')
  await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible()
})
