import { describe, expect, it } from 'vitest'
import { parseCaptureTime } from '../exif'

// A JPEG header with an EXIF block built by hand, so the parser is checked against bytes and not
// against its own idea of the format.

interface Tag {
  id: number
  text: string
}

function writer (little: boolean) {
  return {
    u16: (n: number) => (little ? [n & 0xFF, n >> 8] : [n >> 8, n & 0xFF]),
    u32: (n: number) => (little
      ? [n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF, n >>> 24]
      : [n >>> 24, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF]),
  }
}

function text (value: string): number[] {
  return [...value].map(c => c.codePointAt(0)!).concat(0)
}

// An IFD of ASCII tags at `start` (from the TIFF header); long values follow the entries
function ifd (tags: Tag[], start: number, little: boolean): number[] {
  const { u16, u32 } = writer(little)
  const out: number[] = [...u16(tags.length)]
  let cursor = start + 2 + tags.length * 12 + 4
  const data: number[] = []
  for (const tag of tags) {
    const bytes = text(tag.text)
    out.push(...u16(tag.id), ...u16(2), ...u32(bytes.length))
    if (bytes.length <= 4) {
      out.push(...bytes, ...Array.from({ length: 4 - bytes.length }, () => 0))
    } else {
      out.push(...u32(cursor))
      data.push(...bytes)
      cursor += bytes.length
    }
  }
  return [...out, ...u32(0), ...data]
}

function jpeg (opts: { little?: boolean, original?: string, plain?: string, offset?: string }): Uint8Array {
  const little = opts.little ?? true
  const { u16, u32 } = writer(little)
  const exifTags: Tag[] = []
  if (opts.original) {
    exifTags.push({ id: 0x90_03, text: opts.original })
  }
  if (opts.offset) {
    exifTags.push({ id: 0x90_11, text: opts.offset })
  }
  // IFD0 at 8: DateTime (optional) and the pointer to the Exif IFD, which comes after IFD0's data
  const entries = 1 + (opts.plain ? 1 : 0)
  const zeroSize = 2 + entries * 12 + 4
  const plainBytes = opts.plain ? text(opts.plain) : []
  const exifAt = 8 + zeroSize + plainBytes.length
  const zero: number[] = [...u16(entries)]
  if (opts.plain) {
    zero.push(...u16(0x01_32), ...u16(2), ...u32(plainBytes.length), ...u32(8 + zeroSize))
  }
  zero.push(...u16(0x87_69), ...u16(4), ...u32(1), ...u32(exifAt), ...u32(0), ...plainBytes)
  const tiff = [...(little ? [0x49, 0x49] : [0x4D, 0x4D]), ...u16(42), ...u32(8), ...zero, ...ifd(exifTags, exifAt, little)]
  const body = [0x45, 0x78, 0x69, 0x66, 0, 0, ...tiff]
  const size = body.length + 2
  return Uint8Array.from([0xFF, 0xD8, 0xFF, 0xE1, size >> 8, size & 0xFF, ...body, 0xFF, 0xDA, 0, 2])
}

describe('parseCaptureTime', () => {
  it.each([true, false])('reads DateTimeOriginal (little endian: %s)', little => {
    const got = parseCaptureTime(jpeg({ little, original: '2026:10:21 14:03:05' }))
    expect(got).toEqual({ local: '2026-10-21T14:03:05', offset: null })
  })

  it('reads the offset when the camera wrote one', () => {
    expect(parseCaptureTime(jpeg({ original: '2026:10:21 14:03:05', offset: '-05:00' }))?.offset).toBe('-05:00')
    expect(parseCaptureTime(jpeg({ original: '2026:10:21 14:03:05', offset: '+00:00' }))?.offset).toBe('Z')
  })

  it('ignores an offset it cannot read', () => {
    expect(parseCaptureTime(jpeg({ original: '2026:10:21 14:03:05', offset: 'later' }))?.offset).toBeNull()
  })

  it('falls back to DateTime in the first block', () => {
    expect(parseCaptureTime(jpeg({ plain: '2026:01:02 03:04:05' }))?.local).toBe('2026-01-02T03:04:05')
  })

  it('prefers the time the picture was taken to the time the file was edited', () => {
    const got = parseCaptureTime(jpeg({ original: '2026:10:21 14:03:05', plain: '2027:01:01 00:00:00' }))
    expect(got?.local).toBe('2026-10-21T14:03:05')
  })

  it('answers null for a camera with no clock, no EXIF, not a JPEG, or a cut file', () => {
    expect(parseCaptureTime(jpeg({ original: '0000:00:00 00:00:00' }))).toBeNull()
    expect(parseCaptureTime(Uint8Array.from([0xFF, 0xD8, 0xFF, 0xDA, 0, 2]))).toBeNull()
    expect(parseCaptureTime(new TextEncoder().encode('GIF89a not a jpeg'))).toBeNull()
    expect(parseCaptureTime(jpeg({ original: '2026:10:21 14:03:05' }).slice(0, 30))).toBeNull()
    expect(parseCaptureTime(new Uint8Array(0))).toBeNull()
  })
})
