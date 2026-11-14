import type { FieldBundle, VisitOut } from '@/api/models'
import { File as NodeFile } from 'node:buffer'
import { afterEach, describe, expect, it } from 'vitest'
import { MmsDb } from '@/offline/db'
import { buildExport } from '@/offline/exportConflict'
import { applyAnswers } from '@/offline/outbox'
import { pendingByVisit, totalsOf } from '@/offline/pending'
import { blobsFor, concerns, doneWith, retryStuck, wordsFor } from '../attention'
import {
  arriveAt, captureMedia, contextFor, createElement, endVisit, saveElement, seed, startVisit,
} from '../store'

// Needs attention, Export and the pending counts (W14-13; AFD §6; TRD §7.4): what the server
// refused stays on the phone, is described in the table's words, and goes only on "Done with this".

const opened: MmsDb[] = []
let n = 0
function open (): MmsDb {
  const store = new MmsDb(`attention-${n++}`)
  opened.push(store)
  return store
}
afterEach(async () => {
  for (const store of opened.splice(0)) {
    store.close()
    await store.delete()
  }
})

const ME = { id: 'u1', name: 'Devon Brown', admin: false }
const VISIT = 'v1'
const STATION = 's1'

function visit (): VisitOut {
  return {
    id: VISIT, ref: 'VR-2026-0042-01', request_title: 'Rain gauge reads zero', status: 'planned', started_at: null, ended_at: null,
    additional_visit_required: null, follow_up_notes: null, actions: [], version: 1,
    staff: [{ id: 'u1', name: 'Devon Brown' }],
    stations: [{ station_id: STATION, owner: { id: 'u1', name: 'Devon Brown' }, arrived_at: null, departed_at: null, actions: [] }],
  } as unknown as VisitOut
}

async function started () {
  const store = open()
  const bundle = {
    bundle_version: 1,
    visit: visit(),
    stations: [{ station: { id: STATION, code: 'JM-MBJ-002', name: 'Montego Bay Airport' }, board: [] }],
    files: [],
  } as unknown as FieldBundle
  await store.bundles.put({
    visit_id: VISIT, user_id: ME.id, bundle_version: 1, prepared_at: '2026-10-22T06:00:00Z', ready: true,
    files_total: 0, files_done: 0, documents: [], data: bundle,
  })
  await seed(ME.id, bundle, store)
  const ctx = (await contextFor(VISIT, ME, store))!
  await startVisit(ctx)
  await arriveAt(ctx, STATION)
  return { store, ctx }
}

/** The server turns every sent op into this answer. */
async function refuse (store: MmsDb, status: 'conflict' | 'error', code: string, extra: Record<string, unknown> = {}) {
  const sent = await store.outbox.toArray()
  await applyAnswers(
    sent,
    sent.map(op => ({ op_id: op.op_id, status, code, message: `server says ${code}`, retryable: false, ...extra })),
    0,
    { store },
  )
}

describe('what needs the person', () => {
  it('describes a conflict in the words of the table and keeps the phone’s copy', async () => {
    const { store, ctx } = await started()
    await createElement(ctx, STATION, { id: 'e1', kind: 'note', title: 'Rust on the mast' })
    await store.outbox.clear()
    await saveElement(ctx, STATION, 'e1', { base_version: 1, title: 'Rust on the mast base', shared: false } as never)

    const sent = await store.outbox.toArray()
    await applyAnswers(
      sent,
      sent.map(op => ({
        op_id: op.op_id, status: 'conflict' as const, code: 'element_changed',
        current: { id: 'e1', title: 'Rust on the mast', version: 3, created_by: { id: 'u2', name: 'Tech 2' } },
      })),
      0,
      { store },
    )

    const found = await concerns(ME.id, store)
    expect(found).toHaveLength(1)
    expect(found[0]).toMatchObject({
      visit_id: VISIT, ref: 'VR-2026-0042-01', title: 'Rain gauge reads zero', what: 'Changed on another device',
      canExport: true, canRetry: false, station: { code: 'JM-MBJ-002', name: 'Montego Bay Airport' },
    })
    expect(found[0]!.element).toMatchObject({ title: 'Rust on the mast base' })
    expect(found[0]!.current).toMatchObject({ version: 3 })
  })

  it('groups all of an element’s ops into one item, and a move stands alone', async () => {
    const { store, ctx } = await started()
    await store.outbox.clear()
    await createElement(ctx, STATION, { id: 'e1', kind: 'note', title: 'One' })
    await saveElement(ctx, STATION, 'e1', { base_version: 1, title: 'One, again', shared: false } as never).catch(() => undefined)
    await arriveAt(ctx, STATION).catch(() => undefined)
    await refuse(store, 'conflict', 'not_owner')
    const found = await concerns(ME.id, store)
    expect(found.filter(c => c.element?.id === 'e1')).toHaveLength(1)
  })

  it('offers Try again, not Export, for a cancelled visit', () => {
    expect(wordsFor('visit_cancelled')).toMatchObject({ canRetry: true, canExport: false })
    expect(wordsFor('not_owner')).toMatchObject({ canRetry: false, canExport: true })
    // A reason the table does not know still reads as something the person can act on
    expect(wordsFor('something_new')).toMatchObject({ what: 'Could not be saved', canExport: true })
  })

  it('sends a stuck visit’s ops again after Try again', async () => {
    const { store } = await started()
    await refuse(store, 'conflict', 'visit_cancelled')
    expect((await store.outbox.toArray()).every(op => op.status === 'conflict')).toBe(true)
    await retryStuck(ME.id, VISIT, store)
    expect((await store.outbox.toArray()).every(op => op.status === 'pending')).toBe(true)
  })

  it('keeps the work until “Done with this”, then lets go of it and its files', async () => {
    const { store, ctx } = await started()
    await createElement(ctx, STATION, { id: 'e1', kind: 'note', title: 'Rust on the mast' })
    await captureMedia(ctx, STATION, 'e1', 'main', {
      mediaId: 'm1', file: new NodeFile(['jpeg bytes'], 'seal.jpg', { type: 'image/jpeg' }) as unknown as File,
      name: 'seal.jpg', kind: 'image', sha256: 'abc',
    })
    await refuse(store, 'conflict', 'not_editor')
    const item = (await concerns(ME.id, store)).find(c => c.element?.id === 'e1')!
    expect(await blobsFor(item, store)).toHaveLength(1)

    await doneWith(item, store)
    expect((await concerns(ME.id, store)).find(c => c.element?.id === 'e1')).toBeUndefined()
    expect(await store.visits.get('e1')).toBeUndefined()
    expect(await store.blobs.count()).toBe(0)
    // The visit’s other work is untouched
    expect(await store.bundles.get(VISIT)).toBeDefined()
  })

  it('lets the prepared copy go when the last stuck work of an ended visit is done with', async () => {
    const { store, ctx } = await started()
    await endVisit(ctx, { additional_visit_required: false })
    await refuse(store, 'conflict', 'locked')
    for (const item of await concerns(ME.id, store)) {
      await doneWith(item, store)
    }
    expect(await store.outbox.count()).toBe(0)
    expect(await store.bundles.count()).toBe(0)
    expect(await store.visits.count()).toBe(0)
  })
})

describe('what is waiting', () => {
  it('counts changes and files by visit and leaves out conflicts and test files', async () => {
    const { store, ctx } = await started()
    await createElement(ctx, STATION, { id: 'e1', kind: 'note', title: 'Rust on the mast' })
    await captureMedia(ctx, STATION, 'e1', 'main', {
      mediaId: 'm1', file: new NodeFile([new Uint8Array(2048)], 'seal.jpg', { type: 'image/jpeg' }) as unknown as File,
      name: 'seal.jpg', kind: 'image', sha256: 'abc',
    })
    await store.blobs.put({
      media_id: 'test', user_id: ME.id, owner_ref: 'diagnostic', file: new Blob(['x']), size: 5_000_000, sha256: 'd', state: 'diagnostic',
    })

    const [only] = await pendingByVisit(ME.id, store)
    expect(only).toMatchObject({ visit_id: VISIT, ref: 'VR-2026-0042-01', files: 1, bytes: 2048 })
    expect(only!.changes).toBeGreaterThanOrEqual(4) // start, arrive, create, media_add
    expect(totalsOf([only!], 2)).toMatchObject({ files: 1, attention: 2, bytes: 2048 })

    await refuse(store, 'conflict', 'locked')
    expect(await pendingByVisit(ME.id, store)).toMatchObject([{ changes: 0, files: 1 }])
  })

  it('knows the visit end is still waiting, so the page can say the report follows', async () => {
    const { store, ctx } = await started()
    expect(await pendingByVisit(ME.id, store)).toMatchObject([{ ending: false }])
    await endVisit(ctx, { additional_visit_required: false })
    expect(await pendingByVisit(ME.id, store)).toMatchObject([{ ending: true }])
  })

  it('is nothing for another person', async () => {
    const { store } = await started()
    expect(await pendingByVisit('someone-else', store)).toEqual([])
    expect(await concerns('someone-else', store)).toEqual([])
  })
})

describe('export', () => {
  it('writes one JSON file with the work and the files as they were taken', () => {
    const photo = new Blob(['jpeg bytes'], { type: 'image/jpeg' })
    const built = buildExport({
      visit: { id: VISIT, ref: 'VR-2026-0042-01', title: 'Rain gauge reads zero' },
      station: { code: 'JM-MBJ-002', name: 'Montego Bay Airport' },
      reason: { code: 'not_owner', what: 'Owner changed', text: 'Someone else owns it' },
      element: { id: 'e1', title: 'Rust on the mast' },
      server_copy: null,
      operations: [{ type: 'element.create', created_at: '2026-10-22T09:00:00Z', payload: { id: 'e1' } }],
      blobs: [
        { media_id: 'm1', user_id: ME.id, owner_ref: 'r', file: photo, size: 10, sha256: 'aa', state: 'pending', name: 'seal.jpg', kind: 'image' },
        { media_id: 'm2', user_id: ME.id, owner_ref: 'r', file: photo, size: 10, sha256: 'bb', state: 'pending', name: 'seal.jpg', kind: 'image' },
      ],
      at: new Date('2026-10-22T10:00:00Z'),
    })
    expect(built.json.name).toBe('VR-2026-0042-01-JM-MBJ-002-2026-10-22.json')
    // Two files with one name do not overwrite each other
    expect(built.media.map(f => f.name)).toEqual(['seal.jpg', '2-seal.jpg'])
    expect(built.summary).toMatchObject({ files: 2, bytes: 20, written: 1 })
  })
})
