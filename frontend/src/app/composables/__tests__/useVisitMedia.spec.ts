import type { Upload } from '../useUpload'
import type { VisitOut } from '@/api/models'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import { useVisitMedia, type VisitMediaDeps } from '../useVisitMedia'

const VISIT = {
  id: 'v1',
  stations: [{ station_id: 's1', time_zone: 'America/Jamaica' }],
} as unknown as VisitOut

function photo (name = 'IMG_1.jpg'): File {
  return new File(['x'], name, { type: 'image/jpeg', lastModified: Date.parse('2026-10-21T15:00:00Z') })
}

function video (name = 'walk.mp4'): File {
  return new File(['xxxx'], name, { type: 'video/mp4', lastModified: Date.parse('2026-10-21T15:05:00Z') })
}

interface FakeUpload {
  start: ReturnType<typeof vi.fn>
  reset: ReturnType<typeof vi.fn>
  cancel: ReturnType<typeof vi.fn>
  dispose: ReturnType<typeof vi.fn>
  mediaId: string | null
  error: string | null
  sent: number
  total: number
}

function fake (file: File, ok = true, id = 'media-1'): FakeUpload {
  const upload: FakeUpload = {
    start: vi.fn(async () => {
      upload.mediaId = ok ? id : null
      upload.error = ok ? null : 'The connection kept failing.'
      return ok
    }),
    reset: vi.fn(),
    cancel: vi.fn(async () => {}),
    dispose: vi.fn(),
    mediaId: null, error: null, sent: file.size, total: file.size,
  }
  return upload
}

function setup (overrides: Partial<VisitMediaDeps> = {}) {
  const seen: VisitOut[] = []
  const uploads: FakeUpload[] = []
  const deps: VisitMediaDeps = {
    prepare: vi.fn(async (file: File) => ({ file, captured: null, resized: false })),
    upload: vi.fn((file: File) => {
      const u = fake(file)
      uploads.push(u)
      return u as unknown as Upload
    }),
    addMedia: vi.fn(async () => VISIT),
    ...overrides,
  }
  const media = useVisitMedia({ visit: () => VISIT, onVisit: v => seen.push(v), deps })
  return { media, deps, seen, uploads }
}

async function settle (): Promise<void> {
  for (let i = 0; i < 10; i++) {
    await Promise.resolve()
    await new Promise(resolve => setTimeout(resolve, 0))
  }
}

describe('useVisitMedia', () => {
  it('prepares a photo, uploads it for the station and phase, and puts it on the station', async () => {
    const { media, deps, seen } = setup()
    const refused = media.add('s1', 'before', [photo()])
    expect(refused).toEqual([])
    await settle()
    expect(deps.prepare).toHaveBeenCalledOnce()
    expect(deps.upload).toHaveBeenCalledWith(expect.any(File), { ownerRef: 'visit:v1:station:s1:before', kind: 'image' })
    expect(deps.addMedia).toHaveBeenCalledWith('v1', 's1', {
      media_id: 'media-1', phase: 'before', captured_at: '2026-10-21T15:00:00.000Z',
    })
    expect(seen).toEqual([VISIT])
    expect(media.items).toHaveLength(0) // the visit shows it now
  })

  it('sends a video as recorded, without preparing it', async () => {
    const { media, deps } = setup()
    media.add('s1', 'during', [video()])
    await settle()
    expect(deps.prepare).not.toHaveBeenCalled()
    expect(deps.upload).toHaveBeenCalledWith(expect.any(File), { ownerRef: 'visit:v1:station:s1:during', kind: 'video' })
    expect(deps.addMedia).toHaveBeenCalledWith('v1', 's1', expect.objectContaining({ captured_at: '2026-10-21T15:05:00.000Z' }))
  })

  it('names the files that are neither photos nor video and takes the rest', async () => {
    const { media, deps } = setup()
    const refused = media.add('s1', 'after', [new File(['x'], 'notes.txt', { type: 'text/plain' }), photo()])
    expect(refused).toEqual(['notes.txt'])
    await settle()
    expect(deps.addMedia).toHaveBeenCalledOnce()
  })

  it('sends the capture time the camera wrote, read in the station’s zone', async () => {
    const { media, deps } = setup({
      prepare: vi.fn(async (file: File) => ({ file, captured: { local: '2026-10-21T08:03:05', offset: null }, resized: false })),
    })
    media.add('s1', 'before', [photo()])
    await settle()
    expect(deps.addMedia).toHaveBeenCalledWith('v1', 's1', expect.objectContaining({ captured_at: '2026-10-21T13:03:00.000Z' }))
  })

  it('keeps a failed upload on the list and tries again from where it stopped', async () => {
    const attempts: FakeUpload[] = []
    let ok = false
    const { media, deps } = setup({
      upload: vi.fn((file: File) => {
        const u = fake(file, ok)
        attempts.push(u)
        return u as unknown as Upload
      }),
    })
    media.add('s1', 'before', [photo()])
    await settle()
    const [item] = media.items
    expect(item?.state).toBe('failed')
    expect(item?.error).toBe('The connection kept failing.')
    expect(deps.addMedia).not.toHaveBeenCalled()
    expect(attempts[0]?.reset).toHaveBeenCalledOnce()

    ok = true
    attempts[0]!.start.mockImplementation(async () => {
      attempts[0]!.mediaId = 'media-1'
      return true
    })
    media.retry(item!.key)
    await settle()
    expect(deps.upload).toHaveBeenCalledOnce() // the same upload, so only the rest is sent
    expect(deps.prepare).toHaveBeenCalledOnce() // and the photo is not shrunk twice
    expect(deps.addMedia).toHaveBeenCalledOnce()
    expect(media.items).toHaveLength(0)
  })

  it('does not upload again when only putting it on the station failed', async () => {
    const addMedia = vi.fn()
      .mockRejectedValueOnce(new NetworkError(new Error('offline')))
      .mockResolvedValueOnce(VISIT)
    const { media, deps, uploads } = setup({ addMedia: addMedia as unknown as VisitMediaDeps['addMedia'] })
    media.add('s1', 'before', [photo()])
    await settle()
    expect(media.items[0]?.state).toBe('failed')
    expect(media.items[0]?.error).toContain('connection')
    media.retry(media.items[0]!.key)
    await settle()
    expect(uploads).toHaveLength(1)
    expect(uploads[0]?.start).toHaveBeenCalledOnce()
    expect(deps.addMedia).toHaveBeenCalledTimes(2)
    expect(addMedia.mock.calls[1]).toEqual(addMedia.mock.calls[0]) // the same media id again
    expect(media.items).toHaveLength(0)
  })

  it('shows the reason the server gave in words a person can act on', async () => {
    const refusal = new ApiError(409, { status: 409, code: 'locked', detail: 'x' })
    const { media } = setup({ addMedia: vi.fn().mockRejectedValue(refusal) as unknown as VisitMediaDeps['addMedia'] })
    media.add('s1', 'before', [photo()])
    await settle()
    expect(media.items[0]?.error).toBe('The visit report has been finalized. Ask an admin to reopen it.')
    const unknown = new ApiError(422, { status: 422, code: 'something_new', detail: 'The server’s own words.' })
    const other = setup({ addMedia: vi.fn().mockRejectedValue(unknown) as unknown as VisitMediaDeps['addMedia'] })
    other.media.add('s1', 'before', [photo()])
    await settle()
    expect(other.media.items[0]?.error).toBe('The server’s own words.')
  })

  it('removes an item and the half-sent file with it', async () => {
    const { media, uploads } = setup({ upload: vi.fn((file: File) => ({ ...fake(file, false) }) as unknown as Upload) })
    media.add('s1', 'before', [photo()])
    await settle()
    const key = media.items[0]!.key
    await media.discard(key)
    expect(media.items).toHaveLength(0)
    expect(uploads).toHaveLength(0)
  })

  it('cancels the upload of a discarded item on the server', async () => {
    const made: FakeUpload[] = []
    const { media } = setup({
      upload: vi.fn((file: File) => {
        const u = fake(file, false)
        made.push(u)
        return u as unknown as Upload
      }),
    })
    media.add('s1', 'before', [photo()])
    await settle()
    await media.discard(media.items[0]!.key)
    expect(made[0]?.cancel).toHaveBeenCalledWith(true)
  })

  it('works on two files at a time and starts the next when one finishes', async () => {
    const gates: (() => void)[] = []
    const { media, deps } = setup({
      upload: vi.fn((file: File) => {
        const u = fake(file)
        u.start.mockImplementation(async () => {
          await new Promise<void>(resolve => gates.push(resolve))
          u.mediaId = 'm'
          return true
        })
        return u as unknown as Upload
      }),
    })
    media.add('s1', 'before', [photo('a.jpg'), photo('b.jpg'), photo('c.jpg')])
    await settle()
    expect(deps.upload).toHaveBeenCalledTimes(2)
    gates.shift()!()
    await settle()
    expect(deps.upload).toHaveBeenCalledTimes(3)
    for (const gate of gates.splice(0)) {
      gate()
    }
    await settle()
    expect(media.items).toHaveLength(0)
  })

  it('lists what is on its way for one station and phase', async () => {
    const { media } = setup({ upload: vi.fn((file: File) => fake(file, false) as unknown as Upload) })
    media.add('s1', 'before', [photo('a.jpg')])
    media.add('s1', 'after', [photo('b.jpg')])
    await settle()
    expect(media.forStation('s1').map(i => i.name)).toEqual(['a.jpg', 'b.jpg'])
    expect(media.forStation('s1', 'after').map(i => i.name)).toEqual(['b.jpg'])
    expect(media.forStation('s2')).toEqual([])
  })

  it('stops sending when the page goes away', async () => {
    const made: FakeUpload[] = []
    const { media } = setup({
      upload: vi.fn((file: File) => {
        const u = fake(file, false)
        made.push(u)
        return u as unknown as Upload
      }),
    })
    media.add('s1', 'before', [photo()])
    await settle()
    media.dispose()
    expect(made[0]?.dispose).toHaveBeenCalledOnce()
  })
})
