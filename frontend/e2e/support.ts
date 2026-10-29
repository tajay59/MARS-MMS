import type { Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { test as base, expect } from '@playwright/test'

const MAILPIT = process.env.MMS_MAILPIT_URL ?? 'http://127.0.0.1:8025'

/** Every page fails its test on a CSP violation or an uncaught error (TP "Frontend quality"). */
export const test = base.extend<{ watched: Page }>({
  watched: async ({ page }, use) => {
    const problems: string[] = []
    page.on('console', message => {
      if (message.type() === 'error' && /Content Security Policy|Refused to/i.test(message.text())) {
        problems.push(`CSP: ${message.text()}`)
      }
    })
    page.on('pageerror', error => problems.push(`Uncaught: ${error.message}`))
    await use(page)
    expect(problems, problems.join('\n')).toEqual([])
  },
})

export function seedPassword (): string {
  const password = process.env.MMS_SEED_PASSWORD
  if (!password) {
    throw new Error('MMS_SEED_PASSWORD is not set (global-setup reads it from infra/.env)')
  }
  return password
}

/**
 * WCAG 2.2 AA in light and dark (NFR-11, DBD D2). Test accounts use the System appearance, so
 * the app follows the emulated colour scheme live, as it would follow the phone's setting.
 */
export async function checkA11y (page: Page, label: string): Promise<void> {
  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' })
    await expect(page.locator('html')).toHaveClass(scheme === 'dark' ? /app-dark/ : /^(?!.*app-dark)/)
    // Measure the settled page, not one mid-transition or still loading its fonts.
    await page.waitForLoadState('networkidle')
    await page.evaluate(async () => {
      await document.fonts.ready
    })
    await page.waitForTimeout(300)
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze()
    const found = results.violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(', ')}`)
    expect(found, `${label} (${scheme})`).toEqual([])
  }
  await page.emulateMedia({ colorScheme: 'light' })
}

interface MailSummary { ID: string, Subject: string }

/** The newest email to `to` whose subject contains `subject`, waiting for the platform consumer. */
export async function mailTo (to: string, subject: string, timeoutMs = 60_000): Promise<{ Text: string, HTML: string }> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const found = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`)
    const { messages = [] } = await found.json() as { messages?: MailSummary[] }
    const hit = messages.find(m => m.Subject.includes(subject))
    if (hit) {
      const message = await fetch(`${MAILPIT}/api/v1/message/${hit.ID}`)
      return await message.json() as { Text: string, HTML: string }
    }
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
  throw new Error(`No email "${subject}" to ${to} within ${timeoutMs / 1000} s`)
}

/** The first link in an email's text that goes to `pathPrefix`, as a path on this app. */
export function linkIn (text: string, pathPrefix: string): string {
  const match = text.match(new RegExp(String.raw`https://[^/\s]+(${pathPrefix}[^\s>)]*)`))
  if (!match?.[1]) {
    throw new Error(`No ${pathPrefix} link in:\n${text}`)
  }
  return match[1]
}

/**
 * Submits a public auth form, waiting out Nginx's `auth` rate limit (10/min per IP, burst 5)
 * that a run of journeys can reach: a 429 shows "Too many attempts", so wait and send again.
 * A failed attempt clears the password, so the typed values are put back before each retry.
 */
export async function submitPaced (page: Page, button: string): Promise<void> {
  const inputs = page.locator('form input:not([type="checkbox"]):not([type="radio"])')
  const typed = await inputs.evaluateAll(fields => fields.map(f => (f as HTMLInputElement).value))
  for (let attempt = 0; attempt < 4; attempt++) {
    if (attempt > 0) {
      for (const [index, value] of typed.entries()) {
        const field = inputs.nth(index)
        if (value && await field.inputValue() !== value) {
          await field.fill(value)
        }
      }
    }
    // "Moved" means away from where the click happened: a page that is not /login (the reset
    // page, say) already satisfies "not the login page", which hid the throttle from this helper
    const from = page.url()
    await page.getByRole('button', { name: button, exact: true }).click()
    const throttled = page.getByText('Too many attempts')
    const outcome = await Promise.race([
      throttled.waitFor({ timeout: 4000 }).then(() => 'throttled' as const),
      page.waitForURL(url => url.href !== from, { timeout: 4000 }).then(() => 'moved' as const),
    ]).catch(() => 'settled' as const)
    if (outcome !== 'throttled') {
      return
    }
    await page.waitForTimeout(7000)
  }
}

export { expect } from '@playwright/test'
