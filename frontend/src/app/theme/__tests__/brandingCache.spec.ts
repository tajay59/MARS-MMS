import { beforeEach, describe, expect, it } from 'vitest'
import { builtInMaterial } from '@/app/theme/brand'
import { BRANDING_STORAGE_KEY, readCachedBranding, writeCachedBranding } from '@/app/theme/brandingCache'

// The organization's colours kept on the device for the first paint and offline (W4-12)
describe('brandingCache', () => {
  beforeEach(() => localStorage.clear())

  it('starts with the built-in colours', () => {
    expect(readCachedBranding()).toEqual({ material: null, version: 0 })
  })

  it('keeps what the server sent', () => {
    writeCachedBranding({ material: builtInMaterial, version: 3 })
    expect(readCachedBranding()).toEqual({ material: builtInMaterial, version: 3 })
  })

  it('falls back to built-in for anything broken, and forgets its version so it fetches again', () => {
    localStorage.setItem(BRANDING_STORAGE_KEY, '{"material": {"schemes": {}}, "version": 7}')
    expect(readCachedBranding()).toEqual({ material: null, version: 0 })
    localStorage.setItem(BRANDING_STORAGE_KEY, 'not json')
    expect(readCachedBranding()).toEqual({ material: null, version: 0 })
  })
})
