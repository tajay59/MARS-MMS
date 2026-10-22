import type { VisitMedia } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { byPhase, canAddMedia, canRemoveMedia, capturedAt, kindOf, mediaRefusal, ownerRef, stationMedia } from '../media'

const NOW = new Date('2026-10-21T18:00:00Z')

function item (id: string, phase: VisitMedia['phase'], at: string | null, added = '2026-10-21T15:00:00Z'): VisitMedia {
  return {
    media_id: id, phase, kind: 'image', filename: `${id}.jpg`, caption: null, captured_at: at,
    added_by: { id: 'u1', name: 'Andrea' }, added_at: added, hidden: false,
  }
}

describe('ownerRef', () => {
  it('is the reference the server checks', () => {
    expect(ownerRef('v1', 's1', 'during')).toBe('visit:v1:station:s1:during')
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

describe('byPhase', () => {
  it('has every phase, oldest capture first, falling back to when it was added', () => {
    const groups = byPhase([
      item('c', 'after', '2026-10-21T16:00:00Z'),
      item('b', 'before', '2026-10-21T14:00:00Z'),
      item('a', 'before', '2026-10-21T13:00:00Z'),
      item('d', 'before', null, '2026-10-21T13:30:00Z'),
    ])
    expect(groups.map(g => g.phase)).toEqual(['before', 'during', 'after'])
    expect(groups[0]!.items.map(i => i.media_id)).toEqual(['a', 'd', 'b'])
    expect(groups[1]!.items).toEqual([])
    expect(groups[2]!.items.map(i => i.media_id)).toEqual(['c'])
  })
})

describe('who and when', () => {
  const visit = (status: string) => ({ status, actions: [], staff: [{ id: 'u1', name: 'A' }] }) as never

  it('lets those attending add while the visit is started or ended', () => {
    expect(canAddMedia(visit('started'), 'u1', false)).toBe(true)
    expect(canAddMedia(visit('ended'), 'u1', false)).toBe(true)
    expect(canAddMedia(visit('planned'), 'u1', false)).toBe(false)
    expect(canAddMedia(visit('cancelled'), 'u1', true)).toBe(false)
    expect(canAddMedia(visit('started'), 'u2', false)).toBe(false)
    expect(canAddMedia(visit('started'), 'u2', true)).toBe(true)
  })

  it('lets the person who added it, or an admin, remove it', () => {
    expect(canRemoveMedia(item('a', 'before', null), 'u1', false)).toBe(true)
    expect(canRemoveMedia(item('a', 'before', null), 'u2', false)).toBe(false)
    expect(canRemoveMedia(item('a', 'before', null), 'u2', true)).toBe(true)
  })

  it('finds a station’s media on the visit', () => {
    const visitDoc = { stations: [{ station_id: 's1', media: [item('a', 'before', null)] }, { station_id: 's2', media: [] }] } as never
    expect(stationMedia(visitDoc, 's1')).toHaveLength(1)
    expect(stationMedia(visitDoc, 's9')).toEqual([])
  })
})

describe('mediaRefusal', () => {
  it('has a sentence for each reason the server gives and none for the rest', () => {
    expect(mediaRefusal('not_uploader')).toBe('Only the person who added it, or an admin, can remove it.')
    expect(mediaRefusal('locked')).toContain('finalized')
    expect(mediaRefusal('something_new')).toBeNull()
  })
})
