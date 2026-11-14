import { describe, expect, it } from 'vitest'
import { badge, decodeText, extension, gallery, linesOf, sizeText, TEXT_LIMIT, viewKind } from '../view'

function file (filename: string, kind: 'image' | 'video' | 'config' = 'config', size = 1000) {
  return { filename, kind, size_bytes: size }
}

describe('viewKind', () => {
  it('shows photos and video as themselves', () => {
    expect(viewKind(file('IMG_1.jpg', 'image'))).toBe('image')
    expect(viewKind(file('walk.mp4', 'video'))).toBe('video')
  })

  it('draws a PDF and reads logger programs, scripts and settings as text', () => {
    expect(viewKind(file('wiring.PDF'))).toBe('pdf')
    for (const name of ['rh_offset.py', 'KIN_main_v4.2.CR1', 'program.cr6', 'modem_settings.txt', 'data.csv', 'site.ttx']) {
      expect(viewKind(file(name))).toBe('text')
    }
  })

  it('offers anything else, and a text file over 1 MB, as a download', () => {
    expect(viewKind(file('firmware.bin'))).toBe('file')
    expect(viewKind(file('noextension'))).toBe('file')
    expect(viewKind(file('huge.log', 'config', TEXT_LIMIT + 1))).toBe('file')
  })
})

describe('decodeText', () => {
  it('reads UTF-8 text', () => {
    expect(decodeText(new TextEncoder().encode('OFFSET = -1.2\n°C').buffer)).toBe('OFFSET = -1.2\n°C')
  })

  it('refuses a file with a NUL byte or bad UTF-8, so it is offered as a download', () => {
    expect(decodeText(new Uint8Array([72, 0, 105]).buffer)).toBeNull()
    expect(decodeText(new Uint8Array([0xFF, 0xFE, 0x41]).buffer)).toBeNull()
  })
})

describe('the small helpers', () => {
  it('splits lines without a last empty one', () => {
    expect(linesOf('a\r\nb\n')).toEqual(['a', 'b'])
    expect(linesOf('')).toEqual([''])
  })

  it('names extensions and badges', () => {
    expect(extension('a.tar.GZ')).toBe('gz')
    expect(extension('.profile')).toBe('')
    expect(badge('KIN_main_v4.2.CR1')).toBe('CR1')
    expect(badge('setup')).toBe('FILE')
  })

  it('writes sizes for people', () => {
    expect(sizeText(512)).toBe('512 B')
    expect(sizeText(18 * 1024)).toBe('18 KB')
    expect(sizeText(1.2 * 1024 * 1024)).toBe('1.2 MB')
    expect(sizeText(null)).toBe('')
  })

  it('pages through the photos and video of a section only', () => {
    const files = [file('a.jpg', 'image'), file('b.py'), file('c.mp4', 'video')].map((f, i) => ({ ...f, media_id: String(i) })) as never[]
    expect(gallery(files).map((f: { media_id: string }) => f.media_id)).toEqual(['0', '2'])
  })
})
