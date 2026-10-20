import { describe, expect, it } from 'vitest'
import { qrPicture } from '@/features/stations/qrCode'
import { decodeFrame } from '../qrDecode'
import { guideRegion, tokenFromScan } from '../scan'

// The code the station card draws must be one the scanner reads: draw one, then decode it.
function render (text: string, scale: number, invert = false) {
  const { size, path } = qrPicture(text)
  const quiet = 4
  const side = (size + quiet * 2) * scale
  const data = new Uint8ClampedArray(side * side * 4).fill(255)
  const dark = new Set<string>()
  for (const m of path.matchAll(/M(\d+) (\d+)h(\d+)/g)) {
    const [x0, y, run] = [Number(m[1]), Number(m[2]), Number(m[3])] as const
    for (let x = x0; x < x0 + run; x++) {
      dark.add(`${x},${y}`)
    }
  }
  for (let py = 0; py < side; py++) {
    for (let px = 0; px < side; px++) {
      const mx = Math.floor(px / scale) - quiet
      const my = Math.floor(py / scale) - quiet
      const value = dark.has(`${mx},${my}`) === !invert ? 0 : 255
      const i = (py * side + px) * 4
      data[i] = data[i + 1] = data[i + 2] = value
    }
  }
  return { data, width: side, height: side }
}

describe('decodeFrame', () => {
  const url = 'https://mms.example.org/s/AbCdEfGhIjKlMnOpQrXk3p'

  it('reads the code the station card draws, and the token comes out of it', () => {
    const text = decodeFrame(render(url, 5))
    expect(text).toBe(url)
    expect(tokenFromScan(text ?? '')).toBe('AbCdEfGhIjKlMnOpQrXk3p')
  })

  it('reads a small, light-on-dark code too (a label under a torch)', () => {
    expect(decodeFrame(render(url, 3, true))).toBe(url)
  })

  it('finds nothing in a blank frame', () => {
    expect(decodeFrame({ data: new Uint8ClampedArray(64 * 64 * 4).fill(200), width: 64, height: 64 })).toBeNull()
  })
})

describe('guideRegion', () => {
  it('is a square in the middle of the shorter side', () => {
    expect(guideRegion(1280, 720)).toEqual({ x: 388, y: 108, size: 504 })
    expect(guideRegion(720, 1280)).toEqual({ x: 108, y: 388, size: 504 })
  })
})
