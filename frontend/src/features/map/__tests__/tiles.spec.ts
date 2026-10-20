import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CachedRangeSource } from '../tiles'

/** A Cache Storage that remembers in a Map, in insertion order like the real one. */
function fakeCaches (): { store: Map<string, ArrayBuffer>, open: ReturnType<typeof vi.fn> } {
  const store = new Map<string, ArrayBuffer>()
  const cache = {
    async match (key: string) {
      const hit = store.get(key)
      return hit ? new Response(hit.slice(0)) : undefined
    },
    async put (key: string, response: Response) {
      store.set(key, await response.arrayBuffer())
    },
    async keys () {
      return [...store.keys()]
    },
    async delete (key: string) {
      return store.delete(key)
    },
  }
  return { store, open: vi.fn(async () => cache) }
}

function partial (bytes: number, status = 206): Response {
  return new Response(new Uint8Array(bytes).fill(7), { status, headers: { etag: '"abc"' } })
}

describe('CachedRangeSource', () => {
  let caches: ReturnType<typeof fakeCaches>

  beforeEach(() => {
    caches = fakeCaches()
    vi.stubGlobal('caches', { open: caches.open })
  })

  it('asks for the byte range and keeps the answer', async () => {
    const fetchMock = vi.fn(async () => partial(100))
    vi.stubGlobal('fetch', fetchMock)
    const source = new CachedRangeSource('/tiles/a.pmtiles')

    const first = await source.getBytes(200, 100)
    expect(first.data.byteLength).toBe(100)
    expect(first.etag).toBe('"abc"')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/tiles\/a\.pmtiles$/)
    expect((init.headers as Record<string, string>).Range).toBe('bytes=200-299')
    expect([...caches.store.keys()]).toHaveLength(1)

    // The second time there is no network at all (a phone with no signal)
    const offline = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    vi.stubGlobal('fetch', offline)
    const again = await source.getBytes(200, 100)
    expect(again.data.byteLength).toBe(100)
    expect(offline).not.toHaveBeenCalled()
  })

  it('keys ranges by offset and length, so different ranges are different entries', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => partial(10)))
    const source = new CachedRangeSource('/tiles/a.pmtiles')
    await source.getBytes(0, 10)
    await source.getBytes(10, 10)
    expect(caches.store.size).toBe(2)
  })

  it('refuses a whole-file answer from a server that ignores Range', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => partial(100, 200)))
    await expect(new CachedRangeSource('/tiles/a.pmtiles').getBytes(0, 100)).rejects.toThrow(/206/)
    expect(caches.store.size).toBe(0)
  })

  it('does not keep a short answer, which would be served for ever', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => partial(40)))
    await expect(new CachedRangeSource('/tiles/a.pmtiles').getBytes(0, 100)).rejects.toThrow(/100 bytes/)
    expect(caches.store.size).toBe(0)
  })

  it('still answers when Cache Storage is missing or refuses', async () => {
    vi.stubGlobal('caches', undefined)
    vi.stubGlobal('fetch', vi.fn(async () => partial(10)))
    expect((await new CachedRangeSource('/tiles/a.pmtiles').getBytes(0, 10)).data.byteLength).toBe(10)

    vi.stubGlobal('caches', { open: vi.fn(async () => {
      throw new Error('SecurityError')
    }) })
    expect((await new CachedRangeSource('/tiles/a.pmtiles').getBytes(0, 10)).data.byteLength).toBe(10)
  })

  it('drops the oldest third once there are more than the limit', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => partial(1)))
    const source = new CachedRangeSource('/tiles/a.pmtiles')
    for (let i = 0; i < 9; i++) {
      await source.getBytes(i, 1)
    }
    await source.prune(20)
    expect(caches.store.size).toBe(9) // under the limit: nothing goes
    await source.prune(8)
    expect(caches.store.size).toBe(6)
    expect([...caches.store.keys()][0]).toMatch(/bytes=3-3$/) // the three oldest went
  })
})
