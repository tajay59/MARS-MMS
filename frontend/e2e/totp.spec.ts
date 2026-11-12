import type { Page } from '@playwright/test'
import { createHmac } from 'node:crypto'
import { checkA11y, expect, seedPassword, submitPaced, test } from './support'

/*
  Two-step sign-in (W22; PRD AUTH-14; AFD J2), through the real stack: the code step, a wrong code,
  a replayed code, opting in as a technician, recovery codes, and an admin resetting a lost phone.
  The codes are computed here from the secret on screen (RFC 6238), at the moment they are typed.
  `admin_mfa` has the public test secret from mms_common.testing.seed (the seed command sets it).
*/

const MFA_ADMIN = 'admin.mfa@example.org'
const MFA_SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
const ADMIN = 'admin@example.org'
const TECH = 'tech2@example.org'
const STEP_MS = 30_000

function base32 (text: string): Buffer {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const ch of text.replaceAll(/[\s=]/g, '').toUpperCase()) {
    bits += alphabet.indexOf(ch).toString(2).padStart(5, '0')
  }
  const bytes: number[] = []
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(Number.parseInt(bits.slice(i, i + 8), 2))
  }
  return Buffer.from(bytes)
}

/** RFC 6238: HMAC-SHA1, 6 digits, 30 s steps; `shift` steps from now. */
function totp (secret: string, shift = 0): string {
  const counter = Math.floor(Date.now() / STEP_MS) + shift
  const message = Buffer.alloc(8)
  message.writeBigUInt64BE(BigInt(counter))
  const mac = createHmac('sha1', base32(secret)).update(message).digest()
  const offset = mac.at(-1)! & 0x0F
  const number = (mac.readUInt32BE(offset) & 0x7F_FF_FF_FF) % 1_000_000
  return String(number).padStart(6, '0')
}

/** Waits for the next 30-second step, so a code used a moment ago is not a replay. */
async function nextStep (page: Page): Promise<void> {
  await page.waitForTimeout(STEP_MS - (Date.now() % STEP_MS) + 1500)
}

async function password (page: Page, email: string): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
}

async function type (page: Page, label: string, digits: string): Promise<void> {
  // One real input sits behind the six boxes, which cover it: focus it, as a tap on a box does
  await page.getByLabel(label).first().focus()
  await page.keyboard.type(digits)
}

async function logout (page: Page): Promise<void> {
  await page.getByRole('button', { name: /Account menu/ }).click()
  await page.getByRole('menuitem', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login$/)
}

test.describe.configure({ mode: 'serial' })
test.setTimeout(150_000)

test('an admin with two-step sign-in logs in with a code, and a code works once @AUTH-14', async ({ watched: page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await password(page, MFA_ADMIN)

  // The password alone is not a session: the code step comes next
  await expect(page.getByRole('heading', { name: 'Enter your code' })).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
  await checkA11y(page, '/login (code step)')

  // A wrong code says only that it is incorrect, and the step stays open
  await type(page, '6-digit code', totp(MFA_SECRET, 5))
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page.getByText('That code is incorrect. Enter the current code from your app.')).toBeVisible()

  await type(page, '6-digit code', totp(MFA_SECRET))
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  // This admin has two-step sign-in on: no setup banner
  await expect(page.getByText(/Set up two-step sign-in/)).toHaveCount(0)
  const code = totp(MFA_SECRET)

  // The same code again, in the same 30 seconds, is a replay
  await logout(page)
  await password(page, MFA_ADMIN)
  await type(page, '6-digit code', code)
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page.getByText('That code is incorrect. Enter the current code from your app.')).toBeVisible()
  await nextStep(page)
  await type(page, '6-digit code', totp(MFA_SECRET))
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
})

test('a technician turns it on, uses a recovery code, makes new ones and turns it off @AUTH-14', async ({ watched: page }) => {
  await password(page, TECH)
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/profile')
  await expect(page.getByRole('heading', { name: 'Two-step sign-in' })).toBeVisible()
  await page.getByRole('button', { name: 'Turn on' }).click()

  // 1 · the password
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Set up two-step sign-in' })).toBeVisible()
  await dialog.getByLabel('Password', { exact: true }).fill(seedPassword())
  await dialog.getByRole('button', { name: 'Continue' }).click()

  // 2 · the QR code and the typed key
  await expect(dialog.getByRole('heading', { name: 'Scan the QR code' })).toBeVisible()
  await expect(dialog.getByRole('img', { name: /QR code for MARS-MMS/ })).toBeVisible()
  const key = ((await dialog.locator('code').textContent()) ?? '').replaceAll(/\s/g, '')
  expect(key).toMatch(/^[A-Z2-7]{32}$/)
  await dialog.getByRole('button', { name: 'Continue' }).click()

  // 3 · a code that proves the app has the key
  await type(page, '6-digit code', totp(key, 3))
  await dialog.getByRole('button', { name: 'Turn on' }).click()
  await expect(dialog.getByText('That code is incorrect.')).toBeVisible()
  await type(page, '6-digit code', totp(key))
  await dialog.getByRole('button', { name: 'Turn on' }).click()

  // Recovery codes, shown once; Done waits for the tick
  await expect(dialog.getByRole('heading', { name: 'Save your recovery codes' })).toBeVisible()
  const codes = await dialog.getByRole('list', { name: 'Recovery codes' }).getByRole('listitem').allInnerTexts()
  expect(codes).toHaveLength(10)
  expect(codes[0]).toMatch(/^[A-Z2-7]{5}-[A-Z2-7]{5}$/)
  await expect(dialog.getByRole('button', { name: 'Done' })).toBeDisabled()
  await dialog.getByLabel('I’ve saved my recovery codes').check()
  await dialog.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByText('Two-step sign-in is on.')).toBeVisible()
  await expect(page.getByText('10', { exact: true })).toBeVisible()
  await checkA11y(page, '/profile (two-step on)')

  // Log in again: the password, then a recovery code from the sheet
  await logout(page)
  await password(page, TECH)
  await expect(page.getByRole('heading', { name: 'Enter your code' })).toBeVisible()
  await page.getByRole('button', { name: 'Use a recovery code' }).click()
  await expect(page.getByRole('heading', { name: 'Use a recovery code' })).toBeVisible()
  await page.getByLabel('Recovery code').fill(codes[0]!)
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByText('You used a recovery code. 9 are left.')).toBeVisible()
  await page.getByRole('button', { name: 'Dismiss' }).click()

  // The same recovery code is spent
  await logout(page)
  await password(page, TECH)
  await page.getByRole('button', { name: 'Use a recovery code' }).click()
  await page.getByLabel('Recovery code').fill(codes[0]!)
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page.getByText('That recovery code is incorrect or already used.')).toBeVisible()
  await page.getByLabel('Recovery code').fill(codes[1]!)
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.getByRole('button', { name: 'Dismiss' }).click()

  // New recovery codes ask for the password and a code; the old ones stop working
  await page.goto('/profile')
  await page.getByRole('button', { name: 'Make new recovery codes' }).click()
  const proof = page.getByRole('dialog')
  await proof.getByLabel('Password', { exact: true }).fill(seedPassword())
  await proof.getByRole('button', { name: 'Use a recovery code instead' }).click()
  await proof.getByLabel('Recovery code').fill(codes[2]!)
  await proof.getByRole('button', { name: 'Make new codes' }).click()
  await expect(proof.getByRole('heading', { name: 'Save your new recovery codes' })).toBeVisible()
  const fresh = await proof.getByRole('list', { name: 'Recovery codes' }).getByRole('listitem').allInnerTexts()
  expect(fresh).toHaveLength(10)
  await proof.getByLabel('I’ve saved my recovery codes').check()
  await proof.getByRole('button', { name: 'Done' }).click()

  // Turn it off with one of the new codes: a technician may; the dialog says what follows
  await page.getByRole('button', { name: 'Turn off' }).click()
  const off = page.getByRole('dialog')
  await expect(off.getByRole('heading', { name: 'Turn off two-step sign-in?' })).toBeVisible()
  await off.getByLabel('Password', { exact: true }).fill(seedPassword())
  await off.getByRole('button', { name: 'Use a recovery code instead' }).click()
  await off.getByLabel('Recovery code').fill(fresh[0]!)
  await off.getByRole('button', { name: 'Turn off' }).click()
  await expect(page.getByRole('button', { name: 'Turn on' })).toBeVisible()
  await expect(page.getByText('Off', { exact: true })).toBeVisible()
})

test('an admin without it sees the setup banner on every page and the card on My profile @AUTH-14', async ({ watched: page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await password(page, ADMIN)
  await expect(page).toHaveURL(/\/dashboard$/)
  // Inside the 7 days: a banner with the date, on the dashboard and on other pages
  const banner = page.getByText(/Set up two-step sign-in by \d{1,2} \w{3} \d{4}\./)
  await expect(banner).toBeVisible()
  await checkA11y(page, '/dashboard (setup banner)')
  await page.goto('/admin/users')
  await expect(banner).toBeVisible()

  await page.getByRole('link', { name: 'Set up now' }).click()
  await expect(page).toHaveURL(/\/profile#two-step$/)
  await expect(page.getByRole('heading', { name: 'Two-step sign-in' })).toBeVisible()
  await expect(page.getByText('Not set up', { exact: true })).toBeVisible()
  await expect(page.getByText('Required for admins.')).toBeVisible()
  // An admin can't turn it off: there is nothing to turn off yet, and later no button
  await checkA11y(page, '/profile (admin, two-step not set up)')
  await expect(page.getByRole('button', { name: 'Set up two-step sign-in' })).toBeVisible()
})

test('another admin resets a lost phone, and they log in with the password again @AUTH-14', async ({ watched: page }) => {
  await password(page, ADMIN)
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/admin/users')
  const reset = page.getByRole('button', { name: 'Reset two-step sign-in for Admin MFA' })
  await expect(reset).toBeVisible()
  // Not offered for yourself
  await expect(page.getByRole('button', { name: 'Reset two-step sign-in for Admin', exact: true })).toHaveCount(0)
  await checkA11y(page, '/admin/users (two-step column)')
  await reset.click()

  const dialog = page.getByRole('alertdialog').or(page.getByRole('dialog'))
  await expect(dialog.getByRole('heading', { name: 'Reset two-step sign-in for Admin MFA?' })).toBeVisible()
  await expect(dialog.getByText('They have 7 days to set it up again before it is required.')).toBeVisible()
  await dialog.getByRole('button', { name: 'Reset two-step sign-in' }).click()
  await expect(page.getByText(/Two-step sign-in reset for Admin MFA/)).toBeVisible()
  await expect(reset).toHaveCount(0)

  // Their sessions ended and the code step is gone: the password signs them in, with the nudge
  await logout(page)
  await password(page, MFA_ADMIN)
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByText(/Set up two-step sign-in by/)).toBeVisible()
})
