import type { MediaDetail, UploadIn, UploadOut } from '@/api/models'
import type { UploadApi, UploadDeps } from '@/offline/upload'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/problem'
import { createUpload } from '../useUpload'

const remove = vi.fn(async (_id: string) => {})
vi.mock('@/api/media', () => ({
  mediaApi: { remove: (id: string) => remove(id), get: vi.fn() },
  uploadsApi: {},
}))

const MEDIA_ID = '01920000-0000-7000-8000-00000000aaaa'

function out (status: string, size = 8): UploadOut {
  return {
    media_id: MEDIA_ID,
    status,
    part_size: 8,
    part_count: 1,
    parts_done: status === 'pending' ? [] : [1],
    urls: status === 'pending' ? [{ part_number: 1, url: 'https://files.test/1' }] : [],
    expires_at: null,
    resumed: false,
    media: { id: MEDIA_ID, owner_ref: 'config:s1', kind: 'config', filename: 'a.cfg', size_bytes: size, status, visibility: 'staff', created_at: '', updated_at: '' },
  }
}

function detail (status: string, error?: string): MediaDetail {
  return { id: MEDIA_ID, owner_ref: 'config:s1', kind: 'config', filename: 'a.cfg', size_bytes: 8, status, visibility: 'staff', created_at: '', updated_at: '', error }
}

function problem (detailText: string, reason?: string): ApiError {
  return new ApiError(422, { type: 'about:blank', title: 'No', status: 422, detail: detailText, reason })
}

function deps (api: Partial<UploadApi>): Partial<UploadDeps> {
  return {
    api: {
      create: async () => out('pending'),
      parts: async () => out('pending'),
      complete: async () => out('uploaded'),
      get: async () => detail('ready'),
      ...api,
    },
    hash: async () => 'a'.repeat(64),
    sendPart: async (_url, body, _signal, onProgress) => onProgress(body.size),
    network: { ready: async () => {} },
    sleep: async () => {},
    lock: async (_name, run) => run(),
  }
}

const file = () => new File([new Uint8Array(8)], 'a.cfg')

beforeEach(() => remove.mockClear())

describe('createUpload', () => {
  it('is ready once the bytes are up and media has passed the file', async () => {
    const upload = createUpload(file(), { ownerRef: 'config:s1', kind: 'config', untilChecked: true, deps: deps({}) })
    expect(await upload.start()).toBe(true)
    expect(upload.state).toBe('ready')
    expect(upload.mediaId).toBe(MEDIA_ID)
    expect(upload.sent).toBe(8)
    expect(upload.error).toBeNull()
  })

  it('stops at arrived when the checks are not waited for (documents)', async () => {
    const get = vi.fn(async () => detail('ready'))
    const upload = createUpload(file(), { ownerRef: 'document:station:s1', kind: 'pdf', deps: deps({ get }) })
    expect(await upload.start()).toBe(true)
    expect(upload.state).toBe('arrived')
    expect(get).not.toHaveBeenCalled()
  })

  it('says why a file failed its checks', async () => {
    const upload = createUpload(file(), {
      ownerRef: 'config:s1',
      kind: 'config',
      untilChecked: true,
      deps: deps({ get: async () => detail('failed', 'infected') }),
    })
    expect(await upload.start()).toBe(false)
    expect(upload.state).toBe('failed')
    expect(upload.error).toMatch(/virus/)
  })

  it('shows the words of the server when it refuses the upload', async () => {
    const upload = createUpload(file(), {
      ownerRef: 'config:s1',
      kind: 'config',
      deps: deps({ create: async () => {
        throw problem('Config files can be up to 50 MB')
      } }),
    })
    expect(await upload.start()).toBe(false)
    expect(upload.error).toBe('Config files can be up to 50 MB')
  })

  it('joins the same server upload when started again after a failure', async () => {
    const create = vi.fn(async (_body: UploadIn) => out('pending'))
    let first = true
    const upload = createUpload(file(), {
      ownerRef: 'config:s1',
      kind: 'config',
      deps: deps({
        create,
        complete: async () => {
          if (first) {
            first = false
            throw problem('No', 'bad_type')
          }
          return out('uploaded')
        },
      }),
    })
    expect(await upload.start()).toBe(false)
    upload.reset()
    expect(upload.state).toBe('idle')
    expect(await upload.start()).toBe(true)
    // The second try asked for the ID the first one got
    expect(create.mock.calls[1]![0]).toMatchObject({ media_id: MEDIA_ID })
  })

  it('takes a cancelled file off the server', async () => {
    const upload = createUpload(file(), { ownerRef: 'config:s1', kind: 'config', deps: deps({}) })
    await upload.start()
    await upload.cancel()
    expect(upload.state).toBe('cancelled')
    expect(remove).toHaveBeenCalledWith(MEDIA_ID)
  })

  it('leaves the server alone when a page is only going away', async () => {
    const upload = createUpload(file(), { ownerRef: 'config:s1', kind: 'config', deps: deps({}) })
    await upload.start()
    upload.dispose()
    expect(remove).not.toHaveBeenCalled()
  })
})
