import type { Me, VisitState } from './localVisit'
import type { BoardElement, BoardElementIn, BoardElementList, BoardElementPut, BoardMedia, FieldBundle, VisitOut } from '@/api/models'
import type { LocalVisit, MmsDb, OutboxOp } from '@/offline/db'
import type { NewOp } from '@/offline/ops'
import type { Answer } from '@/offline/outbox'
import Dexie from 'dexie'
import { NetworkError } from '@/api/problem'
import { db } from '@/offline/db'
import {
  arriveOp, createElementOp, deleteElementOp, departOp, endOp, mediaAddOp, mediaRemoveOp, startOp, updateElementOp,
} from '@/offline/ops'
import { ownerRef } from '../media'
import { applySave, buildElement, canEdit, withMedia, withoutMedia } from './localBoard'
import { arrive, attends, depart, end, overlay, refusal, start, stateOf } from './localVisit'

/*
  A prepared visit on the phone, and every change to it (W14-6, W14-7, W14-9). While a visit is
  prepared, its board and its moves are read from and written to Dexie first; each change is saved
  with its outbox op in one transaction, and the runner sends it when there is signal.

  Rows in `visits`: an element (`id` = the element's id) holds the element as the board shows it;
  `visit:<id>` holds the visit's own moves. A row is `dirty` while the server has not confirmed it.
  A save folds into the change before it when that has not been sent yet, so a note typed over a
  minute is one operation and the phone's `version` still moves the way the server's will.
*/

export interface Context {
  store: MmsDb
  userId: string
  me: Me
  visitId: string
  base: VisitOut
}

const visitRow = (visitId: string): string => `visit:${visitId}`

/** The prepared visit for this person, or null when it is not prepared on this phone. */
export async function contextFor (visitId: string, me: Me, store: MmsDb = db): Promise<Context | null> {
  const row = await store.bundles.get(visitId)
  if (!row || row.user_id !== me.id || !row.ready) {
    return null
  }
  return { store, userId: me.id, me, visitId, base: (row.data as FieldBundle).visit }
}

async function stateOfVisit (ctx: Context): Promise<VisitState> {
  const row = await ctx.store.visits.get(visitRow(ctx.visitId))
  return (row?.data as VisitState | undefined) ?? stateOf(ctx.base)
}

// --- Seeding (Prepare) ---------------------------------------------------------------------------

/**
 * Put a bundle's boards and the visit's state into Dexie. What the person already changed on the
 * phone is left alone: preparing again takes in the server's changes, never over the phone's own.
 */
export async function seed (userId: string, bundle: FieldBundle, store: MmsDb = db): Promise<void> {
  await store.transaction('rw', store.visits, async () => {
    for (const item of bundle.stations) {
      for (const element of item.board) {
        const existing = await store.visits.get(element.id)
        if (existing?.dirty) {
          continue
        }
        await store.visits.put({
          id: element.id, user_id: userId, visit_id: bundle.visit.id, station_id: element.station_id,
          data: element, dirty: false,
        })
      }
    }
    const existing = await store.visits.get(visitRow(bundle.visit.id))
    if (!existing?.dirty) {
      await store.visits.put({
        id: visitRow(bundle.visit.id), user_id: userId, visit_id: bundle.visit.id,
        data: stateOf(bundle.visit), dirty: false,
      })
    }
  })
}

// --- Reading -------------------------------------------------------------------------------------

export async function visitView (ctx: Context): Promise<VisitOut> {
  return overlay(ctx.base, await stateOfVisit(ctx), ctx.me)
}

function open (state: VisitState): void {
  if (state.status === 'cancelled') {
    throw refusal('visit_cancelled', 'This visit was cancelled')
  }
  if (state.status === 'planned') {
    throw refusal('not_started', 'Start the visit first')
  }
}

export async function listElements (ctx: Context, stationId: string): Promise<BoardElementList> {
  const rows = await ctx.store.visits.where('[visit_id+station_id]').equals([ctx.visitId, stationId]).toArray()
  const items = rows
    .filter(r => r.user_id === ctx.userId)
    .map(r => ({ ...(r.data as BoardElement), can_edit: canEdit(r.data as BoardElement, ctx.base, stationId, ctx.me) }))
  const state = await stateOfVisit(ctx)
  const canAdd = attends(ctx.base, ctx.me) && (state.status === 'started' || state.status === 'ended')
  return { items, can_add: canAdd } as BoardElementList
}

// --- Writing -------------------------------------------------------------------------------------

const who = (ctx: Context) => ({ userId: ctx.userId, visitId: ctx.visitId })

type Tx = (add: (...ops: NewOp[]) => Promise<void>) => Promise<void>

/** One Dexie transaction for a change and its ops. Only Dexie calls inside. */
async function within (ctx: Context, run: Tx): Promise<void> {
  const { store } = ctx
  await store.transaction('rw', [store.visits, store.outbox, store.blobs], async () => {
    await run(async (...ops) => {
      for (const op of ops) {
        await store.outbox.add(op)
      }
    })
  })
}

/** This element's changes that are waiting and not in the runner's hands. */
async function waitingFor (ctx: Context, elementId: string): Promise<OutboxOp[]> {
  const mine = await ctx.store.outbox.where('[user_id+visit_id]').equals([ctx.userId, ctx.visitId]).filter(op => op.status === 'pending' && !op.inflight).sortBy('seq')
  return mine.filter(op => {
    const p = op.payload as { id?: string, element_id?: string }
    return op.type.startsWith('element.') && (p.element_id === elementId || (op.type === 'element.create' && p.id === elementId))
  })
}

function contentOf (element: BoardElement) {
  return {
    title: element.title,
    description: element.description,
    items: element.items.map(i => ({ id: i.id, text: i.text, done: i.done })),
    priority: element.priority,
    shared: element.shared,
  }
}

async function row (ctx: Context, elementId: string): Promise<LocalVisit | undefined> {
  const found = await ctx.store.visits.get(elementId)
  return found && found.user_id === ctx.userId && found.visit_id === ctx.visitId ? found : undefined
}

function allowedToEdit (ctx: Context, element: BoardElement, stationId: string, state: VisitState): void {
  if (!canEdit(element, ctx.base, stationId, ctx.me)) {
    throw refusal('not_editor', 'Only the person who added it or the station’s owner can change it', 403)
  }
  open(state)
}

export async function createElement (ctx: Context, stationId: string, body: BoardElementIn): Promise<BoardElement> {
  const state = await stateOfVisit(ctx)
  const existing = await row(ctx, body.id)
  if (existing) {
    return existing.data as BoardElement // the same id again: the element that was made
  }
  if (!attends(ctx.base, ctx.me)) {
    throw refusal('not_attending', 'Only the people attending can do this', 403)
  }
  open(state)
  const now = new Date().toISOString()
  const element = buildElement(body, ctx.base, stationId, ctx.me, now)
  await within(ctx, async add => {
    await ctx.store.visits.put({
      id: element.id, user_id: ctx.userId, visit_id: ctx.visitId, station_id: stationId, data: element, dirty: true,
    })
    await add(createElementOp(who(ctx), stationId, { id: element.id, kind: element.kind, ...contentOf(element) }))
  })
  return element
}

export async function saveElement (
  ctx: Context, stationId: string, elementId: string, body: BoardElementPut,
): Promise<BoardElement> {
  const found = await row(ctx, elementId)
  if (!found) {
    throw refusal('element_deleted', 'This was deleted')
  }
  const element = found.data as BoardElement
  allowedToEdit(ctx, element, stationId, await stateOfVisit(ctx))
  const now = new Date().toISOString()
  let saved = element
  await within(ctx, async add => {
    const waiting = await waitingFor(ctx, elementId)
    const fold = waiting.findLast(op => op.type === 'element.update')
      ?? waiting.find(op => op.type === 'element.create')
    saved = applySave(element, body, ctx.me, now, fold !== undefined)
    if (saved === element) {
      return
    }
    const content = contentOf(saved)
    await (fold ? ctx.store.outbox.update(fold.seq!, { payload: { ...(fold.payload as object), ...content } }) : add(updateElementOp(who(ctx), stationId, elementId, content, element.version)))
    await ctx.store.visits.put({ ...found, data: saved, dirty: true })
  })
  return saved
}

/** Drop what has not been sent for an element (and the files that were waiting for it). */
async function forget (ctx: Context, ops: readonly OutboxOp[]): Promise<void> {
  for (const op of ops) {
    await ctx.store.outbox.delete(op.seq!)
    if (op.blob_id) {
      await ctx.store.blobs.delete(op.blob_id)
    }
  }
}

export async function removeElement (ctx: Context, stationId: string, elementId: string, baseVersion: number): Promise<void> {
  const found = await row(ctx, elementId)
  if (!found) {
    return // already gone: deleting again changes nothing
  }
  const element = found.data as BoardElement
  allowedToEdit(ctx, element, stationId, await stateOfVisit(ctx))
  if (baseVersion !== element.version) {
    throw refusal('element_changed', 'This was changed on another device', 409, { current: element })
  }
  await within(ctx, async add => {
    const waiting = await waitingFor(ctx, elementId)
    const unsent = waiting.some(op => op.type === 'element.create')
    await forget(ctx, waiting)
    await ctx.store.visits.delete(elementId)
    if (!unsent) {
      await add(deleteElementOp(who(ctx), stationId, elementId, element.version))
    }
  })
}

export interface Capture {
  mediaId: string
  file: Blob
  name: string
  kind: BoardMedia['kind']
  sha256: string
  caption?: string | null
  capturedAt?: string | null
}

/** A photo, video or file kept on the phone and queued to go on an element (OFF-2, OFF-6). */
export async function captureMedia (
  ctx: Context, stationId: string, elementId: string, section: string, capture: Capture,
): Promise<BoardElement> {
  const found = await row(ctx, elementId)
  if (!found) {
    throw refusal('element_deleted', 'This was deleted')
  }
  const element = found.data as BoardElement
  allowedToEdit(ctx, element, stationId, await stateOfVisit(ctx))
  const now = new Date().toISOString()
  const entry: BoardMedia = {
    media_id: capture.mediaId, kind: capture.kind, filename: capture.name, caption: capture.caption ?? null,
    captured_at: capture.capturedAt ?? null, hidden: false, size_bytes: capture.file.size, added_at: now,
    added_by: { id: ctx.me.id, name: ctx.me.name },
  }
  const next = withMedia(element, section as never, entry)
  await within(ctx, async add => {
    await ctx.store.blobs.put({
      media_id: capture.mediaId, user_id: ctx.userId, visit_id: ctx.visitId,
      owner_ref: ownerRef(ctx.visitId, stationId, elementId, section as never),
      file: capture.file, size: capture.file.size, sha256: capture.sha256, state: 'pending',
      name: capture.name, kind: capture.kind,
    })
    await ctx.store.visits.put({ ...found, data: next, dirty: true })
    await add(mediaAddOp(who(ctx), stationId, elementId, {
      mediaId: capture.mediaId, section, caption: capture.caption ?? null, capturedAt: capture.capturedAt ?? null,
    }))
  })
  return next
}

export async function removeMedia (ctx: Context, stationId: string, elementId: string, mediaId: string): Promise<BoardElement> {
  const found = await row(ctx, elementId)
  if (!found) {
    throw refusal('element_deleted', 'This was deleted')
  }
  const element = found.data as BoardElement
  allowedToEdit(ctx, element, stationId, await stateOfVisit(ctx))
  const next = withoutMedia(element, mediaId)
  await within(ctx, async add => {
    const waiting = await waitingFor(ctx, elementId)
    const unsent = waiting.find(op => op.type === 'element.media_add' && (op.payload as { media_id?: string }).media_id === mediaId)
    await (unsent ? forget(ctx, [unsent]) : add(mediaRemoveOp(who(ctx), stationId, elementId, mediaId)))
    await ctx.store.visits.put({ ...found, data: next, dirty: true })
  })
  return next
}

/** A caption can change here only while its photo has not gone up; anything else needs the server. */
export async function changeCaption (
  ctx: Context, stationId: string, elementId: string, mediaId: string, caption: string | null,
): Promise<BoardElement> {
  const found = await row(ctx, elementId)
  if (!found) {
    throw refusal('element_deleted', 'This was deleted')
  }
  const element = found.data as BoardElement
  allowedToEdit(ctx, element, stationId, await stateOfVisit(ctx))
  const waiting = await waitingFor(ctx, elementId)
  const unsent = waiting.find(op => op.type === 'element.media_add' && (op.payload as { media_id?: string }).media_id === mediaId)
  if (!unsent) {
    throw new NetworkError(undefined) // already on the server: the caption changes with a connection
  }
  const next: BoardElement = {
    ...element,
    media: Object.fromEntries(Object.entries(element.media).map(([section, list]) => [
      section, list.map(m => (m.media_id === mediaId ? { ...m, caption } : m)),
    ])),
  }
  await within(ctx, async () => {
    await ctx.store.outbox.update(unsent.seq!, { payload: { ...(unsent.payload as object), caption } })
    await ctx.store.visits.put({ ...found, data: next, dirty: true })
  })
  return next
}

// --- The visit's own moves -----------------------------------------------------------------------

async function move (ctx: Context, change: (state: VisitState, at: string) => VisitState, op: (at: string) => NewOp): Promise<VisitOut> {
  const state = await stateOfVisit(ctx)
  const at = new Date().toISOString()
  const next = change(state, at)
  if (next !== state) {
    await within(ctx, async add => {
      await ctx.store.visits.put({
        id: visitRow(ctx.visitId), user_id: ctx.userId, visit_id: ctx.visitId, data: next, dirty: true,
      })
      await add(op(at))
    })
  }
  return overlay(ctx.base, next, ctx.me)
}

export function startVisit (ctx: Context): Promise<VisitOut> {
  return move(ctx, (s, at) => start(ctx.base, s, ctx.me, at), at => startOp(who(ctx), at))
}

export function arriveAt (ctx: Context, stationId: string): Promise<VisitOut> {
  return move(ctx, (s, at) => arrive(ctx.base, s, ctx.me, stationId, at), at => arriveOp(who(ctx), stationId, at))
}

export function departFrom (ctx: Context, stationId: string): Promise<VisitOut> {
  return move(ctx, (s, at) => depart(ctx.base, s, ctx.me, stationId, at), at => departOp(who(ctx), stationId, at))
}

export function endVisit (
  ctx: Context, body: { additional_visit_required: boolean, follow_up_notes?: string | null },
): Promise<VisitOut> {
  return move(
    ctx,
    (s, at) => end(ctx.base, s, ctx.me, { ...body, at }),
    at => endOp(who(ctx), { additional_visit_required: body.additional_visit_required, follow_up_notes: (body.follow_up_notes ?? '').trim() || null, at }),
  )
}

// --- What the server confirmed -------------------------------------------------------------------

/**
 * An op was applied: take the server's copy into the phone (unless the phone is already ahead of
 * it), and when the visit's end is applied and nothing is left for it, let the visit go (OFF-8).
 * Runs inside the transaction that removes the op.
 */
export async function adoptApplied (op: OutboxOp, answer: Answer, store: MmsDb = db): Promise<void> {
  const result = answer.result as Record<string, unknown> | null | undefined
  const others = await store.outbox.where('[user_id+visit_id]').equals([op.user_id, op.visit_id]).filter(o => o.seq !== op.seq).toArray()
  const payload = op.payload as { id?: string, element_id?: string, media_id?: string }
  const elementId = op.type === 'element.create' ? payload.id : payload.element_id

  if (elementId) {
    const mine = await store.visits.get(elementId)
    const ahead = others.some(o => {
      const p = o.payload as { id?: string, element_id?: string }
      return p.element_id === elementId || (o.type === 'element.create' && p.id === elementId)
    })
    if (mine && !ahead && result && typeof result.id === 'string') {
      await store.visits.put({ ...mine, data: result as unknown as BoardElement, dirty: false })
    } else if (mine && !ahead) {
      await store.visits.put({ ...mine, dirty: false })
    }
  }
  if (op.type === 'element.media_add' && payload.media_id) {
    await store.blobs.delete(payload.media_id) // the server holds the file and has put it on the element
  }
  if (op.type.startsWith('visit.') || op.type.startsWith('station.')) {
    const mine = await store.visits.get(visitRow(op.visit_id))
    const ahead = others.some(o => o.type.startsWith('visit.') || o.type.startsWith('station.'))
    if (mine && !ahead) {
      await store.visits.put({ ...mine, dirty: false })
    }
  }
  if (op.type === 'visit.end' && others.length === 0) {
    const pendingFiles = await store.blobs.where('user_id').equals(op.user_id).filter(b => b.visit_id === op.visit_id && b.state !== 'diagnostic').count()
    if (pendingFiles === 0) {
      await store.bundles.delete(op.visit_id)
      await store.files.where('[visit_id+media_id]').between([op.visit_id, Dexie.minKey], [op.visit_id, Dexie.maxKey]).delete()
      await store.visits.where('visit_id').equals(op.visit_id).delete()
    }
  }
}
