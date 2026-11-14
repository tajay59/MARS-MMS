import type { OutboxOp } from './db'
import { newId } from '@/app/ids'

/*
  The operations a phone queues (TRD §7.2, W14-4). Each one is the body of the route that does the
  work online plus the station and element it is about, and `v`, the payload version, so an op
  queued by an older app still applies after an update (finding F8). The builders make an op with
  its own `op_id` (a UUIDv7, rule 9): the same op sent twice is applied once.

  No Vue, no DOM: the sync runner may one day run in the service worker.
*/

export const OP_VERSION = 1

export type NewOp = Omit<OutboxOp, 'seq'>

export type OpType
  = | 'visit.start' | 'station.arrive' | 'station.depart' | 'visit.end'
    | 'element.create' | 'element.update' | 'element.delete'
    | 'element.media_add' | 'element.media_remove'

export interface Who {
  userId: string
  visitId: string
}

function make (who: Who, type: OpType, payload: Record<string, unknown>, extra: Partial<NewOp> = {}, now: Date = new Date()): NewOp {
  return {
    op_id: newId(now.getTime()),
    v: OP_VERSION,
    user_id: who.userId,
    visit_id: who.visitId,
    type,
    payload,
    created_at: now.toISOString(),
    attempts: 0,
    status: 'pending',
    ...extra,
  }
}

export interface ItemBody { id: string, text: string, done: boolean }

export interface ElementContent {
  title: string
  description?: string | null
  items: ItemBody[]
  priority?: string | null
  shared: boolean
}

export const startOp = (who: Who, at: string): NewOp => make(who, 'visit.start', { at })

export function arriveOp (who: Who, stationId: string, at: string): NewOp {
  return make(who, 'station.arrive', { station_id: stationId, at })
}

export function departOp (who: Who, stationId: string, at: string): NewOp {
  return make(who, 'station.depart', { station_id: stationId, at })
}

export function endOp (who: Who, body: { additional_visit_required: boolean, follow_up_notes?: string | null, at: string }): NewOp {
  return make(who, 'visit.end', body)
}

export function createElementOp (who: Who, stationId: string, element: ElementContent & { id: string, kind: string }): NewOp {
  return make(who, 'element.create', { station_id: stationId, ...element })
}

export function updateElementOp (who: Who, stationId: string, elementId: string, content: ElementContent, baseVersion: number): NewOp {
  return make(who, 'element.update', {
    station_id: stationId, element_id: elementId, ...content, base_version: baseVersion,
  })
}

export function deleteElementOp (who: Who, stationId: string, elementId: string, baseVersion: number): NewOp {
  return make(who, 'element.delete', { station_id: stationId, element_id: elementId, base_version: baseVersion })
}

/** The file is uploaded first (`blob_id` is its `media_id`), then put on the element. */
export function mediaAddOp (who: Who, stationId: string, elementId: string,
  media: { mediaId: string, section: string, caption?: string | null, capturedAt?: string | null }): NewOp {
  return make(who, 'element.media_add', {
    station_id: stationId, element_id: elementId, media_id: media.mediaId, section: media.section,
    caption: media.caption ?? null, captured_at: media.capturedAt ?? null,
  }, { blob_id: media.mediaId })
}

export function mediaRemoveOp (who: Who, stationId: string, elementId: string, mediaId: string): NewOp {
  return make(who, 'element.media_remove', { station_id: stationId, element_id: elementId, media_id: mediaId })
}

/** What goes on the wire for one op. */
export function wire (op: OutboxOp): { op_id: string, v: number, type: string, visit_id: string, payload: unknown } {
  return { op_id: op.op_id, v: op.v, type: op.type, visit_id: op.visit_id, payload: op.payload }
}
