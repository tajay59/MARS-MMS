import type { Answer } from '../outbox'
import type { Deps, SyncRequest } from '../sync'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NetworkError } from '@/api/problem'
import { MmsDb } from '../db'
import { arriveOp, createElementOp, mediaAddOp, startOp } from '../ops'
import { counts, enqueue } from '../outbox'
import { BATCH, FileRefused, runSync } from '../sync'

// The sync runner (TRD §7.3; OFF-5 to OFF-8; W14-10 to W14-12): order, one runner, offline, files
// before their ops, conflicts that stop one visit, batches, and what a failure half-way leaves.

const opened: MmsDb[] = []
let n = 0
function open (): MmsDb {
  const store = new MmsDb(`sync-${n++}`)
  opened.push(store)
  return store
}
afterEach(async () => {
  for (const store of opened.splice(0)) {
    store.close()
    await store.delete()
  }
})

const A = (visitId = 'v1') => ({ userId: 'u1', visitId })
const AT = '2026-10-22T08:00:00Z'
const NOW = 5_000_000
const note = (id: string) => ({ id, kind: 'note', title: id, items: [], shared: false })

/** A server that applies every op once and says `duplicate` for one it has seen: the idempotency
 *  the real one has. `rule` can answer an op differently. */
function server (rule?: (type: string, visit: string) => Partial<Answer> | undefined) {
  const seen = new Set<string>()
  const received: SyncRequest[] = []
  const send = vi.fn(async (body: SyncRequest) => {
    received.push(body)
    const answers: Answer[] = []
    let stopped = new Set<string>()
    for (const op of body.ops) {
      if (stopped.has(op.visit_id)) {
        answers.push({ op_id: op.op_id, status: 'skipped', code: 'waiting', retryable: true })
        continue
      }
      const special = rule?.(op.type, op.visit_id)
      if (special) {
        answers.push({ op_id: op.op_id, status: 'applied', ...special })
        if (special.status !== 'applied' && special.status !== 'duplicate') {
          stopped = new Set([...stopped, op.visit_id])
        }
        continue
      }
      answers.push({ op_id: op.op_id, status: seen.has(op.op_id) ? 'duplicate' : 'applied' })
      seen.add(op.op_id)
    }
    return { answers }
  })
  return { send, received, seen }
}

function deps (store: MmsDb, over: Partial<Deps> = {}): Deps {
  return {
    session: async () => ({ kind: 'ok' }),
    send: server().send,
    upload: async () => undefined,
    deviceId: async () => 'device-1',
    now: () => NOW,
    random: () => 1,
    lock: async run => run(),
    store,
    ...over,
  }
}

describe('sending', () => {
  it('sends a visit’s ops in the order they were made and removes what was applied', async () => {
    const store = open()
    const s = server()
    await enqueue([startOp(A(), AT), arriveOp(A(), 's1', AT), createElementOp(A(), 's1', note('e1'))], undefined, store)
    const result = await runSync('u1', deps(store, { send: s.send }))
    expect(result).toMatchObject({ outcome: 'done', sent: 3, applied: 3, conflicts: 0 })
    expect(s.received[0]!.device_id).toBe('device-1')
    expect(s.received[0]!.ops.map(o => o.type)).toEqual(['visit.start', 'station.arrive', 'element.create'])
    expect(await store.outbox.count()).toBe(0)
    expect((await store.meta.get('sync-last'))?.value).toBe(NOW)
  })

  it('does nothing, and asks nobody, when nothing is waiting', async () => {
    const store = open()
    const session = vi.fn(async () => ({ kind: 'ok' as const }))
    expect(await runSync('u1', deps(store, { session }))).toMatchObject({ outcome: 'nothing', sent: 0 })
    expect(session).not.toHaveBeenCalled()
  })

  it('runs one at a time: a second runner answers busy and sends nothing', async () => {
    const store = open()
    await enqueue([startOp(A(), AT)], undefined, store)
    const s = server()
    const result = await runSync('u1', deps(store, { send: s.send, lock: async () => null }))
    expect(result.outcome).toBe('busy')
    expect(s.send).not.toHaveBeenCalled()
    expect(await store.outbox.count()).toBe(1)
  })

  it('syncing the same work twice changes nothing: the second run finds nothing to send', async () => {
    const store = open()
    const s = server()
    await enqueue([startOp(A(), AT), arriveOp(A(), 's1', AT)], undefined, store)
    await runSync('u1', deps(store, { send: s.send }))
    expect((await runSync('u1', deps(store, { send: s.send }))).outcome).toBe('nothing')
    expect(s.send).toHaveBeenCalledTimes(1)
  })

  it('splits a long queue into batches of a hundred', async () => {
    const store = open()
    const s = server()
    const ops = Array.from({ length: 250 }, (_, i) => createElementOp(A(), 's1', note(`e${i}`)))
    await enqueue(ops, undefined, store)
    const result = await runSync('u1', deps(store, { send: s.send }))
    expect(s.received.map(b => b.ops.length)).toEqual([BATCH, BATCH, 50])
    expect(result.applied).toBe(250)
    expect(await store.outbox.count()).toBe(0)
  })

  it('sends only this user’s work', async () => {
    const store = open()
    const s = server()
    await enqueue([startOp(A(), AT), startOp({ userId: 'u2', visitId: 'v9' }, AT)], undefined, store)
    await runSync('u1', deps(store, { send: s.send }))
    expect(s.received[0]!.ops.map(o => o.visit_id)).toEqual(['v1'])
    expect((await store.outbox.toArray()).map(o => o.user_id)).toEqual(['u2'])
  })
})

describe('when it cannot', () => {
  it('leaves everything as it was when the server cannot be reached', async () => {
    const store = open()
    await enqueue([startOp(A(), AT), arriveOp(A(), 's1', AT)], undefined, store)
    const send = vi.fn(async () => {
      throw new NetworkError(new TypeError('Failed to fetch'))
    })
    expect((await runSync('u1', deps(store, { send }))).outcome).toBe('offline')
    const left = await store.outbox.toArray()
    expect(left).toHaveLength(2)
    expect(left.every(o => o.status === 'pending' && o.attempts === 0)).toBe(true)
  })

  it('says log in, or offline, when there is no session, and sends nothing', async () => {
    const store = open()
    await enqueue([startOp(A(), AT)], undefined, store)
    const s = server()
    expect((await runSync('u1', deps(store, { send: s.send, session: async () => ({ kind: 'login' }) }))).outcome).toBe('login')
    expect((await runSync('u1', deps(store, { send: s.send, session: async () => ({ kind: 'offline' }) }))).outcome).toBe('offline')
    expect(s.send).not.toHaveBeenCalled()
    expect(await store.outbox.count()).toBe(1)
  })

  it('applies a half-answered batch: what was answered goes, the rest is sent again', async () => {
    const store = open()
    await enqueue([startOp(A(), AT), arriveOp(A(), 's1', AT)], undefined, store)
    const send = vi.fn(async (body: SyncRequest) => ({ answers: [{ op_id: body.ops[0]!.op_id, status: 'applied' as const }] }))
    await runSync('u1', deps(store, { send }))
    expect((await store.outbox.toArray()).map(o => o.type)).toEqual(['station.arrive'])
  })

  it('keeps every op when saving the answers fails (the retry gets duplicates, never doubles)', async () => {
    const store = open()
    const s = server()
    await enqueue([startOp(A(), AT), arriveOp(A(), 's1', AT)], undefined, store)
    await expect(runSync('u1', deps(store, {
      send: s.send,
      onApplied: async () => {
        throw new Error('killed while saving the server copy')
      },
    }))).rejects.toThrow()
    expect(await store.outbox.count()).toBe(2)
    const again = await runSync('u1', deps(store, { send: s.send }))
    expect(again).toMatchObject({ outcome: 'done', applied: 2 })
    expect(s.received[1]!.ops.map(o => o.op_id)).toEqual(s.received[0]!.ops.map(o => o.op_id))
    expect(await store.outbox.count()).toBe(0)
  })
})

describe('conflicts and errors', () => {
  it('keeps a conflict, stops its visit, and goes on with another', async () => {
    const store = open()
    const s = server((type, visit) => (visit === 'v1' && type === 'station.arrive'
      ? { status: 'conflict', code: 'not_owner', message: 'Someone else owns it now' }
      : undefined))
    await enqueue([
      startOp(A(), AT), arriveOp(A(), 's1', AT), createElementOp(A(), 's1', note('e1')),
      startOp(A('v2'), AT),
    ], undefined, store)
    const result = await runSync('u1', deps(store, { send: s.send }))
    expect(result).toMatchObject({ applied: 2, conflicts: 1 })
    const left = await store.outbox.orderBy('seq').toArray()
    expect(left.map(o => [o.type, o.status])).toEqual([['station.arrive', 'conflict'], ['element.create', 'pending']])
    expect(left[0]).toMatchObject({ code: 'not_owner', message: 'Someone else owns it now' })

    // Next time the stuck visit sends nothing, so it is not told off again
    s.send.mockClear()
    expect((await runSync('u1', deps(store, { send: s.send }))).outcome).toBe('nothing')
    expect(s.send).not.toHaveBeenCalled()
    expect(await counts('u1', store)).toEqual({ changes: 1, files: 0, attention: 1 })
  })

  it('waits out a retryable error and holds the later ops, until Sync now', async () => {
    const store = open()
    let fail = true
    const s = server(type => (fail && type === 'visit.start' ? { status: 'error', code: 'try_again', retryable: true } : undefined))
    await enqueue([startOp(A(), AT), arriveOp(A(), 's1', AT)], undefined, store)
    const first = await runSync('u1', deps(store, { send: s.send }))
    expect(first.applied).toBe(0)
    const [one] = await store.outbox.orderBy('seq').toArray()
    expect(one).toMatchObject({ status: 'pending', attempts: 1, next_at: NOW + 2000 })

    s.send.mockClear()
    expect((await runSync('u1', deps(store, { send: s.send }))).outcome).toBe('nothing') // still backing off
    fail = false
    const forced = await runSync('u1', deps(store, { send: s.send }), { force: true })
    expect(forced).toMatchObject({ outcome: 'done', applied: 2 })
    expect(await store.outbox.count()).toBe(0)
  })

  it('counts a refusal for good', async () => {
    const store = open()
    const s = server(() => ({ status: 'error', code: 'title_required', message: 'A title is needed', retryable: false }))
    await enqueue([createElementOp(A(), 's1', note('e1'))], undefined, store)
    expect((await runSync('u1', deps(store, { send: s.send }))).refused).toBe(1)
    expect((await store.outbox.toArray())[0]).toMatchObject({ status: 'failed', code: 'title_required' })
  })
})

describe('files go up before their ops', () => {
  async function withFile (store: MmsDb, visitId = 'v1'): Promise<string> {
    await store.blobs.put({
      media_id: `m-${visitId}`, user_id: 'u1', owner_ref: 'visit:x', file: new Blob(['photo']), size: 5,
      sha256: 'abc', state: 'pending', name: 'p.jpg', kind: 'image',
    })
    return `m-${visitId}`
  }

  it('uploads the file, then sends the op that puts it on the element', async () => {
    const store = open()
    const order: string[] = []
    const mediaId = await withFile(store)
    await enqueue([createElementOp(A(), 's1', note('e1')), mediaAddOp(A(), 's1', 'e1', { mediaId, section: 'main' })], undefined, store)
    const s = server()
    await runSync('u1', deps(store, {
      send: async body => {
        order.push(`send:${body.ops.map(o => o.type).join(',')}`)
        return s.send(body)
      },
      upload: async blob => {
        order.push(`upload:${blob.media_id}`)
      },
    }))
    expect(order).toEqual([`upload:${mediaId}`, 'send:element.create,element.media_add'])
    expect((await store.blobs.get(mediaId))?.state).toBe('uploaded')
  })

  it('does not upload a file twice', async () => {
    const store = open()
    const mediaId = await withFile(store)
    await store.blobs.update(mediaId, { state: 'uploaded' })
    await enqueue([mediaAddOp(A(), 's1', 'e1', { mediaId, section: 'main' })], undefined, store)
    const upload = vi.fn(async () => undefined)
    await runSync('u1', deps(store, { upload }))
    expect(upload).not.toHaveBeenCalled()
  })

  it('goes offline when the file cannot go up, sends nothing, and puts the file back to waiting', async () => {
    const store = open()
    const mediaId = await withFile(store)
    await enqueue([createElementOp(A(), 's1', note('e1')), mediaAddOp(A(), 's1', 'e1', { mediaId, section: 'main' })], undefined, store)
    const s = server()
    const result = await runSync('u1', deps(store, {
      send: s.send,
      upload: async () => {
        throw new NetworkError(undefined)
      },
    }))
    expect(result.outcome).toBe('offline')
    expect(s.send).not.toHaveBeenCalled()
    expect((await store.blobs.get(mediaId))?.state).toBe('pending')
    expect(await store.outbox.count()).toBe(2)
  })

  it('sends the ops before a file that cannot go up, then stops that visit and carries on with others', async () => {
    const store = open()
    const bad = await withFile(store, 'v1')
    const good = await withFile(store, 'v2')
    await enqueue([
      createElementOp(A(), 's1', note('e1')), mediaAddOp(A(), 's1', 'e1', { mediaId: bad, section: 'main' }),
      createElementOp(A(), 's1', note('e2')),
      createElementOp(A('v2'), 's1', note('e3')), mediaAddOp(A('v2'), 's1', 'e3', { mediaId: good, section: 'main' }),
    ], undefined, store)
    const s = server()
    const result = await runSync('u1', deps(store, {
      send: s.send,
      upload: async blob => {
        if (blob.media_id === bad) {
          throw new FileRefused('The file is too large', 'too_large')
        }
      },
    }))
    expect(result.refused).toBe(1)
    const sent = s.received.flatMap(b => b.ops.map(o => `${o.visit_id}:${o.type}`))
    expect(sent).toEqual(['v1:element.create', 'v2:element.create', 'v2:element.media_add'])
    const left = await store.outbox.orderBy('seq').toArray()
    expect(left.map(o => [o.visit_id, o.type, o.status])).toEqual([
      ['v1', 'element.media_add', 'failed'],
      ['v1', 'element.create', 'pending'],
    ])
    expect(left[0]).toMatchObject({ code: 'too_large', message: 'The file is too large' })
  })

  it('counts an upload that ran out of tries as an attempt and tries at the next trigger', async () => {
    const store = open()
    const mediaId = await withFile(store)
    await enqueue([mediaAddOp(A(), 's1', 'e1', { mediaId, section: 'main' })], undefined, store)
    await runSync('u1', deps(store, {
      upload: async () => {
        throw new Error('The connection kept failing')
      },
    }))
    const [op] = await store.outbox.toArray()
    expect(op).toMatchObject({ status: 'pending', attempts: 1 })
    expect((await store.blobs.get(mediaId))?.state).toBe('pending')
  })
})
