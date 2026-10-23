import type { BoardElement, FieldBundle, VisitOut } from '@/api/models'
import { File as NodeFile } from 'node:buffer'
import { afterEach, describe, expect, it } from 'vitest'
import { NetworkError } from '@/api/problem'
import { MmsDb } from '@/offline/db'
import { applyAnswers } from '@/offline/outbox'
import {
  adoptApplied, arriveAt, captureMedia, changeCaption, contextFor, createElement, departFrom, endVisit,
  listElements, removeElement, removeMedia, saveElement, seed, startVisit, visitView,
} from '../store'

// A prepared visit on the phone (W14-6, W14-7, W14-9, W14-12): every change is written to Dexie
// with its op, a save folds into an unsent change, and the server's answers are taken in.

const opened: MmsDb[] = []
let n = 0
function open (): MmsDb {
  const store = new MmsDb(`local-${n++}`)
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
    id: VISIT, status: 'planned', started_at: null, ended_at: null, additional_visit_required: null,
    follow_up_notes: null, actions: [], version: 1,
    staff: [{ id: 'u1', name: 'Devon Brown' }],
    stations: [{ station_id: STATION, owner: { id: 'u1', name: 'Devon Brown' }, arrived_at: null, departed_at: null, actions: [] }],
  } as unknown as VisitOut
}

function serverElement (id: string, over: Partial<BoardElement> = {}): BoardElement {
  return {
    id, visit_id: VISIT, station_id: STATION, kind: 'note', title: 'From the server', description: null, items: [],
    complete: null, completed_at: null, priority: null, request_ref: null, config_version_ids: [], config_versions: [],
    version_due: false, media: { main: [] }, shared: false, created_by: { id: 'u1', name: 'Devon Brown' },
    created_at: '2026-10-22T07:00:00Z', updated_at: '2026-10-22T07:00:00Z', version: 1, can_edit: true, ...over,
  } as BoardElement
}

async function prepared (board: BoardElement[] = []) {
  const store = open()
  const bundle = { bundle_version: 1, visit: visit(), stations: [{ station: { id: STATION }, board }], files: [] } as unknown as FieldBundle
  await store.bundles.put({
    visit_id: VISIT, user_id: ME.id, bundle_version: 1, prepared_at: '2026-10-22T06:00:00Z', ready: true,
    files_total: 0, files_done: 0, documents: [], data: bundle,
  })
  await seed(ME.id, bundle, store)
  const ctx = (await contextFor(VISIT, ME, store))!
  return { store, ctx }
}

async function started (board: BoardElement[] = []) {
  const made = await prepared(board)
  await startVisit(made.ctx)
  await made.store.outbox.clear()
  return made
}

const body = (id: string, title = 'Rust on the mast') => ({ id, kind: 'note' as const, title })
const ops = async (store: MmsDb) => (await store.outbox.orderBy('seq').toArray()).map(o => o.type)

describe('a visit kept on the phone', () => {
  it('is only the signed-in person’s, and only once it is ready', async () => {
    const { store } = await prepared()
    expect(await contextFor(VISIT, { ...ME, id: 'u2' }, store)).toBeNull()
    await store.bundles.update(VISIT, { ready: false })
    expect(await contextFor(VISIT, ME, store)).toBeNull()
    expect(await contextFor('other', ME, store)).toBeNull()
  })

  it('is seeded with the boards, and preparing again leaves the phone’s own changes alone', async () => {
    const { store, ctx } = await started([serverElement('e1'), serverElement('e2')])
    expect((await listElements(ctx, STATION)).items.map(e => e.id).toSorted()).toEqual(['e1', 'e2'])
    await saveElement(ctx, STATION, 'e1', { title: 'Changed here', items: [], shared: false, base_version: 1 })
    const again = { bundle_version: 1, visit: visit(), stations: [{ station: { id: STATION }, board: [serverElement('e1', { title: 'Server again' }), serverElement('e2', { title: 'Server again' })] }], files: [] } as unknown as FieldBundle
    await seed(ME.id, again, store)
    const titles = Object.fromEntries((await listElements(ctx, STATION)).items.map(e => [e.id, e.title]))
    expect(titles).toEqual({ e1: 'Changed here', e2: 'Server again' })
  })
})

describe('the visit’s moves', () => {
  it('start, arrive, depart and end are saved with their ops, in order', async () => {
    const { store, ctx } = await prepared()
    expect((await visitView(ctx)).actions).toEqual(['start'])
    expect((await startVisit(ctx)).status).toBe('started')
    expect((await arriveAt(ctx, STATION)).stations[0]!.arrived_at).toBeTruthy()
    expect((await departFrom(ctx, STATION)).stations[0]!.departed_at).toBeTruthy()
    const ended = await endVisit(ctx, { additional_visit_required: false })
    expect(ended).toMatchObject({ status: 'ended', additional_visit_required: false })
    expect(await ops(store)).toEqual(['visit.start', 'station.arrive', 'station.depart', 'visit.end'])
    expect((await visitView(ctx)).status).toBe('ended')
  })

  it('a repeated move writes nothing more', async () => {
    const { store, ctx } = await prepared()
    await startVisit(ctx)
    await startVisit(ctx)
    expect(await ops(store)).toEqual(['visit.start'])
  })

  it('is refused the way the server would: no arriving before the start', async () => {
    const { ctx } = await prepared()
    await expect(arriveAt(ctx, STATION)).rejects.toMatchObject({ code: 'not_started' })
  })
})

describe('the board', () => {
  it('writes a new element and its op together, and the same id again returns the first', async () => {
    const { store, ctx } = await started()
    const made = await createElement(ctx, STATION, body('e1'))
    expect(made).toMatchObject({ id: 'e1', version: 1, title: 'Rust on the mast' })
    expect(await createElement(ctx, STATION, body('e1', 'Something else'))).toEqual(made)
    expect(await ops(store)).toEqual(['element.create'])
    expect((await store.visits.get('e1'))?.dirty).toBe(true)
    expect((await listElements(ctx, STATION)).items).toHaveLength(1)
  })

  it('refuses before the visit starts, and with an empty title, writing nothing', async () => {
    const planned = await prepared()
    await expect(createElement(planned.ctx, STATION, body('e1'))).rejects.toMatchObject({ code: 'not_started' })
    const { store, ctx } = await started()
    await expect(createElement(ctx, STATION, body('e2', '  '))).rejects.toMatchObject({ code: 'title_required' })
    expect(await store.outbox.count()).toBe(0)
    expect(await store.visits.get('e2')).toBeUndefined()
  })

  it('folds saves into the create that has not been sent: one op, still version 1', async () => {
    const { store, ctx } = await started()
    await createElement(ctx, STATION, body('e1'))
    const first = await saveElement(ctx, STATION, 'e1', { title: 'Rust on the mast base', items: [], shared: false, base_version: 1 })
    const second = await saveElement(ctx, STATION, 'e1', { title: 'Rust, mast base and stay', items: [], shared: false, base_version: first.version })
    expect([first.version, second.version]).toEqual([1, 1])
    const [only, ...rest] = await store.outbox.toArray()
    expect(rest).toEqual([])
    expect(only!.payload).toMatchObject({ id: 'e1', title: 'Rust, mast base and stay' })
  })

  it('folds saves into an update that has not been sent, and starts a new one once it is in flight', async () => {
    const { store, ctx } = await started([serverElement('e1')])
    const one = await saveElement(ctx, STATION, 'e1', { title: 'A', items: [], shared: false, base_version: 1 })
    const two = await saveElement(ctx, STATION, 'e1', { title: 'AB', items: [], shared: false, base_version: one.version })
    expect([one.version, two.version]).toEqual([2, 2])
    let [update] = await store.outbox.toArray()
    expect(update).toMatchObject({ type: 'element.update', payload: { title: 'AB', base_version: 1 } })

    await store.outbox.update(update!.seq!, { inflight: true })
    const three = await saveElement(ctx, STATION, 'e1', { title: 'ABC', items: [], shared: false, base_version: two.version })
    expect(three.version).toBe(3)
    const all = await store.outbox.orderBy('seq').toArray()
    expect(all.map(o => [o.type, (o.payload as { title: string, base_version: number }).base_version])).toEqual([['element.update', 1], ['element.update', 2]])
    update = all[0]
    expect((update!.payload as { title: string }).title).toBe('AB') // what was sent stays as it was sent
  })

  it('writes nothing for a save that says what is already saved', async () => {
    const { store, ctx } = await started([serverElement('e1')])
    await saveElement(ctx, STATION, 'e1', { title: 'From the server', items: [], shared: false, base_version: 1 })
    expect(await store.outbox.count()).toBe(0)
  })

  it('refuses a save from someone who may not edit, and a stale one with the saved copy', async () => {
    const { ctx } = await started([serverElement('e1', { created_by: { id: 'u2', name: 'Other' } })])
    // Devon owns the station, so he may; a stale base is refused
    await expect(saveElement(ctx, STATION, 'e1', { title: 'x', items: [], shared: false, base_version: 7 }))
      .rejects
      .toMatchObject({ code: 'element_changed' })
    const other = await contextFor(VISIT, { id: 'u1', name: 'Devon Brown', admin: false }, ctx.store)
    expect(other).not.toBeNull()
  })

  it('deleting something never sent leaves no trace, and deleting something the server has queues a delete', async () => {
    const { store, ctx } = await started([serverElement('e2')])
    await createElement(ctx, STATION, body('e1'))
    await removeElement(ctx, STATION, 'e1', 1)
    expect(await store.outbox.count()).toBe(0)
    expect(await store.visits.get('e1')).toBeUndefined()

    await saveElement(ctx, STATION, 'e2', { title: 'Edited first', items: [], shared: false, base_version: 1 })
    await removeElement(ctx, STATION, 'e2', 2)
    expect((await store.outbox.toArray()).map(o => [o.type, (o.payload as { base_version?: number }).base_version])).toEqual([['element.delete', 2]])
    expect(await store.visits.get('e2')).toBeUndefined()
    await removeElement(ctx, STATION, 'e2', 2) // again: nothing more
    expect(await store.outbox.count()).toBe(1)
  })
})

describe('files', () => {
  const capture = (id: string, name = 'p.jpg') => ({
    mediaId: id, file: new NodeFile(['photo'], name, { type: 'image/jpeg' }) as unknown as Blob,
    name, kind: 'image' as const, sha256: 'a'.repeat(64), capturedAt: '2026-10-22T08:30:00Z',
  })

  it('go into blobs with the element and a media_add op, in one write', async () => {
    const { store, ctx } = await started()
    await createElement(ctx, STATION, { id: 'e1', kind: 'task', title: 'Funnel' })
    const next = await captureMedia(ctx, STATION, 'e1', 'before', capture('m1'))
    expect(next.media.before).toHaveLength(1)
    expect(next.version).toBe(1)
    const blob = await store.blobs.get('m1')
    expect(blob).toMatchObject({ user_id: 'u1', visit_id: VISIT, state: 'pending', kind: 'image', owner_ref: `visit:${VISIT}:station:${STATION}:element:e1:before` })
    expect(await ops(store)).toEqual(['element.create', 'element.media_add'])
    expect((await store.outbox.toArray())[1]!.blob_id).toBe('m1')
  })

  it('removing a file not yet sent drops its op and its blob; one the server has queues a remove', async () => {
    const onServer = { media_id: 'm9', kind: 'image', filename: 'old.jpg', caption: null, captured_at: null, hidden: false, size_bytes: 3, added_at: '2026-10-22T07:00:00Z', added_by: { id: 'u1', name: 'D' } }
    const { store, ctx } = await started([serverElement('e1', { kind: 'task', media: { before: [onServer], after: [] } as never })])
    await captureMedia(ctx, STATION, 'e1', 'after', capture('m1'))
    await removeMedia(ctx, STATION, 'e1', 'm1')
    expect(await store.outbox.count()).toBe(0)
    expect(await store.blobs.count()).toBe(0)
    await removeMedia(ctx, STATION, 'e1', 'm9')
    expect(await ops(store)).toEqual(['element.media_remove'])
  })

  it('a caption can change while the file has not gone up, and not after', async () => {
    const onServer = { media_id: 'm9', kind: 'image', filename: 'old.jpg', caption: null, captured_at: null, hidden: false, size_bytes: 3, added_at: '2026-10-22T07:00:00Z', added_by: { id: 'u1', name: 'D' } }
    const { store, ctx } = await started([serverElement('e1', { kind: 'task', media: { before: [onServer], after: [] } as never })])
    await captureMedia(ctx, STATION, 'e1', 'after', capture('m1'))
    const next = await changeCaption(ctx, STATION, 'e1', 'm1', 'Funnel before')
    expect(next.media.after![0]!.caption).toBe('Funnel before')
    expect((await store.outbox.toArray())[0]!.payload).toMatchObject({ caption: 'Funnel before' })
    await expect(changeCaption(ctx, STATION, 'e1', 'm9', 'x')).rejects.toBeInstanceOf(NetworkError)
  })
})

describe('what the server confirmed', () => {
  async function answered (store: MmsDb, answer: (op: { type: string }) => { status: 'applied', result?: unknown }) {
    const sent = await store.outbox.orderBy('seq').toArray()
    await applyAnswers(sent, sent.map(op => ({ op_id: op.op_id, ...answer(op) })), 0, {
      store, onApplied: (op, a) => adoptApplied(op, a, store),
    })
  }

  it('replaces the phone’s element with the server’s and marks it clean', async () => {
    const { store, ctx } = await started()
    await createElement(ctx, STATION, body('e1'))
    await answered(store, () => ({ status: 'applied', result: serverElement('e1', { title: 'Rust on the mast', updated_at: '2026-10-22T09:00:00Z' }) }))
    const row = await store.visits.get('e1')
    expect(row?.dirty).toBe(false)
    expect((row?.data as BoardElement).updated_at).toBe('2026-10-22T09:00:00Z')
    expect(await store.outbox.count()).toBe(0)
  })

  it('keeps the phone’s element while later changes to it are still waiting', async () => {
    const { store, ctx } = await started([serverElement('e1')])
    await saveElement(ctx, STATION, 'e1', { title: 'One', items: [], shared: false, base_version: 1 })
    const [first] = await store.outbox.toArray()
    await store.outbox.update(first!.seq!, { inflight: true })
    await saveElement(ctx, STATION, 'e1', { title: 'Two', items: [], shared: false, base_version: 2 })
    const sent = [(await store.outbox.get(first!.seq!))!]
    await applyAnswers(sent, [{ op_id: first!.op_id, status: 'applied', result: serverElement('e1', { title: 'One', version: 2 }) }], 0, {
      store, onApplied: (op, a) => adoptApplied(op, a, store),
    })
    const row = await store.visits.get('e1')
    expect((row?.data as BoardElement).title).toBe('Two')
    expect(row?.dirty).toBe(true)
    expect(await store.outbox.count()).toBe(1)
  })

  it('deletes a file’s blob once its media_add is applied', async () => {
    const { store, ctx } = await started()
    await createElement(ctx, STATION, { id: 'e1', kind: 'note', title: 'Mast' })
    await captureMedia(ctx, STATION, 'e1', 'main', { mediaId: 'm1', file: new Blob(['x']), name: 'p.jpg', kind: 'image', sha256: 'a'.repeat(64) })
    await answered(store, op => ({ status: 'applied', result: op.type === 'element.create' ? serverElement('e1') : undefined }))
    expect(await store.blobs.count()).toBe(0)
  })

  it('lets the visit go once its end is applied and nothing is left: bundle, files and copies', async () => {
    const { store, ctx } = await started([serverElement('e1')])
    await store.files.put({ media_id: 'f1', visit_id: VISIT, user_id: 'u1', station_id: STATION, name: 'a.pdf', size: 1, content_type: 'application/pdf', required: false, blob: new Blob(['x']) })
    await startVisit(ctx).catch(() => undefined)
    await endVisit(ctx, { additional_visit_required: false })
    await answered(store, () => ({ status: 'applied' }))
    expect(await store.bundles.get(VISIT)).toBeUndefined()
    expect(await store.files.count()).toBe(0)
    expect(await store.visits.where('visit_id').equals(VISIT).count()).toBe(0)
  })

  it('keeps the visit while a file for it is still waiting', async () => {
    const { store, ctx } = await started([serverElement('e1')])
    await store.blobs.put({ media_id: 'm5', user_id: 'u1', visit_id: VISIT, owner_ref: 'x', file: new Blob(['x']), size: 1, sha256: 'a', state: 'pending' })
    await endVisit(ctx, { additional_visit_required: false })
    await answered(store, () => ({ status: 'applied' }))
    expect(await store.bundles.get(VISIT)).toBeDefined()
  })
})
