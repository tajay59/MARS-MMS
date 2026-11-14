// Capture time from a JPEG's EXIF block (decision W11-12). Pure bytes in, no browser API: the
// canvas resize in image.ts drops EXIF, so the time is read from the original file first.
//
// EXIF stores local time with no zone ("2026:10:21 14:03:05"), and the offset tag (OffsetTimeOriginal)
// only exists on newer phones. So the answer is the wall-clock text plus the offset when there is
// one; the caller reads it in the station's time zone (rule 8).

export interface CaptureTime {
  /** Wall clock as written by the camera: `YYYY-MM-DDTHH:mm:ss`. */
  local: string
  /** `+05:30`, `-05:00` or `Z`, when the camera wrote OffsetTimeOriginal. */
  offset: string | null
}

const TAG_EXIF_IFD = 0x87_69
const TAG_DATE_TIME = 0x01_32
const TAG_DATE_TIME_ORIGINAL = 0x90_03
const TAG_OFFSET_TIME_ORIGINAL = 0x90_11
const TYPE_ASCII = 2
/** Enough for the APP1 segment of every phone camera; the thumbnail lives after it. */
export const EXIF_HEAD_BYTES = 128 * 1024

const EXIF_DATE = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/
const EXIF_OFFSET = /^[+-]\d{2}:\d{2}$/

export function parseCaptureTime (head: Uint8Array): CaptureTime | null {
  const tiff = findTiff(head)
  if (!tiff) {
    return null
  }
  const { view, base } = tiff
  const little = view.getUint16(base, false) === 0x49_49
  const ifd0 = base + view.getUint32(base + 4, little)
  const zero = readIfd(view, base, ifd0, little)
  const pointer = zero.get(TAG_EXIF_IFD)
  const exif = pointer && pointer.type === 4 ? readIfd(view, base, base + pointer.value, little) : new Map<number, Entry>()
  const raw = ascii(view, base, exif.get(TAG_DATE_TIME_ORIGINAL)) ?? ascii(view, base, zero.get(TAG_DATE_TIME))
  const match = raw ? EXIF_DATE.exec(raw) : null
  if (!match) {
    return null
  }
  const [, y, mo, d, h, mi, s] = match
  if (y === '0000') {
    return null // cameras without a clock write zeros
  }
  const offsetText = ascii(view, base, exif.get(TAG_OFFSET_TIME_ORIGINAL))
  const offset = offsetText && EXIF_OFFSET.test(offsetText) ? offsetText : null
  return { local: `${y}-${mo}-${d}T${h}:${mi}:${s}`, offset: offset === '+00:00' ? 'Z' : offset }
}

interface Entry {
  type: number
  count: number
  /** For ASCII, the offset of the text from the TIFF header; for a LONG, the value. */
  value: number
}

function findTiff (bytes: Uint8Array): { view: DataView, base: number } | null {
  if (bytes.length < 4 || bytes[0] !== 0xFF || bytes[1] !== 0xD8) {
    return null
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  let at = 2
  while (at + 4 <= bytes.length && bytes[at] === 0xFF) {
    const marker = bytes[at + 1]!
    if (marker === 0xDA || marker === 0xD9) {
      return null // start of the picture data: no EXIF before it
    }
    const size = view.getUint16(at + 2, false)
    if (marker === 0xE1 && size >= 14 && at + 10 <= bytes.length && isExifHeader(bytes, at + 4)) {
      const base = at + 10
      if (base + 8 > bytes.length) {
        return null
      }
      const order = view.getUint16(base, false)
      return order === 0x49_49 || order === 0x4D_4D ? { view, base } : null
    }
    at += 2 + size
  }
  return null
}

function isExifHeader (bytes: Uint8Array, at: number): boolean {
  return [0x45, 0x78, 0x69, 0x66, 0, 0].every((code, i) => bytes[at + i] === code)
}

function readIfd (view: DataView, base: number, at: number, little: boolean): Map<number, Entry> {
  const entries = new Map<number, Entry>()
  if (at < base || at + 2 > view.byteLength) {
    return entries
  }
  const count = view.getUint16(at, little)
  for (let i = 0; i < count; i++) {
    const entry = at + 2 + i * 12
    if (entry + 12 > view.byteLength) {
      break
    }
    const type = view.getUint16(entry + 2, little)
    const length = view.getUint32(entry + 4, little)
    // An ASCII value of 4 bytes or fewer sits in the entry itself; longer ones sit at an offset
    const inline = type === TYPE_ASCII && length <= 4
    entries.set(view.getUint16(entry, little), {
      type,
      count: length,
      value: inline ? entry + 8 - base : view.getUint32(entry + 8, little),
    })
  }
  return entries
}

function ascii (view: DataView, base: number, entry: Entry | undefined): string | null {
  if (!entry || entry.type !== TYPE_ASCII || entry.count < 2) {
    return null
  }
  const from = base + entry.value
  if (from + entry.count > view.byteLength) {
    return null
  }
  let out = ''
  for (let i = 0; i < entry.count; i++) {
    const code = view.getUint8(from + i)
    if (code === 0) {
      break
    }
    out += String.fromCodePoint(code)
  }
  return out
}
