import { randomUUID } from 'node:crypto'
import { checkA11y, expect, linkIn, mailTo, seedPassword, submitPaced, test } from './support'

/*
  J1 (register and get approved) and J2 (log in and reset a password), AFD §4, through the real
  stack: Nginx, auth, Kafka, the platform consumer and Mailpit. TP: auth.spec.ts, Phase 1 smoke.
*/

const ADMIN = 'admin@example.org'

test.describe.configure({ mode: 'serial' })

const run = randomUUID().slice(0, 8)
const client = {
  name: `Maria Lopez ${run}`,
  email: `j1-${run}@example.org`,
  password: `field season ${randomUUID()}`, // never on a breached list
}
let resetPassword = ''

test('J1: a client registers, an admin approves, the client logs in @J1 @AUTH-1 @AUTH-2 @AUTH-3', async ({ watched: page, browser }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/login')
  await checkA11y(page, '/login')
  await page.getByRole('link', { name: 'Create an account' }).click()
  await expect(page).toHaveURL(/\/register$/)
  await checkA11y(page, '/register')

  await page.getByLabel('Your name').fill(client.name)
  await page.getByLabel('Email').fill(client.email)
  await page.getByLabel('Your organization').fill('Organization A')
  await page.getByLabel('Password', { exact: true }).fill('too short')
  await page.getByRole('button', { name: 'Register' }).click()
  await expect(page.getByText('Use at least 10 characters')).toBeVisible()

  await page.getByLabel('Password', { exact: true }).fill(client.password)
  await submitPaced(page, 'Register')
  await expect(page).toHaveURL(/\/register\/pending$/)
  await expect(page.getByRole('heading', { name: 'Waiting for approval' })).toBeVisible()
  await expect(page.getByText(client.email)).toBeVisible()
  await checkA11y(page, '/register/pending')

  // A pending account can't log in yet: the login sends it back to the waiting page.
  await page.getByRole('link', { name: 'Back to log in' }).click()
  await page.getByLabel('Email').fill(client.email)
  await page.getByLabel('Password', { exact: true }).fill(client.password)
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/register\/pending$/)

  // The admin approves it, linked to the organization that matches what was typed.
  const adminContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const admin = await adminContext.newPage()
  await admin.goto('/login')
  await admin.getByLabel('Email').fill(ADMIN)
  await admin.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(admin, 'Log in')
  await expect(admin).toHaveURL(/\/dashboard$/)
  await admin.getByRole('link', { name: /Registrations pending/ }).click()
  await expect(admin).toHaveURL(/\/admin\/registrations$/)
  await checkA11y(admin, '/admin/registrations')
  await admin.getByRole('button', { name: client.name, exact: true }).click()
  await expect(admin.getByRole('radio', { name: /Organization A/ })).toBeChecked()
  await admin.getByRole('button', { name: `Approve ${client.name}` }).click()
  await expect(admin.getByText(`${client.name} is approved`)).toBeVisible()
  await expect(admin.getByRole('button', { name: client.name, exact: true })).toHaveCount(0)
  await adminContext.close()

  // The approval email links to /login (J1 step 5).
  const approved = await mailTo(client.email, 'account is approved')
  await page.goto(linkIn(approved.Text, '/login'))
  await page.getByLabel('Email').fill(client.email)
  await page.getByLabel('Password', { exact: true }).fill(client.password)
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('link', { name: 'Report a problem' })).toBeVisible()
  await checkA11y(page, '/dashboard (client)')
})

test('J2: forgot password, reset by email, log in with the new one @J2 @AUTH-8', async ({ watched: page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/login')
  await page.getByRole('link', { name: 'Forgot password?' }).click()
  await expect(page).toHaveURL(/\/forgot-password$/)
  await checkA11y(page, '/forgot-password')
  await page.getByLabel('Email').fill(client.email)
  await submitPaced(page, 'Send link')
  await expect(page.getByText('If that email is registered, a link is on its way.')).toBeVisible()

  const email = await mailTo(client.email, 'Reset your')
  const resetPath = linkIn(email.Text, '/reset-password/')
  await page.goto(resetPath)
  await expect(page.getByRole('heading', { name: 'Set a new password' })).toBeVisible()
  await checkA11y(page, '/reset-password/:token')

  resetPassword = `new season ${randomUUID()}`
  await page.getByLabel('New password').fill(resetPassword)
  await page.getByLabel('Type it again').fill(resetPassword)
  await submitPaced(page, 'Save')
  await expect(page).toHaveURL(/\/login\?notice=password-changed$/)
  await expect(page.getByText('Password changed. Log in with your new password.')).toBeVisible()

  // The old password no longer works; the new one does, and lands on the dashboard.
  await page.getByLabel('Email').fill(client.email)
  await page.getByLabel('Password', { exact: true }).fill(client.password)
  await submitPaced(page, 'Log in')
  await expect(page.getByText('Email or password is incorrect.')).toBeVisible()
  await page.getByLabel('Password', { exact: true }).fill(resetPassword)
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/dashboard$/)

  // The link works once (AUTH-8).
  await page.goto(resetPath)
  await page.getByLabel('New password').fill(`again ${randomUUID()}`)
  await page.getByLabel('Type it again').fill(await page.getByLabel('New password').inputValue())
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('This link has expired.')).toBeVisible()
})

test('J2: a deep link survives login, and a reload keeps the session @J2 @AUTH-7', async ({ watched: page }) => {
  await page.goto('/profile')
  await expect(page).toHaveURL(/\/login\?next=(%2F|\/)profile$/)
  await page.getByLabel('Email').fill(client.email)
  await page.getByLabel('Password', { exact: true }).fill(resetPassword)
  await submitPaced(page, 'Log in')
  await expect(page).toHaveURL(/\/profile$/)
  await expect(page.getByRole('heading', { name: 'My profile' })).toBeVisible()
  await checkA11y(page, '/profile')

  // No token is stored: a reload gets a new one from the refresh cookie (TRD §6.1.1).
  await page.reload()
  await expect(page.getByRole('heading', { name: 'My profile' })).toBeVisible()
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))
  expect(stored).not.toMatch(/eyJ/) // no JWT anywhere in web storage

  // A client can't open admin pages: they look like a missing page (AFD §5.2).
  await page.goto('/admin/users')
  await expect(page.getByText('We can’t find that page')).toBeVisible()

  await page.getByRole('button', { name: /Account menu/ }).click()
  await page.getByRole('menuitem', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login/)
})

test('Admin invites a technician from Users @AUTH-6', async ({ watched: page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ADMIN)
  await page.getByLabel('Password', { exact: true }).fill(seedPassword())
  await submitPaced(page, 'Log in')
  await page.goto('/admin/users')
  await checkA11y(page, '/admin/users')
  await page.getByRole('button', { name: 'Invite user' }).click()
  const invitee = `tech-${run}@example.org`
  await page.getByLabel('Name').fill(`Shanice Grant ${run}`)
  await page.getByLabel('Email').fill(invitee)
  await page.getByRole('radio', { name: /Technician/ }).check()
  await page.getByRole('button', { name: 'Send invitation' }).click()
  await expect(page.getByText(`Invitation sent to ${invitee}.`)).toBeVisible()

  // The invitation email opens /invite/:token; setting a password signs them in.
  const mail = await mailTo(invitee, 'invit')
  const context = await page.context().browser()!.newContext({ ignoreHTTPSErrors: true })
  const invited = await context.newPage()
  await invited.goto(linkIn(mail.Text, '/invite/'))
  const password = `first visit ${randomUUID()}`
  await invited.getByLabel('New password').fill(password)
  await invited.getByLabel('Type it again').fill(password)
  await submitPaced(invited, 'Save')
  await expect(invited).toHaveURL(/\/dashboard$/)
  // A technician's Work section opens on their queue (the rail and the pane's tabs, DBD "The app shell")
  await invited.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Work' }).click()
  await expect(invited).toHaveURL(/\/queue$/)
  await expect(invited.getByRole('navigation', { name: 'Work pages' }).getByRole('link', { name: 'Queue' })).toBeVisible()
  await context.close()
})
