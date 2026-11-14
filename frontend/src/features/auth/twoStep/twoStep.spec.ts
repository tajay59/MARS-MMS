import { describe, expect, it } from 'vitest'
import { groupKey, recoveryCodesText, setupBanner } from './twoStep'

describe('the setup banner', () => {
  const end = '2026-11-19T15:00:00Z'

  it('names the date while there are days left', () => {
    const banner = setupBanner(end, new Date('2026-11-14T15:00:00Z'), 'America/Jamaica')
    expect(banner.type).toBe('warning')
    expect(banner.lead).toBe('Set up two-step sign-in by 19 Nov 2026.')
    expect(banner.rest).toBe('After that, you can’t log in without it.')
  })

  it('says today on the last day', () => {
    const banner = setupBanner(end, new Date('2026-11-19T09:00:00Z'), 'America/Jamaica')
    expect(banner.type).toBe('warning')
    expect(banner.lead).toBe('Set up two-step sign-in today.')
    expect(banner.rest).toBe('After today, you can’t log in without it.')
  })

  it('counts the day in the person’s zone, not UTC', () => {
    // 02:00 UTC on the 20th is still the evening of the 19th in Jamaica
    const banner = setupBanner('2026-11-20T02:00:00Z', new Date('2026-11-19T20:00:00Z'), 'America/Jamaica')
    expect(banner.lead).toBe('Set up two-step sign-in today.')
  })

  it('turns into an error once the window is over, and says the rule applies at the next login', () => {
    const banner = setupBanner(end, new Date('2026-11-20T00:00:00Z'))
    expect(banner.type).toBe('error')
    expect(banner.lead).toBe('Two-step sign-in isn’t set up.')
    expect(banner.rest).toBe('You’ll need it the next time you log in.')
  })

  it('treats a date it can’t read as overdue rather than hiding the nudge', () => {
    expect(setupBanner('nonsense').type).toBe('error')
  })
})

describe('the recovery codes file', () => {
  it('lists every code under what they are for, and holds nothing else secret', () => {
    const text = recoveryCodesText(['AAAAA-BBBBB', 'CCCCC-DDDDD'], 'admin@example.org', '12 Nov 2026')
    expect(text).toContain('recovery codes for admin@example.org')
    expect(text).toContain('Made on 12 Nov 2026')
    expect(text).toContain('AAAAA-BBBBB\nCCCCC-DDDDD')
    expect(text).toContain('log in once')
  })
})

describe('the typed key', () => {
  it('is written in groups of four', () => {
    expect(groupKey('JBSWY3DPEHPK3PXP')).toBe('JBSW Y3DP EHPK 3PXP')
    expect(groupKey('ABC')).toBe('ABC')
  })
})
