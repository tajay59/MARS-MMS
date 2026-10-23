import type { BoardElement, FieldBundle } from '@/api/models'
import type { LocalBlob, MmsDb, OutboxOp } from '@/offline/db'
import Dexie from 'dexie'
import { db } from '@/offline/db'
import { attention } from '@/offline/outbox'

/*
  Needs attention (AFD §6, TRD §7.4; W14-13). The outbox keeps an op the server did not apply
  with its reason; this module turns those into things a person can read and act on, one for each
  piece of work: an element with everything queued for it, or a move (arrive, depart, end). No
  Vue. The phone's copy stays until the person says "Done with this" (ADR-18, OFF-11).
*/

export interface Concern {
  /** Stable: the visit and the element (or op). */
  key: string
  visit_id: string
  /** The visit's reference and request title, from the prepared copy. */
  ref: string
  title: string
  station_id: string | null
  station: { code: string, name: string } | null
  /** The server's reason (`not_owner`, `element_changed`, …) or the refusal's code. */
  code: string
  /** The short label on the card: "Owner changed", "Visit cancelled". */
  what: string
  text: string
  /** Export is offered when the phone holds work that would otherwise be lost. */
  canExport: boolean
  /** Try again is offered when something else (an admin) can make the same ops succeed. */
  canRetry: boolean
  ops: OutboxOp[]
  /** The element as the phone holds it. */
  element: BoardElement | null
  /** The server's copy, when the answer carried it. */
  current: BoardElement | null
}

interface Words {
  what: string
  text: (where: string) => string
  canExport: boolean
  canRetry: boolean
}

const WORDS: Record<string, Words> = {
  not_owner: {
    what: 'Owner changed',
    text: where => `Someone else owns ${where} now. Your work on it is saved on this phone; export it and pass it on.`,
    canExport: true,
    canRetry: false,
  },
  not_editor: {
    what: 'Owner changed',
    text: where => `You can no longer change this at ${where}. Your copy is saved on this phone; export it and pass it on.`,
    canExport: true,
    canRetry: false,
  },
  element_changed: {
    what: 'Changed on another device',
    text: () => 'This was changed on another device while you were offline. Your version is saved on this phone; the server keeps theirs.',
    canExport: true,
    canRetry: false,
  },
  element_deleted: {
    what: 'Deleted elsewhere',
    text: () => 'This was deleted while you were offline. Your copy is saved on this phone; nothing is recreated.',
    canExport: true,
    canRetry: false,
  },
  locked: {
    what: 'Report is final',
    text: () => 'This visit’s report is final. Your changes are saved on this phone; ask an admin to reopen the report.',
    canExport: true,
    canRetry: false,
  },
  visit_cancelled: {
    what: 'Visit cancelled',
    text: () => 'This visit was cancelled while you were offline. Your work is saved on this phone and an admin has been told.',
    canExport: false,
    canRetry: true,
  },
  already_ended: {
    what: 'Already ended',
    text: () => 'Another person already ended this visit. Your other changes still apply; nothing is lost.',
    canExport: false,
    canRetry: true,
  },
}

const FALLBACK: Words = {
  what: 'Could not be saved',
  text: () => 'The server could not save this. Your work is safe on this phone.',
  canExport: true,
  canRetry: true,
}

/** What the person reads for a code. The server's own sentence is kept as a last line for codes we do not know. */
export function wordsFor (code: string | undefined): Words {
  return (code && WORDS[code]) || FALLBACK
}

function elementIdOf (op: OutboxOp): string | undefined {
  const payload = op.payload as { id?: string, element_id?: string }
  return op.type === 'element.create' ? payload.id : payload.element_id
}

function stationIdOf (op: OutboxOp): string | undefined {
  return (op.payload as { station_id?: string }).station_id
}

/** Ops that belong together: all of an element's, or a move on its own. */
export function keyOf (op: OutboxOp): string {
  const element = elementIdOf(op)
  return element ? `${op.visit_id}:${element}` : `${op.visit_id}:${op.op_id}`
}

function stationOf (bundle: FieldBundle | undefined, id: string | undefined): Concern['station'] {
  const found = bundle?.stations.find(s => s.station.id === id)
  return found ? { code: found.station.code, name: found.station.name } : null
}

/** Everything the phone has that the server refused, grouped, oldest first. */
export async function concerns (userId: string, store: MmsDb = db): Promise<Concern[]> {
  const stuck = await attention(userId, store)
  const groups = new Map<string, OutboxOp[]>()
  for (const op of stuck) {
    const key = keyOf(op)
    groups.set(key, [...(groups.get(key) ?? []), op])
  }
  const out: Concern[] = []
  for (const [key, ops] of groups) {
    const lead = ops.find(op => op.status === 'conflict') ?? ops[0]!
    const row = await store.bundles.get(lead.visit_id)
    const bundle = row?.data as FieldBundle | undefined
    const stationId = stationIdOf(lead) ?? null
    const station = stationOf(bundle, stationId ?? undefined)
    const elementId = elementIdOf(lead)
    const local = elementId ? await store.visits.get(elementId) : undefined
    const words = wordsFor(lead.code)
    const where = station ? `${station.name} (${station.code})` : 'this station'
    const known = lead.code && WORDS[lead.code]
    out.push({
      key,
      visit_id: lead.visit_id,
      ref: bundle?.visit.ref ?? 'Visit',
      title: bundle?.visit.request_title ?? '',
      station_id: stationId,
      station,
      code: lead.code ?? 'error',
      what: words.what,
      text: known ? words.text(where) : (lead.message ?? words.text(where)),
      canExport: words.canExport,
      canRetry: words.canRetry,
      ops,
      element: (local?.data as BoardElement | undefined) ?? null,
      current: (lead.current as BoardElement | undefined) ?? null,
    })
  }
  return out
}

/** The files the phone holds for an element (photos taken offline that never went up). */
export async function blobsFor (concern: Concern, store: MmsDb = db): Promise<LocalBlob[]> {
  const elementId = concern.element?.id ?? concern.ops.map(op => elementIdOf(op)).find(Boolean)
  if (!elementId) {
    return []
  }
  const mine = await store.blobs.where('user_id').equals(concern.ops[0]!.user_id).toArray()
  return mine.filter(blob => blob.owner_ref.includes(`:element:${elementId}:`) && blob.state !== 'diagnostic')
}

/** Send what was stuck again (an admin restored the visit, or the person is ready to try). */
export { retryStuck } from '@/offline/outbox'

/**
 * "Done with this": the phone lets go of the work the server refused. Its ops, the element's other
 * ops, the files taken for it and the element's copy go; when nothing else is left for the visit
 * the prepared copy goes too (OFF-8). Export is offered before this, never required by it.
 */
export async function doneWith (concern: Concern, store: MmsDb = db): Promise<void> {
  const userId = concern.ops[0]!.user_id
  const blobs = await blobsFor(concern, store)
  await store.transaction('rw', [store.outbox, store.visits, store.blobs, store.bundles, store.files], async () => {
    const mine = await store.outbox.where('[user_id+visit_id]').equals([userId, concern.visit_id]).toArray()
    const doomed = mine.filter(op => keyOf(op) === concern.key)
    await store.outbox.bulkDelete(doomed.map(op => op.seq!))
    for (const blob of blobs) {
      await store.blobs.delete(blob.media_id)
    }
    const elementId = concern.element?.id ?? doomed.map(op => elementIdOf(op)).find(Boolean)
    if (elementId) {
      await store.visits.delete(elementId)
    }
    const left = await store.outbox.where('[user_id+visit_id]').equals([userId, concern.visit_id]).count()
    const ended = (await store.visits.get(`visit:${concern.visit_id}`))?.data as { status?: string } | undefined
    if (left === 0 && ended?.status === 'ended') {
      await store.bundles.delete(concern.visit_id)
      await store.files.where('[visit_id+media_id]').between([concern.visit_id, Dexie.minKey], [concern.visit_id, Dexie.maxKey]).delete()
      await store.visits.where('visit_id').equals(concern.visit_id).delete()
    }
  })
}
