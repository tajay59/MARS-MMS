import type { BoardElement, VisitOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/problem'
import { applySave, buildElement, canEdit, withMedia, withoutMedia } from '../localBoard'
import { arrive, depart, end, overlay, start, stateOf } from '../localVisit'

// The rules a phone applies to a prepared visit with no signal (W14-6, W14-7): the same refusals as
// the server's lifecycle and board rules, well enough for the screen.

const ME = { id: 'u1', name: 'Devon Brown', admin: false }
const OTHER = { id: 'u2', name: 'Andrea Clarke', admin: false }
const ADMIN = { id: 'u9', name: 'Admin', admin: true }
const T0 = '2026-10-22T08:00:00Z'
const T1 = '2026-10-22T09:00:00Z'
const T2 = '2026-10-22T10:00:00Z'

function visit (over: Partial<VisitOut> = {}): VisitOut {
  return {
    id: 'v1', status: 'planned', started_at: null, ended_at: null, additional_visit_required: null,
    follow_up_notes: null, actions: [], version: 1,
    staff: [{ id: 'u1', name: 'Devon Brown' }, { id: 'u2', name: 'Andrea Clarke' }],
    stations: [
      { station_id: 's1', owner: { id: 'u1', name: 'Devon Brown' }, arrived_at: null, departed_at: null, actions: [] },
      { station_id: 's2', owner: { id: 'u2', name: 'Andrea Clarke' }, arrived_at: null, departed_at: null, actions: [] },
    ],
    ...over,
  } as unknown as VisitOut
}

function refused (run: () => unknown): ApiError {
  try {
    run()
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError)
    return error as ApiError
  }
  throw new Error('nothing was refused')
}

describe('a prepared visit on the phone', () => {
  it('can be started by someone attending, and only then ended', () => {
    const v = visit()
    let state = stateOf(v)
    expect(overlay(v, state, ME).actions).toEqual(['start'])
    state = start(v, state, ME, T0)
    expect(state).toMatchObject({ status: 'started', started_at: T0 })
    expect(overlay(v, state, ME).actions).toEqual(['end'])
    expect(start(v, state, ME, T1)).toBe(state) // starting again changes nothing
    state = end(v, state, ME, { additional_visit_required: false, at: T2 })
    expect(state).toMatchObject({ status: 'ended', ended_at: T2, additional_visit_required: false })
    expect(overlay(v, state, ME).actions).toEqual([])
  })

  it('is not started or ended by someone who is not attending', () => {
    const v = visit()
    const outsider = { id: 'u7', name: 'Someone', admin: false }
    expect(refused(() => start(v, stateOf(v), outsider, T0)).code).toBe('not_attending')
    expect(overlay(v, stateOf(v), outsider).actions).toEqual([])
    expect(overlay(v, stateOf(v), ADMIN).actions).toEqual(['start'])
  })

  it('offers Arrive then Depart to each station’s owner only, while it is started', () => {
    const v = visit()
    const started = start(v, stateOf(v), ME, T0)
    const mine = overlay(v, started, ME).stations
    expect(mine.map(s => s.actions)).toEqual([['arrive'], []])
    const arrived = arrive(v, started, ME, 's1', T1)
    expect(overlay(v, arrived, ME).stations[0]!.actions).toEqual(['depart'])
    const left = depart(v, arrived, ME, 's1', T2)
    expect(overlay(v, left, ME).stations[0]).toMatchObject({ actions: [], arrived_at: T1, departed_at: T2 })
    expect(overlay(v, started, ADMIN).stations.map(s => s.actions)).toEqual([['arrive'], ['arrive']])
  })

  it('refuses the way the server does', () => {
    const v = visit()
    const planned = stateOf(v)
    const started = start(v, planned, ME, T0)
    expect(refused(() => arrive(v, planned, ME, 's1', T1)).code).toBe('not_started')
    expect(refused(() => arrive(v, started, ME, 's2', T1)).code).toBe('not_owner')
    expect(refused(() => depart(v, started, ME, 's1', T1)).code).toBe('not_arrived')
    const arrived = arrive(v, started, ME, 's1', T1)
    expect(refused(() => depart(v, arrived, ME, 's1', T0)).code).toBe('bad_time')
    expect(refused(() => end(v, started, ME, { additional_visit_required: true, at: T2 })).code).toBe('notes_required')
    expect(refused(() => end(v, planned, ME, { additional_visit_required: false, at: T2 })).code).toBe('not_started')
    expect(refused(() => arrive(v, { ...started, status: 'cancelled' }, ME, 's1', T1)).code).toBe('visit_cancelled')
    expect(refused(() => arrive(v, { ...started, status: 'ended' }, ME, 's1', T1)).code).toBe('already_ended')
  })

  it('arriving or departing twice changes nothing', () => {
    const v = visit()
    const arrived = arrive(v, start(v, stateOf(v), ME, T0), ME, 's1', T1)
    expect(arrive(v, arrived, ME, 's1', T2)).toBe(arrived)
    const left = depart(v, arrived, ME, 's1', T2)
    expect(depart(v, left, ME, 's1', '2026-10-22T11:00:00Z')).toBe(left)
  })

  it('takes follow-up notes with a visit that needs another', () => {
    const v = visit()
    const done = end(v, start(v, stateOf(v), ME, T0), ME, { additional_visit_required: true, follow_up_notes: '  Bring a ladder  ', at: T2 })
    expect(done.follow_up_notes).toBe('Bring a ladder')
  })
})

const NEW = { id: 'e1', kind: 'note' as const, title: '  Rust on the mast  ' }

describe('an element built on the phone', () => {
  it('is a version 1 element of the person, with the kind’s sections and sharing', () => {
    const e = buildElement(NEW, visit(), 's1', ME, T0)
    expect(e).toMatchObject({
      id: 'e1', visit_id: 'v1', station_id: 's1', kind: 'note', title: 'Rust on the mast', description: null,
      shared: false, version: 1, can_edit: true, created_by: { id: 'u1', name: 'Devon Brown' }, created_at: T0,
    })
    expect(e.media).toEqual({ main: [] })
    expect(buildElement({ ...NEW, kind: 'task', title: 'Funnel' }, visit(), 's1', ME, T0).media).toEqual({ before: [], after: [] })
    expect(buildElement({ ...NEW, kind: 'task', title: 'Funnel' }, visit(), 's1', ME, T0).shared).toBe(true)
    expect(buildElement({ ...NEW, kind: 'recommendation', title: 'Wire' }, visit(), 's1', ME, T0).priority).toBe('medium')
  })

  it('refuses what the server would', () => {
    const make = (body: object) => refused(() => buildElement({ ...NEW, ...body } as never, visit(), 's1', ME, T0))
    expect(make({ title: ' '.repeat(3) }).code).toBe('title_required')
    expect(make({ title: 'x'.repeat(81) }).code).toBe('too_long')
    expect(make({ items: [{ id: 'i1', text: 'x', done: false }] }).code).toBe('items_not_allowed')
    expect(make({ priority: 'high' }).code).toBe('priority_not_allowed')
    expect(make({ kind: 'task', items: [{ id: 'i1', text: ' ', done: false }] }).code).toBe('item_required')
    expect(make({ kind: 'task', items: [{ id: 'i1', text: 'a', done: false }, { id: 'i1', text: 'b', done: false }] }).code).toBe('duplicate_id')
  })

  it('knows who may edit it', () => {
    const e = buildElement(NEW, visit(), 's2', OTHER, T0)
    expect(canEdit(e, visit(), 's2', OTHER)).toBe(true) // its author and the station's owner
    expect(canEdit(e, visit(), 's2', ME)).toBe(false)
    expect(canEdit(buildElement(NEW, visit(), 's2', ME, T0), visit(), 's2', OTHER)).toBe(true) // the owner
    expect(canEdit(e, visit(), 's2', ADMIN)).toBe(true)
  })
})

describe('saving an element on the phone', () => {
  const task = (): BoardElement => buildElement({
    id: 'e2', kind: 'task', title: 'Funnel',
    items: [{ id: 'i1', text: 'Remove', done: false }, { id: 'i2', text: 'Fit', done: false }],
  }, visit(), 's1', ME, T0)
  const body = (e: BoardElement, over: object = {}) => ({
    title: e.title, description: e.description, shared: e.shared, priority: e.priority,
    items: e.items.map(i => ({ id: i.id, text: i.text, done: i.done })), base_version: e.version, ...over,
  }) as never

  it('moves the version when the content changes, and not when it does not', () => {
    const e = task()
    expect(applySave(e, body(e), ME, T1, false)).toBe(e)
    const changed = applySave(e, body(e, { title: 'Replace funnel' }), ME, T1, false)
    expect(changed).toMatchObject({ title: 'Replace funnel', version: 2, updated_at: T1 })
  })

  it('keeps the version when it folds into a change not yet sent', () => {
    const e = task()
    const first = applySave(e, body(e, { title: 'A' }), ME, T1, false)
    const second = applySave(first, body(first, { title: 'AB' }), ME, T2, true)
    expect(first.version).toBe(2)
    expect(second.version).toBe(2)
  })

  it('records who ticked an item and when, keeps it while it stays ticked, and completes the task', () => {
    const e = task()
    const one = applySave(e, body(e, { items: [{ id: 'i1', text: 'Remove', done: true }, { id: 'i2', text: 'Fit', done: false }] }), ME, T1, false)
    expect(one.items[0]).toMatchObject({ done: true, done_by: 'u1', done_at: T1 })
    expect(one.complete).toBe(false)
    const both = applySave(one, body(one, { items: [{ id: 'i1', text: 'Remove', done: true }, { id: 'i2', text: 'Fit', done: true }] }), OTHER, T2, false)
    expect(both.items[0]).toMatchObject({ done_by: 'u1', done_at: T1 })
    expect(both.items[1]).toMatchObject({ done_by: 'u2', done_at: T2 })
    expect(both).toMatchObject({ complete: true, completed_at: T2 })
    const back = applySave(both, body(both, { items: [{ id: 'i1', text: 'Remove', done: false }, { id: 'i2', text: 'Fit', done: true }] }), ME, T2, false)
    expect(back).toMatchObject({ complete: false, completed_at: null })
  })

  it('refuses a save made against an older version, with the saved copy', () => {
    const e = task()
    const error = refused(() => applySave(e, body(e, { base_version: 5 }), ME, T1, false))
    expect(error.code).toBe('element_changed')
    expect((error.body.current as BoardElement).id).toBe('e2')
  })

  it('refuses an empty title', () => {
    const e = task()
    expect(refused(() => applySave(e, body(e, { title: ' ' }), ME, T1, false)).code).toBe('title_required')
  })
})

describe('files on an element', () => {
  const entry = (id: string) => ({
    media_id: id, kind: 'image', filename: `${id}.jpg`, caption: null, captured_at: null, hidden: false,
    size_bytes: 10, added_at: T1, added_by: { id: 'u1', name: 'Devon Brown' },
  }) as never

  it('go in a section the kind has, once, and come out again', () => {
    const e = buildElement({ id: 'e3', kind: 'task', title: 'Funnel' }, visit(), 's1', ME, T0)
    const added = withMedia(e, 'before', entry('m1'))
    expect(added.media.before).toHaveLength(1)
    expect(withMedia(added, 'before', entry('m1'))).toBe(added)
    expect(withoutMedia(added, 'm1').media.before).toEqual([])
    expect(refused(() => withMedia(e, 'main', entry('m2'))).code).toBe('bad_section')
    expect(added.version).toBe(1) // a file never changes the version
  })
})
