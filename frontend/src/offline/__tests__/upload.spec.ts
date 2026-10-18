import type { MediaDetail, UploadIn, UploadOut } from '@/api/models'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import { PartError } from '../transport'
import { type Progress, type UploadApi, type UploadDeps, UploadError, uploadFile, waitUntilChecked } from '../upload'

const MEDIA_ID = '01920000-0000-7000-8000-00000000aaaa'
const PART = 5

/** A stand-in for media: remembers which parts the "store" holds, like the real one. */
class FakeServer {
  stored = new Set<number>()
  status: UploadOut['status'] = 'pending'
  creates: UploadIn[] = []
  partCalls = 0
  completeCalls = 0
  size = 0
  mediaId = MEDIA_ID
  onComplete: (() => UploadOut) | null = null

  api: UploadApi = {
    create: async body => {
      this.creates.push(body)
      this.size = body.size_bytes
      return this.out()
    },
    parts: async () => {
      this.partCalls++
      return this.out()
    },
    complete: async () => {
      this.completeCalls++
      if (this.onComplete) {
        return this.onComplete()
      }
      this.status = 'uploaded'
      return this.out()
    },
    get: async () => {
      throw new Error('not used')
    },
  }

  out (): UploadOut {
    const count = Math.ceil(this.size / PART)
    const urls = Array.from({ length: count }, (_, i) => i + 1).filter(n => !this.stored.has(n)).map(n => ({ part_number: n, url: `https://files.test/${this.mediaId}/${n}?v=${this.partCalls}` }))
    return {
      media_id: this.mediaId, status: this.status, part_size: PART, part_count: count,
      parts_done: [...this.stored].toSorted((a, b) => a - b), urls, expires_at: null, resumed: false,
      media: {
        id: this.mediaId, owner_ref: 'document:station:s1', kind: 'pdf', filename: 'a.pdf', size_bytes: this.size,
        status: this.status, visibility: 'staff', created_at: '2026-10-19T09:00:00Z', updated_at: '2026-10-19T09:00:00Z',
      },
    }
  }
}

function file (size: number, name = 'a.pdf'): File {
  return new File([new Uint8Array(size).fill(7)], name, { type: 'application/pdf' })
}

function deps (server: FakeServer, extra: Partial<UploadDeps> = {}): UploadDeps & { sent: number[], sleeps: number[] } {
  const sent: number[] = []
  const sleeps: number[] = []
  const base: UploadDeps = {
    api: server.api,
    hash: async () => 'a'.repeat(64),
    sendPart: async (url, body, _signal, onProgress) => {
      const n = Number(new URL(url).pathname.split('/').at(-1))
      sent.push(n)
      onProgress(body.size)
      server.stored.add(n)
    },
    network: { ready: async () => {} },
    sleep: async ms => {
      sleeps.push(ms)
    },
    random: () => 0.5,
    newId: () => MEDIA_ID,
    lock: async (_name, run) => run(),
    ...extra,
  }
  return Object.assign(base, { sent, sleeps })
}

const request = (size: number) => ({ file: file(size), ownerRef: 'document:station:s1', kind: 'pdf' })

describe('uploadFile', () => {
  it('sends every part, joins them, and reports bytes up to the whole file', async () => {
    const server = new FakeServer()
    const d = deps(server)
    const seen: Progress[] = []
    const out = await uploadFile(request(12), d, new AbortController().signal, p => seen.push(p))
    expect(d.sent.toSorted()).toEqual([1, 2, 3])
    expect(server.completeCalls).toBe(1)
    expect(out.status).toBe('uploaded')
    expect(server.creates[0]).toMatchObject({ media_id: MEDIA_ID, owner_ref: 'document:station:s1', kind: 'pdf', filename: 'a.pdf', size_bytes: 12, sha256: 'a'.repeat(64) })
    expect(seen.map(p => p.phase)).toContain('sending')
    expect(seen.at(-1)).toMatchObject({ phase: 'done', sent: 12, total: 12, mediaId: MEDIA_ID })
    expect(Math.max(...seen.map(p => p.sent))).toBe(12)
  })

  it('carries on from the parts the store already holds', async () => {
    const server = new FakeServer()
    server.stored = new Set([1, 3])
    const d = deps(server)
    await uploadFile(request(12), d, new AbortController().signal)
    expect(d.sent).toEqual([2])
    expect(server.completeCalls).toBe(1)
  })

  it('cuts the file the way the server says, the last part short', async () => {
    const server = new FakeServer()
    const bodies: number[] = []
    const d = deps(server, {
      sendPart: async (url, body) => {
        bodies.push(body.size)
        server.stored.add(Number(url.split('/').pop()!.split('?', 1)[0]))
      },
    })
    await uploadFile(request(12), d, new AbortController().signal)
    expect(bodies.toSorted()).toEqual([2, 5, 5])
  })

  it('uses the media_id the server answers with when it joined an open upload', async () => {
    const server = new FakeServer()
    server.mediaId = '01920000-0000-7000-8000-00000000bbbb'
    const seen: Progress[] = []
    await uploadFile(request(5), deps(server), new AbortController().signal, p => seen.push(p))
    expect(seen.at(-1)?.mediaId).toBe(server.mediaId)
  })

  it('waits for the connection and backs off before trying a part again', async () => {
    const server = new FakeServer()
    let failures = 2
    const ready = vi.fn(async () => {})
    const d = deps(server, {
      network: { ready },
      sendPart: async url => {
        if (failures-- > 0) {
          throw new PartError(0)
        }
        server.stored.add(Number(url.split('/').pop()!.split('?', 1)[0]))
      },
    })
    await uploadFile(request(5), d, new AbortController().signal)
    expect(ready).toHaveBeenCalledTimes(2)
    expect(d.sleeps).toEqual([500, 1000]) // random()=0.5 of 1 s then 2 s
    expect(server.completeCalls).toBe(1)
  })

  it('asks for fresh URLs when a part is refused as expired, then sends it', async () => {
    const server = new FakeServer()
    const urls: string[] = []
    let refused = true
    const d = deps(server, {
      sendPart: async url => {
        urls.push(url)
        if (refused) {
          refused = false
          throw new PartError(403)
        }
        server.stored.add(1)
      },
    })
    await uploadFile(request(5), d, new AbortController().signal)
    expect(server.partCalls).toBe(1)
    expect(urls[0]).not.toBe(urls[1]) // the second try used the refreshed URL
  })

  it('stops asking for a part the store turns out to hold already', async () => {
    const server = new FakeServer()
    let calls = 0
    const d = deps(server, {
      sendPart: async () => {
        calls++
        server.stored.add(1) // it did arrive, but the answer was lost
        throw new PartError(403)
      },
    })
    await uploadFile(request(5), d, new AbortController().signal)
    expect(calls).toBe(1)
  })

  it('sends the parts the store says are missing when complete finds a gap', async () => {
    const server = new FakeServer()
    let first = true
    server.onComplete = () => {
      if (first) {
        first = false
        server.stored.delete(2) // the store lost a part
        throw new ApiError(409, { code: 'conflict', reason: 'incomplete_upload', detail: 'Some parts have not arrived' })
      }
      server.status = 'uploaded'
      return server.out()
    }
    const d = deps(server)
    const out = await uploadFile(request(10), d, new AbortController().signal)
    expect(d.sent.toSorted()).toEqual([1, 2, 2])
    expect(server.completeCalls).toBe(2)
    expect(out.status).toBe('uploaded')
  })

  it('fails for good when the server says the file is not the size announced', async () => {
    const server = new FakeServer()
    server.onComplete = () => {
      throw new ApiError(409, { code: 'conflict', reason: 'size_mismatch', detail: 'Wrong size' })
    }
    const error = await uploadFile(request(5), deps(server), new AbortController().signal).catch(error_ => error_)
    expect(error).toBeInstanceOf(UploadError)
    expect(error).toMatchObject({ kind: 'failed', reason: 'size_mismatch' })
  })

  it('does not retry a refusal from the store', async () => {
    const server = new FakeServer()
    const d = deps(server, { sendPart: async () => {
      throw new PartError(400)
    } })
    const error = await uploadFile(request(5), d, new AbortController().signal).catch(error_ => error_)
    expect(error).toMatchObject({ kind: 'failed', reason: 'store_refused' })
    expect(d.sleeps).toEqual([])
  })

  it('stalls, safe to try again, once the retries run out', async () => {
    const server = new FakeServer()
    const d = deps(server, { attempts: 3, sendPart: async () => {
      throw new PartError(503)
    } })
    const error = await uploadFile(request(5), d, new AbortController().signal).catch(error_ => error_)
    expect(error).toMatchObject({ kind: 'stalled' })
    expect(server.completeCalls).toBe(0)
  })

  it('rides out a server error when creating the upload', async () => {
    const server = new FakeServer()
    const real = server.api.create
    let bad = 2
    server.api.create = async (body, signal) => {
      if (bad-- > 0) {
        throw bad === 0 ? new NetworkError(new Error('reset')) : new ApiError(503, { code: 'owner_unavailable' })
      }
      return real(body, signal)
    }
    const d = deps(server)
    await uploadFile(request(5), d, new AbortController().signal)
    expect(d.sleeps).toHaveLength(2)
  })

  it('passes a 4xx on creating straight to the caller', async () => {
    const server = new FakeServer()
    server.api.create = async () => {
      throw new ApiError(422, { code: 'validation_failed', reason: 'too_large', detail: 'Too big' })
    }
    const error = await uploadFile(request(5), deps(server), new AbortController().signal).catch(error_ => error_)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.reason).toBe('too_large')
  })

  it('never has more parts in flight than the limit', async () => {
    const server = new FakeServer()
    let live = 0
    let peak = 0
    const d = deps(server, {
      concurrency: 2,
      sendPart: async url => {
        live++
        peak = Math.max(peak, live)
        await new Promise(r => setTimeout(r, 5))
        live--
        server.stored.add(Number(url.split('/').pop()!.split('?', 1)[0]))
      },
    })
    await uploadFile(request(25), d, new AbortController().signal)
    expect(peak).toBe(2)
  })

  it('stops when the caller aborts', async () => {
    const server = new FakeServer()
    const controller = new AbortController()
    const d = deps(server, {
      sendPart: async () => {
        controller.abort()
        throw new DOMException('Aborted', 'AbortError')
      },
    })
    const error = await uploadFile(request(5), d, controller.signal).catch(error_ => error_)
    expect(error).toBeInstanceOf(DOMException)
    expect(server.completeCalls).toBe(0)
  })

  it('refuses a second upload of the same file while another tab has it', async () => {
    const server = new FakeServer()
    const d = deps(server, { lock: async () => null })
    const error = await uploadFile(request(5), d, new AbortController().signal).catch(error_ => error_)
    expect(error).toMatchObject({ kind: 'busy' })
    expect(server.creates).toEqual([])
  })

  it('returns at once when the server already holds the whole file', async () => {
    const server = new FakeServer()
    server.status = 'ready'
    const d = deps(server)
    const out = await uploadFile(request(5), d, new AbortController().signal)
    expect(out.status).toBe('ready')
    expect(d.sent).toEqual([])
    expect(server.completeCalls).toBe(0)
  })
})

describe('waitUntilChecked', () => {
  function detail (status: string, error?: string): MediaDetail {
    return { id: MEDIA_ID, owner_ref: 'x:y', kind: 'pdf', filename: 'a.pdf', size_bytes: 1, status, visibility: 'staff', error, urls: {}, created_at: '', updated_at: '' } as MediaDetail
  }

  it('polls until the file is ready', async () => {
    const answers = [detail('uploaded'), detail('processing'), detail('ready')]
    const get = vi.fn(async () => answers.shift()!)
    const d = deps(new FakeServer(), { api: { ...new FakeServer().api, get } })
    const out = await waitUntilChecked(MEDIA_ID, d, new AbortController().signal)
    expect(out.status).toBe('ready')
    expect(get).toHaveBeenCalledTimes(3)
    expect(d.sleeps).toHaveLength(2)
  })

  it('says why a file failed its checks', async () => {
    const get = async () => detail('failed', 'infected')
    const d = deps(new FakeServer(), { api: { ...new FakeServer().api, get } })
    const error = await waitUntilChecked(MEDIA_ID, d, new AbortController().signal).catch(error_ => error_)
    expect(error).toMatchObject({ kind: 'failed', reason: 'infected' })
  })

  it('waits out a lost connection while polling', async () => {
    const answers: Array<() => MediaDetail> = [() => {
      throw new NetworkError(new Error('x'))
    }, () => detail('ready')]
    const get = async () => answers.shift()!()
    const ready = vi.fn(async () => {})
    const d = deps(new FakeServer(), { api: { ...new FakeServer().api, get }, network: { ready } })
    expect((await waitUntilChecked(MEDIA_ID, d, new AbortController().signal)).status).toBe('ready')
    expect(ready).toHaveBeenCalledTimes(1)
  })

  it('gives up when the checks take far too long', async () => {
    const get = async () => detail('processing')
    const d = deps(new FakeServer(), { api: { ...new FakeServer().api, get }, checkTimeoutMs: -1 })
    const error = await waitUntilChecked(MEDIA_ID, d, new AbortController().signal).catch(error_ => error_)
    expect(error).toMatchObject({ kind: 'stalled' })
  })
})
