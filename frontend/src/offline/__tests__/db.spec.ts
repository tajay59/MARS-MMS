import { afterEach, describe, expect, it } from 'vitest'
import { UUID7 } from '@/app/ids'
import { deviceId, getMeta, MmsDb, setMeta } from '../db'

// The phone's store (TRD §7.1, W13-1): six tables, per-user rows, a stable device ID.

const opened: MmsDb[] = []
let n = 0

function open (name = `test-${n++}`): MmsDb {
  const store = new MmsDb(name)
  opened.push(store)
  return store
}

afterEach(async () => {
  for (const store of opened.splice(0)) {
    store.close()
    await store.delete()
  }
})

function op (op_id: string, user_id = 'u1') {
  return {
    op_id,
    v: 1,
    user_id,
    visit_id: 'v1',
    type: 'visit.start',
    payload: {},
    created_at: '2026-10-22T08:00:00Z',
    attempts: 0,
    status: 'pending' as const,
  }
}

describe('the schema', () => {
  it('has the six tables of the design', () => {
    expect(open().tables.map(t => t.name).toSorted()).toEqual(['blobs', 'bundles', 'files', 'meta', 'outbox', 'visits'])
  })

  it('keeps queued work and media across a reopen (nothing is lost by closing the app)', async () => {
    const first = open('keep')
    await first.outbox.add(op('o1'))
    await first.blobs.add({
      media_id: 'm1',
      user_id: 'u1',
      owner_ref: 'visit:v1',
      file: new Blob(['x']),
      size: 1,
      sha256: 'abc',
      state: 'pending',
    })
    first.close()

    const second = open('keep')
    expect(await second.outbox.count()).toBe(1)
    expect((await second.blobs.get('m1'))?.size).toBe(1)
  })

  it('orders the outbox by its local sequence and refuses a repeated op_id', async () => {
    const store = open()
    await store.outbox.bulkAdd([op('b'), op('a'), op('c')])
    expect((await store.outbox.orderBy('seq').toArray()).map(o => o.op_id)).toEqual(['b', 'a', 'c'])
    await expect(store.outbox.add(op('a'))).rejects.toThrow()
    expect(await store.outbox.count()).toBe(3)
  })

  it('finds one user’s operations for one visit', async () => {
    const store = open()
    await store.outbox.bulkAdd([op('a'), op('b', 'u2')])
    const mine = await store.outbox.where('[user_id+visit_id]').equals(['u1', 'v1']).toArray()
    expect(mine.map(o => o.op_id)).toEqual(['a'])
  })

  it('stores the same document for two prepared visits', async () => {
    const store = open()
    const file = (visit_id: string) => ({
      media_id: 'm1',
      visit_id,
      user_id: 'u1',
      station_id: 's1',
      name: 'config.json',
      size: 1,
      content_type: 'application/json',
      required: true,
      blob: new Blob(['x']),
    })
    await store.files.bulkAdd([file('v1'), file('v2')])
    expect(await store.files.count()).toBe(2)
    expect(await store.files.where('media_id').equals('m1').count()).toBe(2)
  })
})

describe('meta and the device ID', () => {
  it('reads and writes a value', async () => {
    const store = open()
    expect(await getMeta('x', store)).toBeUndefined()
    await setMeta('x', { a: 1 }, store)
    expect(await getMeta('x', store)).toEqual({ a: 1 })
  })

  it('makes one UUIDv7 and keeps it, even when asked at the same moment', async () => {
    const store = open()
    const ids = await Promise.all([deviceId(store), deviceId(store), deviceId(store)])
    expect(new Set(ids).size).toBe(1)
    expect(ids[0]).toMatch(UUID7)
    expect(await deviceId(store)).toBe(ids[0])
  })
})
