import type { Source } from '../bundles'
import type { BundleFile, FieldBundle } from '@/api/models'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BundleTooNew, prepareVisit, SUPPORTED_BUNDLE_VERSION } from '../bundles'
import { MmsDb } from '../db'
import { sha256Hex } from '../hash'

// Prepare for field (OFF-1, W13-9 to W13-11): what is stored, what resumes, what makes a visit ready.

const opened: MmsDb[] = []
let n = 0
function open (): MmsDb {
  const store = new MmsDb(`bundles-${n++}`)
  opened.push(store)
  return store
}
afterEach(async () => {
  for (const store of opened.splice(0)) {
    store.close()
    await store.delete()
  }
})

const VISIT = '01990000-0000-7000-8000-0000000000a1'
const common = { visitId: VISIT, userId: 'u1', deviceId: 'd1' }

function file (media_id: string, over: Partial<BundleFile> = {}): BundleFile {
  return {
    kind: 'document', media_id, document_id: `doc-${media_id}`, station_id: 's1',
    name: `${media_id}.pdf`, size: 5, sha256: null, required: false, ...over,
  }
}

function bundleWith (files: BundleFile[], version = 1): FieldBundle {
  return { bundle_version: version, prepared_at: '2026-10-22T08:00:00Z', files, visit: { id: VISIT }, stations: [] } as unknown as FieldBundle
}

/** A server whose files are `size` bytes of their own ID; `fail` names the ones that break. */
function source (bundle: FieldBundle, fail: ReadonlySet<string> = new Set()): Source & { links: string[] } {
  const links: string[] = []
  return {
    links,
    bundle: vi.fn(async () => bundle),
    link: async f => {
      links.push(f.media_id)
      return `https://files.test/${f.media_id}`
    },
    download: async (url, onBytes) => {
      const id = url.split('/').pop()!
      if (fail.has(id)) {
        throw new TypeError('Failed to fetch')
      }
      const f = bundle.files.find(x => x.media_id === id)!
      const text = id.padEnd(f.size, 'x').slice(0, f.size)
      onBytes(f.size)
      return new Blob([text], { type: 'application/pdf' })
    },
  }
}

describe('prepareVisit', () => {
  it('stores the bundle, the required files and the documents that were ticked, and is ready', async () => {
    const store = open()
    const bundle = bundleWith([file('cfg', { kind: 'config', required: true, name: 'logger.cfg' }), file('man'), file('draw')])
    const outcome = await prepareVisit(source(bundle), { ...common, documents: new Set(['man']), store })

    expect(outcome).toEqual({ ready: true, missing: [], requiredMissing: false })
    const row = await store.bundles.get(VISIT)
    expect(row).toMatchObject({ user_id: 'u1', ready: true, files_total: 2, files_done: 2, bundle_version: 1 })
    expect((await store.files.toArray()).map(f => f.media_id).toSorted()).toEqual(['cfg', 'man'])
    const cfg = await store.files.get([VISIT, 'cfg'])
    expect(cfg).toMatchObject({ name: 'logger.cfg', size: 5, required: true, user_id: 'u1' })
    // fake-indexeddb clones a jsdom Blob to an empty object, so only its presence is checked here
    expect(cfg!.blob).toBeDefined()
  })

  it('reports progress by file and by bytes', async () => {
    const store = open()
    const seen: { filesDone: number, bytesDone: number, current: string | null }[] = []
    await prepareVisit(source(bundleWith([file('a'), file('b', { size: 7 })])), {
      ...common, documents: new Set(['a', 'b']), store, onProgress: p => seen.push(p),
    })
    const last = seen.at(-1)!
    expect(last).toMatchObject({ filesDone: 2, filesTotal: 2, bytesDone: 12, bytesTotal: 12, current: null })
    expect(seen.some(p => p.current === 'a.pdf')).toBe(true)
  })

  it('is ready without a document that failed, and lists it so it can be fetched again', async () => {
    const store = open()
    const bundle = bundleWith([file('cfg', { required: true, kind: 'config' }), file('man'), file('draw')])
    const outcome = await prepareVisit(source(bundle, new Set(['draw'])), { ...common, documents: new Set(['man', 'draw']), store })
    expect(outcome.ready).toBe(true)
    expect(outcome.requiredMissing).toBe(false)
    expect(outcome.missing.map(f => f.media_id)).toEqual(['draw'])
    expect(await store.bundles.get(VISIT)).toMatchObject({ ready: true, files_total: 3, files_done: 2 })
  })

  it('is not ready when a configuration file did not come', async () => {
    const store = open()
    const bundle = bundleWith([file('cfg', { required: true, kind: 'config' }), file('man')])
    const outcome = await prepareVisit(source(bundle, new Set(['cfg'])), { ...common, documents: new Set(['man']), store })
    expect(outcome).toMatchObject({ ready: false, requiredMissing: true })
    expect((await store.bundles.get(VISIT))!.ready).toBe(false)
    expect(await store.files.count()).toBe(1) // the document that did come is kept
  })

  it('on a second run fetches only what is missing', async () => {
    const store = open()
    const bundle = bundleWith([file('cfg', { required: true, kind: 'config' }), file('man'), file('draw')])
    const all = new Set(['man', 'draw'])
    await prepareVisit(source(bundle, new Set(['draw'])), { ...common, documents: all, store })
    const again = source(bundle)
    const outcome = await prepareVisit(again, { ...common, documents: all, store })
    expect(again.links).toEqual(['draw'])
    expect(outcome).toEqual({ ready: true, missing: [], requiredMissing: false })
    expect(await store.files.count()).toBe(3)
    expect(await store.bundles.get(VISIT)).toMatchObject({ files_done: 3, files_total: 3 })
  })

  it('refuses a file that arrives with the wrong size or checksum', async () => {
    const store = open()
    const bundle = bundleWith([
      file('big', { size: 9 }),
      file('sum', { sha256: 'a'.repeat(64) }),
    ])
    const wrong = source(bundle)
    wrong.download = async (_u, onBytes) => {
      onBytes(5)
      return new Blob(['12345'])
    }
    const outcome = await prepareVisit(wrong, { ...common, documents: new Set(['big', 'sum']), store })
    expect(outcome.missing.map(f => f.media_id)).toEqual(['big', 'sum'])
    expect(await store.files.count()).toBe(0)
  })

  it('accepts a configuration file whose checksum matches', async () => {
    const store = open()
    const blob = new Blob(['12345'])
    const sha = await sha256Hex(blob)
    const bundle = bundleWith([file('cfg', { required: true, kind: 'config', sha256: sha })])
    const s = source(bundle)
    s.download = async (_u, onBytes) => {
      onBytes(5)
      return blob
    }
    expect((await prepareVisit(s, { ...common, documents: new Set(), store })).ready).toBe(true)
  })

  it('refuses a bundle from a newer app version', async () => {
    const store = open()
    await expect(prepareVisit(source(bundleWith([], SUPPORTED_BUNDLE_VERSION + 1)), { ...common, documents: new Set(), store }))
      .rejects
      .toBeInstanceOf(BundleTooNew)
    expect(await store.bundles.count()).toBe(0)
  })

  it('stops when asked, keeping what already arrived', async () => {
    const store = open()
    const controller = new AbortController()
    const bundle = bundleWith([file('a'), file('b')])
    const s = source(bundle)
    const real = s.download
    s.download = async (url, onBytes, signal) => {
      const blob = await real(url, onBytes, signal)
      controller.abort()
      return blob
    }
    await expect(prepareVisit(s, { ...common, documents: new Set(['a', 'b']), store, signal: controller.signal })).rejects.toThrow()
    expect(await store.files.count()).toBe(1)
    expect((await store.bundles.get(VISIT))!.ready).toBe(false)
  })

  it('stops with the phone-is-full error rather than listing every file as missing', async () => {
    const store = open()
    const s = source(bundleWith([file('a')]))
    s.download = async () => {
      throw new DOMException('full', 'QuotaExceededError')
    }
    await expect(prepareVisit(s, { ...common, documents: new Set(['a']), store })).rejects.toMatchObject({ name: 'QuotaExceededError' })
  })

  it('does not mix up another visit with the same document', async () => {
    const store = open()
    await store.files.put({ media_id: 'a', visit_id: 'other', user_id: 'u1', station_id: null, name: 'a.pdf', size: 5, content_type: 'application/pdf', required: false, blob: new Blob(['12345']) })
    const s = source(bundleWith([file('a')]))
    await prepareVisit(s, { ...common, documents: new Set(['a']), store })
    expect(s.links).toEqual(['a'])
    expect(await store.files.count()).toBe(2)
  })
})
