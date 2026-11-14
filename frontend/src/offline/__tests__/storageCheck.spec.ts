// Node's own File, because fake-indexeddb clones a jsdom File into an empty object
import { File as NodeFile } from 'node:buffer'
import { afterEach, describe, expect, it } from 'vitest'
import { MmsDb } from '../db'
import { addFiles, clear, MAX_FILES, stored, summarize, verify } from '../storageCheck'

// The storage check (R4, F3): test files kept in `blobs`, read back after a restart.

const opened: MmsDb[] = []
let n = 0
function open (): MmsDb {
  const store = new MmsDb(`check-${n++}`)
  opened.push(store)
  return store
}
afterEach(async () => {
  for (const store of opened.splice(0)) {
    store.close()
    await store.delete()
  }
})

const make = (parts: string[], name: string, type: string): File => new NodeFile(parts, name, { type }) as unknown as File
const photo = (name: string) => make(['photo-bytes'], name, 'image/jpeg')
const video = (name: string) => make(['video-bytes-video'], name, 'video/mp4')

describe('summarize', () => {
  it('counts photos, videos and the rest, with the bytes', () => {
    const list = [photo('a.jpg'), video('b.mp4'), make(['x'], 'c.bin', '')].map(file => ({ file, size: file.size }))
    expect(summarize(list)).toEqual({ photos: 1, videos: 1, other: 1, bytes: 11 + 17 + 1 })
  })
})

describe('adding and clearing', () => {
  it('stores each file as a diagnostic blob for this user', async () => {
    const store = open()
    const added = await addFiles('u1', [photo('a.jpg'), video('b.mp4')], undefined, store)
    expect(added).toBe(2)
    const rows = await store.blobs.toArray()
    expect(rows.map(r => r.state)).toEqual(['diagnostic', 'diagnostic'])
    expect(rows.every(r => r.user_id === 'u1' && r.sha256.length === 64)).toBe(true)
    expect(await stored('u1', store)).toMatchObject({ photos: 1, videos: 1 })
    expect(await stored('u2', store)).toMatchObject({ photos: 0, videos: 0 })
  })

  it('stops at sixty files in all', async () => {
    const store = open()
    const many = Array.from({ length: MAX_FILES + 5 }, (_, i) => photo(`p${i}.jpg`))
    expect(await addFiles('u1', many, undefined, store)).toBe(MAX_FILES)
    expect(await addFiles('u1', [photo('late.jpg')], undefined, store)).toBe(0)
  })

  it('removes only this user’s test files, and nothing queued for upload', async () => {
    const store = open()
    await addFiles('u1', [photo('a.jpg')], undefined, store)
    await addFiles('u2', [photo('b.jpg')], undefined, store)
    await store.blobs.put({ media_id: 'real', user_id: 'u1', owner_ref: 'visit:v1', file: new Blob(['x']), size: 1, sha256: 'a'.repeat(64), state: 'pending' })
    await clear('u1', store)
    expect((await store.blobs.toArray()).map(r => r.media_id).toSorted()).toHaveLength(2)
    expect((await stored('u1', store)).photos).toBe(0)
    expect((await stored('u2', store)).photos).toBe(1)
    expect(await store.blobs.get('real')).toBeDefined()
  })
})

describe('verify', () => {
  it('finds every file matching when nothing changed', async () => {
    const store = open()
    await addFiles('u1', [photo('a.jpg'), video('b.mp4')], undefined, store)
    expect(await verify('u1', undefined, store, 5)).toEqual({ checked: 2, matching: 2, failed: [], at: 5 })
  })

  it('names a file whose bytes no longer match, and one that went missing is simply not there', async () => {
    const store = open()
    await addFiles('u1', [photo('a.jpg'), video('b.mp4')], undefined, store)
    const [first] = await store.blobs.toArray()
    await store.blobs.update(first!.media_id, { file: make(['damaged'], 'x', 'image/jpeg') })
    const verdict = await verify('u1', undefined, store)
    expect(verdict.checked).toBe(2)
    expect(verdict.matching).toBe(1)
    expect(verdict.failed).toHaveLength(1)
  })

  it('reports progress', async () => {
    const store = open()
    await addFiles('u1', [photo('a.jpg'), photo('b.jpg')], undefined, store)
    const seen: number[] = []
    await verify('u1', done => seen.push(done), store)
    expect(seen).toEqual([1, 2])
  })
})
