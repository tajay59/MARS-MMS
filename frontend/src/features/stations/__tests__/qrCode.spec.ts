import { describe, expect, it } from 'vitest'
import { scanUrl, shortScanUrl } from '@/features/scan/scan'
import { qrPicture } from '../qrCode'

describe('scanUrl', () => {
  it('is the address a label holds: the token and nothing else', () => {
    expect(scanUrl('https://mms.example.org', 'abc')).toBe('https://mms.example.org/s/abc')
    expect(scanUrl('https://mms.example.org/', 'abc')).toBe('https://mms.example.org/s/abc')
  })

  it('is shortened for the card without the whole token', () => {
    expect(shortScanUrl('https://mms.example.org', 'AbCdEfGhIjKlMnOpQrXk3p')).toBe('mms.example.org/s/…Xk3p')
  })
})

describe('qrPicture', () => {
  it('draws a square code from the text', () => {
    const picture = qrPicture('https://mms.example.org/s/AbCdEfGhIjKlMnOpQrXk3p')
    // Version 3 to 4 at level M for 47 characters: 29 or 33 modules
    expect(picture.size).toBeGreaterThanOrEqual(25)
    expect(picture.size).toBeLessThanOrEqual(41)
    expect(picture.path).toMatch(/^M\d+ \d+h\d+v1h-\d+z/)
    expect(picture.path).not.toMatch(/[^MhvzHV\d\s-]/)
  })

  it('is the same picture for the same text, and another for another text', () => {
    expect(qrPicture('a').path).toBe(qrPicture('a').path)
    expect(qrPicture('a').path).not.toBe(qrPicture('b').path)
  })
})
