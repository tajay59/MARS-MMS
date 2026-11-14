import type { BoardMedia } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { capturedAt, inOrder, kindOf, mediaRefusal, ownerRef, SECTIONS } from '../media'

const NOW = new Date('2026-10-21T18:00:00Z')

function item (id: string, at: string | null, added = '2026-10-21T15:00:00Z'): BoardMedia {
  return {
    media_id: id, kind: 'image', filename: `${id}.jpg`, size_bytes: 10, caption: null, captured_at: at,
    added_by: { id: 'u1', name: 'Andrea' }, added_at: added, hidden: false,
  }
}

describe('ownerRef', () => {
  it('is the reference the server checks', () => {
    expect(ownerRef('v1', 's1', 'e1', 'before')).toBe('visit:v1:station:s1:element:e1:before')
  })
})

describe('SECTIONS', () => {
  it('gives notes and recommendations one section and tasks and config a before and an after', () => {
    expect(SECTIONS).toEqual({
      note: ['main'], task: ['before', 'after'], recommendation: ['main'], config: ['before', 'after'],
    })
  })
})

describe('kindOf', () => {
  it('reads the type first and the extension when a picker leaves it empty', () => {
    expect(kindOf({ type: 'image/heic', name: 'a.heic' })).toBe('image')
    expect(kindOf({ type: 'video/quicktime', name: 'a.mov' })).toBe('video')
    expect(kindOf({ type: '', name: 'IMG_0001.JPG' })).toBe('image')
    expect(kindOf({ type: '', name: 'clip.MP4' })).toBe('video')
    expect(kindOf({ type: 'application/pdf', name: 'a.pdf' })).toBeNull()
    expect(kindOf({ type: '', name: 'noextension' })).toBeNull()
  })

  it('takes any other file as a file where the element takes them (Config)', () => {
    expect(kindOf({ type: 'application/pdf', name: 'a.pdf' }, true)).toBe('config')
    expect(kindOf({ type: '', name: 'CR1000.ttx' }, true)).toBe('config')
    expect(kindOf({ type: 'image/png', name: 'a.png' }, true)).toBe('image')
  })
})

describe('capturedAt', () => {
  const file = { lastModified: Date.parse('2026-10-21T15:00:00Z') }

  it('uses the offset the camera wrote', () => {
    expect(capturedAt(file, { local: '2026-10-21T10:03:05', offset: '-05:00' }, 'Asia/Tokyo', NOW)).toBe('2026-10-21T15:03:05.000Z')
    expect(capturedAt(file, { local: '2026-10-21T15:03:05', offset: 'Z' }, null, NOW)).toBe('2026-10-21T15:03:05.000Z')
  })

  it('reads a time with no offset in the station’s zone', () => {
    expect(capturedAt(file, { local: '2026-10-21T08:03:05', offset: null }, 'America/Jamaica', NOW)).toBe('2026-10-21T13:03:00.000Z')
  })

  it('falls back to the file’s modified time when there is no usable time in the picture', () => {
    expect(capturedAt(file, null, 'America/Jamaica', NOW)).toBe('2026-10-21T15:00:00.000Z')
    expect(capturedAt(file, { local: '2026-10-21T08:03:05', offset: null }, null, NOW)).toBe('2026-10-21T15:00:00.000Z')
    expect(capturedAt({ lastModified: 0 }, null, null, NOW)).toBeNull()
  })

  it('leaves out a time more than a day ahead of the clock', () => {
    expect(capturedAt({ lastModified: NOW.getTime() + 3 * 86_400_000 }, null, null, NOW)).toBeNull()
    expect(capturedAt({ lastModified: NOW.getTime() + 3_600_000 }, null, null, NOW)).not.toBeNull()
  })
})

describe('inOrder', () => {
  it('puts the oldest capture first, falling back to when it was added', () => {
    const sorted = inOrder([
      item('b', '2026-10-21T14:00:00Z'),
      item('a', '2026-10-21T13:00:00Z'),
      item('d', null, '2026-10-21T13:30:00Z'),
    ])
    expect(sorted.map(i => i.media_id)).toEqual(['a', 'd', 'b'])
  })
})

describe('mediaRefusal', () => {
  it('has a sentence for each reason the server gives and none for the rest', () => {
    expect(mediaRefusal('not_editor')).toBe('Only the person who added this, or the station’s owner, can change it.')
    expect(mediaRefusal('bad_section')).toContain('section')
    expect(mediaRefusal('locked')).toContain('finalized')
    expect(mediaRefusal('something_new')).toBeNull()
  })
})
