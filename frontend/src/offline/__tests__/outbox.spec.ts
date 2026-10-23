import Dexie from 'dexie'
import { afterEach, describe, expect, it } from 'vitest'
import { MmsDb } from '../db'
import { arriveOp, createElementOp, mediaAddOp, OP_VERSION, startOp, wire } from '../ops'
import {
  applyAnswers,
  attention,
  backoffMs,
  blockedVisits,
  counts,
  enqueue,
  retryStuck,
  sendable,
} from '../outbox'

// The outbox (TRD §7.1, §7.2; W14-8 to W14-10): a change and its op are written together or not
// at all, in order, per user; answers come back as removal, a kept conflict or a backoff.

const opened: MmsDb[] = []
let n = 0
function open (name = `outbox-${n++}`): MmsDb {
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

const A = { userId: 'u1', visitId: 'v1' }
const B = { userId: 'u2', visitId: 'v9' }
const AT = '2026-10-22T08:00:00Z'
const NOW = 1_000_000

const element = { id: 'e1', kind: 'note', title: 'Rust', items: [], shared: false }

describe('the database at version 2', () => {
  it('keeps what was queued under version 1', async () => {
    const name = `upgrade-${n++}`
    const old = new Dexie(name)
    old.version(1).stores({
      bundles: 'visit_id, user_id',
      files: '[visit_id+media_id], media_id, user_id',
      visits: 'id, user_id',
      outbox: '++seq, &op_id, user_id, [user_id+visit_id], status',
      blobs: 'media_id, user_id, state',
      meta: 'key',
    })
    await old.open()
    await old.table('outbox').add({ op_id: 'o1', v: 1, user_id: 'u1', visit_id: 'v1', type: 'visit.start', payload: {}, created_at: AT, attempts: 0, status: 'pending' })
    await old.table('blobs').add({ media_id: 'b1', user_id: 'u1', owner_ref: 'x', file: new Blob(['x']), size: 1, sha256: 'a', state: 'pending' })
    await old.table('visits').add({ id: 'e1', user_id: 'u1', data: {} })
    old.close()

    const store = open(name)
    expect(await store.outbox.count()).toBe(1)
    expect((await store.blobs.get('b1'))?.size).toBe(1)
    expect(await store.visits.get('e1')).toBeDefined()
    // ... and the new indexes work on the old rows
    expect(await store.outbox.where('[user_id+status]').equals(['u1', 'pending']).count()).toBe(1)
    await store.visits.update('e1', { visit_id: 'v1', station_id: 's1' })
    expect(await store.visits.where('[visit_id+station_id]').equals(['v1', 's1']).count()).toBe(1)
  })
})

describe('the op builders', () => {
  it('make an op with its own ID, version and status, and the wire form drops the rest', () => {
    const op = createElementOp(A, 's1', element)
    expect(op).toMatchObject({ v: OP_VERSION, user_id: 'u1', visit_id: 'v1', type: 'element.create', status: 'pending', attempts: 0 })
    expect(op.payload).toMatchObject({ station_id: 's1', id: 'e1', title: 'Rust' })
    expect(op.op_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7/)
    expect(createElementOp(A, 's1', element).op_id).not.toBe(op.op_id)
    expect(Object.keys(wire({ ...op, seq: 3 })).toSorted()).toEqual(['op_id', 'payload', 'type', 'v', 'visit_id'])
  })

  it('make a media op wait for its file', () => {
    const op = mediaAddOp(A, 's1', 'e1', { mediaId: 'm1', section: 'main' })
    expect(op.blob_id).toBe('m1')
    expect(op.payload).toMatchObject({ media_id: 'm1', section: 'main', caption: null })
  })
})

describe('enqueue', () => {
  it('writes the change and its ops together, in order', async () => {
    const store = open()
    await enqueue([startOp(A, AT), arriveOp(A, 's1', AT)], async () => {
      await store.visits.put({ id: 'visit:v1', user_id: 'u1', visit_id: 'v1', data: { started: true }, dirty: true })
    }, store)
    expect((await store.outbox.orderBy('seq').toArray()).map(o => o.type)).toEqual(['visit.start', 'station.arrive'])
    expect((await store.visits.get('visit:v1'))?.dirty).toBe(true)
  })

  it('writes neither when something fails inside', async () => {
    const store = open()
    await expect(enqueue([startOp(A, AT)], async () => {
      await store.visits.put({ id: 'visit:v1', user_id: 'u1', data: {} })
      throw new Error('killed halfway')
    }, store)).rejects.toThrow('killed halfway')
    expect(await store.outbox.count()).toBe(0)
    expect(await store.visits.count()).toBe(0)
  })

  it('writes neither when the op cannot be added (a repeated op ID)', async () => {
    const store = open()
    const op = startOp(A, AT)
    await enqueue([op], undefined, store)
    await expect(enqueue([op], async () => {
      await store.visits.put({ id: 'visit:v1', user_id: 'u1', data: {} })
    }, store)).rejects.toThrow()
    expect(await store.visits.count()).toBe(0)
    expect(await store.outbox.count()).toBe(1)
  })
})

describe('what can be sent', () => {
  it('lists each user’s waiting ops by visit, in the order they were made', async () => {
    const store = open()
    await enqueue([startOp(A, AT), startOp(B, AT), arriveOp(A, 's1', AT)], undefined, store)
    const mine = await sendable('u1', NOW, false, store)
    expect([...mine.keys()]).toEqual(['v1'])
    expect(mine.get('v1')!.map(o => o.type)).toEqual(['visit.start', 'station.arrive'])
    expect([...(await sendable('u2', NOW, false, store)).keys()]).toEqual(['v9'])
  })

  it('leaves out a visit that has a conflict or a refusal, and no other', async () => {
    const store = open()
    const other = { userId: 'u1', visitId: 'v2' }
    await enqueue([startOp(A, AT), arriveOp(A, 's1', AT), startOp(other, AT)], undefined, store)
    const [first] = await store.outbox.orderBy('seq').toArray()
    await store.outbox.update(first!.seq!, { status: 'conflict', code: 'not_owner' })
    expect([...(await sendable('u1', NOW, false, store)).keys()]).toEqual(['v2'])
    expect([...await blockedVisits('u1', store)]).toEqual(['v1'])
  })

  it('holds the ops behind one that is still waiting out its backoff, until Sync now', async () => {
    const store = open()
    await enqueue([startOp(A, AT), arriveOp(A, 's1', AT)], undefined, store)
    const [first] = await store.outbox.orderBy('seq').toArray()
    await store.outbox.update(first!.seq!, { next_at: NOW + 60_000, attempts: 1 })
    expect((await sendable('u1', NOW, false, store)).size).toBe(0)
    expect((await sendable('u1', NOW + 61_000, false, store)).get('v1')).toHaveLength(2)
    expect((await sendable('u1', NOW, true, store)).get('v1')).toHaveLength(2)
  })
})

describe('applying the answers', () => {
  async function queued (store: MmsDb, ...ops: ReturnType<typeof startOp>[]) {
    await enqueue(ops, undefined, store)
    return store.outbox.orderBy('seq').toArray()
  }

  it('removes what the server applied or already had, and keeps the rest', async () => {
    const store = open()
    const sent = await queued(store, startOp(A, AT), arriveOp(A, 's1', AT), createElementOp(A, 's1', element))
    await applyAnswers(sent, [
      { op_id: sent[0]!.op_id, status: 'applied' },
      { op_id: sent[1]!.op_id, status: 'duplicate' },
      { op_id: sent[2]!.op_id, status: 'skipped' },
    ], NOW, { store })
    expect((await store.outbox.toArray()).map(o => o.op_id)).toEqual([sent[2]!.op_id])
  })

  it('keeps a conflict with its reason and the server’s copy, and a refusal with its message', async () => {
    const store = open()
    const sent = await queued(store, startOp(A, AT), arriveOp(A, 's1', AT))
    await applyAnswers(sent, [
      { op_id: sent[0]!.op_id, status: 'conflict', code: 'element_changed', message: 'Changed', current: { version: 3 } },
      { op_id: sent[1]!.op_id, status: 'error', code: 'title_required', message: 'A title is needed', retryable: false },
    ], NOW, { store })
    const [one, two] = await store.outbox.orderBy('seq').toArray()
    expect(one).toMatchObject({ status: 'conflict', code: 'element_changed', current: { version: 3 } })
    expect(two).toMatchObject({ status: 'failed', code: 'title_required', message: 'A title is needed' })
    expect((await counts('u1', store)).attention).toBe(2)
    expect((await attention('u1', store)).map(o => o.status)).toEqual(['conflict', 'failed'])
  })

  it('backs off a retryable error: 2 s, then 4 s, then more, with jitter', async () => {
    const store = open()
    const [op] = await queued(store, startOp(A, AT))
    await applyAnswers([op!], [{ op_id: op!.op_id, status: 'error', code: 'try_again', retryable: true }], NOW, { store, random: () => 1 })
    const first = (await store.outbox.get(op!.seq!))!
    expect(first).toMatchObject({ status: 'pending', attempts: 1 })
    expect(first.next_at).toBe(NOW + 2000)
    await applyAnswers([first], [{ op_id: op!.op_id, status: 'error', retryable: true }], NOW, { store, random: () => 1 })
    expect((await store.outbox.get(op!.seq!))!.next_at).toBe(NOW + 4000)
  })

  it('runs onApplied in the same transaction: if it fails, nothing is removed', async () => {
    const store = open()
    const sent = await queued(store, startOp(A, AT), arriveOp(A, 's1', AT))
    await expect(applyAnswers(sent, sent.map(o => ({ op_id: o.op_id, status: 'applied' as const })), NOW, {
      store,
      onApplied: async op => {
        if (op.type === 'station.arrive') {
          throw new Error('killed while saving the server copy')
        }
      },
    })).rejects.toThrow()
    expect(await store.outbox.count()).toBe(2)
  })

  it('ignores an answer for an op it does not have', async () => {
    const store = open()
    const sent = await queued(store, startOp(A, AT))
    await applyAnswers(sent, [{ op_id: 'someone-else', status: 'applied' }], NOW, { store })
    expect(await store.outbox.count()).toBe(1)
  })
})

describe('backoffMs', () => {
  it('doubles from two seconds up to five minutes, with jitter between half and all', () => {
    expect(backoffMs(1, () => 1)).toBe(2000)
    expect(backoffMs(1, () => 0)).toBe(1000)
    expect(backoffMs(3, () => 1)).toBe(8000)
    expect(backoffMs(20, () => 1)).toBe(300_000)
    expect(backoffMs(20, () => 0)).toBe(150_000)
  })
})

describe('counts and retrying', () => {
  it('counts a user’s waiting changes, files and stuck work, and no one else’s', async () => {
    const store = open()
    await enqueue([startOp(A, AT), arriveOp(A, 's1', AT), startOp(B, AT)], undefined, store)
    await store.blobs.bulkAdd([
      { media_id: 'a', user_id: 'u1', owner_ref: 'x', file: new Blob(['1']), size: 1, sha256: 'h', state: 'pending' },
      { media_id: 'b', user_id: 'u1', owner_ref: 'x', file: new Blob(['1']), size: 1, sha256: 'h', state: 'uploaded' },
      { media_id: 'c', user_id: 'u1', owner_ref: 'x', file: new Blob(['1']), size: 1, sha256: 'h', state: 'diagnostic' },
      { media_id: 'd', user_id: 'u2', owner_ref: 'x', file: new Blob(['1']), size: 1, sha256: 'h', state: 'pending' },
    ])
    expect(await counts('u1', store)).toEqual({ changes: 2, files: 1, attention: 0 })
    expect(await counts('u2', store)).toEqual({ changes: 1, files: 1, attention: 0 })
  })

  it('sends a stuck visit again after the person asks, from the start', async () => {
    const store = open()
    await enqueue([startOp(A, AT), arriveOp(A, 's1', AT)], undefined, store)
    const [first] = await store.outbox.orderBy('seq').toArray()
    await store.outbox.update(first!.seq!, { status: 'conflict', code: 'visit_cancelled', attempts: 3 })
    expect((await sendable('u1', NOW, false, store)).size).toBe(0)
    await retryStuck('u1', 'v1', store)
    expect((await sendable('u1', NOW, false, store)).get('v1')).toHaveLength(2)
    expect((await store.outbox.get(first!.seq!))).toMatchObject({ status: 'pending', attempts: 0 })
    await retryStuck('u2', 'v1', store) // someone else's call changes nothing
  })
})
