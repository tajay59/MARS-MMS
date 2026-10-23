import { describe, expect, it } from 'vitest'
import { isIos, isStandalone, mustInstallToPrepare } from '../platform'

// An iPhone prepares only from the installed app (finding F2, W13-12).

function nav (over: Partial<Navigator> & { standalone?: boolean }): Navigator {
  return { userAgent: '', platform: '', maxTouchPoints: 0, ...over } as unknown as Navigator
}

const standalone = { matchMedia: () => ({ matches: true }) } as unknown as Pick<Window, 'matchMedia'>
const browser = { matchMedia: () => ({ matches: false }) } as unknown as Pick<Window, 'matchMedia'>

const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'
const ANDROID = 'Mozilla/5.0 (Linux; Android 15; Pixel 7) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36'

describe('isIos', () => {
  it('knows an iPhone, an iPad and an iPad that says it is a Mac', () => {
    expect(isIos(nav({ userAgent: IPHONE }))).toBe(true)
    expect(isIos(nav({ userAgent: 'Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)' }))).toBe(true)
    expect(isIos(nav({ userAgent: 'Mozilla/5.0 (Macintosh)', platform: 'MacIntel', maxTouchPoints: 5 }))).toBe(true)
  })

  it('does not take Android or a Mac for it', () => {
    expect(isIos(nav({ userAgent: ANDROID }))).toBe(false)
    expect(isIos(nav({ userAgent: 'Mozilla/5.0 (Macintosh)', platform: 'MacIntel', maxTouchPoints: 0 }))).toBe(false)
  })
})

describe('isStandalone', () => {
  it('is true on the Home Screen of an iPhone and in an installed app elsewhere', () => {
    expect(isStandalone(nav({ standalone: true }), browser)).toBe(true)
    expect(isStandalone(nav({}), standalone)).toBe(true)
  })

  it('is false in a tab', () => {
    expect(isStandalone(nav({ standalone: false }), browser)).toBe(false)
  })
})

describe('mustInstallToPrepare', () => {
  it('is only for an iPhone in a Safari tab', () => {
    expect(mustInstallToPrepare(nav({ userAgent: IPHONE }), browser)).toBe(true)
    expect(mustInstallToPrepare(nav({ userAgent: IPHONE, standalone: true }), browser)).toBe(false)
    expect(mustInstallToPrepare(nav({ userAgent: ANDROID }), browser)).toBe(false)
  })
})
