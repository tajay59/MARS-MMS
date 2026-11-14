import { beforeEach, describe, expect, it, vi } from 'vitest'
import { canInstall, hideInstallOffer, offerInstall, promptInstall, resetInstallForTests, simulateInstallPrompt } from '../install'

// The install prompt (W13-12): offered while the browser holds one, hidden for 14 days after "Not now".

function prompt (outcome: 'accepted' | 'dismissed') {
  return Object.assign(new Event('beforeinstallprompt'), {
    prompt: vi.fn(async () => undefined),
    userChoice: Promise.resolve({ outcome }),
  })
}

beforeEach(() => {
  resetInstallForTests()
  localStorage.clear()
})

describe('the install offer', () => {
  it('is not there until the browser offers one', () => {
    expect(canInstall.value).toBe(false)
    expect(offerInstall.value).toBe(false)
  })

  it('shows while the browser holds a prompt', () => {
    simulateInstallPrompt(prompt('accepted'))
    expect(canInstall.value).toBe(true)
    expect(offerInstall.value).toBe(true)
  })

  it('hides for 14 days after Not now, but the prompt is still there for My profile', () => {
    simulateInstallPrompt(prompt('accepted'))
    hideInstallOffer(Date.now())
    expect(offerInstall.value).toBe(false)
    expect(canInstall.value).toBe(true)
    expect(Number(localStorage.getItem('mms-install-hidden'))).toBeGreaterThan(Date.now() + (13 * 86_400_000))
  })

  it('asks the browser once, and an accepted install ends the offer', async () => {
    const event = prompt('accepted')
    simulateInstallPrompt(event)
    expect(await promptInstall()).toBe('accepted')
    expect(event.prompt).toHaveBeenCalledOnce()
    expect(canInstall.value).toBe(false)
    expect(await promptInstall()).toBe('unavailable')
  })

  it('a dismissed prompt is spent too (the browser gives one per event)', async () => {
    simulateInstallPrompt(prompt('dismissed'))
    expect(await promptInstall()).toBe('dismissed')
    expect(canInstall.value).toBe(false)
  })
})
