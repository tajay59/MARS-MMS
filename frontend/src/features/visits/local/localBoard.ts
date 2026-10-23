import type { Me } from './localVisit'
import type { BoardElement, BoardElementIn, BoardElementPut, BoardItem, BoardMedia, ElementKind, VisitOut } from '@/api/models'
import { MAX_DESCRIPTION, MAX_ITEM, MAX_ITEMS, MAX_TITLE } from '../board'
import { SECTIONS } from '../media'
import { refusal } from './localVisit'

/*
  A station's board on the phone (W14-7): the element as the board shows it, built and changed here
  when there is no server to ask. It mirrors the rules in `domain/visits/elements.py` (a title,
  a task's checklist and who ticked what, a recommendation's priority, sharing by kind, who may
  edit, how `version` moves) well enough for the screen, and throws the same refusals; the server
  judges the same operations again when they sync. No Vue, no Dexie.
*/

const SHARED: Record<ElementKind, boolean> = { note: false, task: true, recommendation: true, config: false }

function text (value: string | null | undefined, field: string, limit: number, required = false): string | null {
  const clean = (value ?? '').trim()
  if (required && !clean) {
    throw refusal('title_required', 'Give it a title', 422)
  }
  if (clean.length > limit) {
    throw refusal('too_long', `Keep ${field} under ${limit} characters`, 422)
  }
  return clean || null
}

function items (
  kind: ElementKind, given: readonly { id: string, text: string, done: boolean }[] | undefined,
  before: readonly BoardItem[], me: Me, now: string,
): BoardItem[] {
  if (kind !== 'task') {
    if (given && given.length > 0) {
      throw refusal('items_not_allowed', 'Only a task has items', 422)
    }
    return []
  }
  const list = given ?? []
  if (list.length > MAX_ITEMS) {
    throw refusal('too_many_items', `A task can have up to ${MAX_ITEMS} items`, 422)
  }
  const old = new Map(before.map(i => [i.id, i]))
  const seen = new Set<string>()
  return list.map(item => {
    if (seen.has(item.id)) {
      throw refusal('duplicate_id', 'Two items share an id', 422)
    }
    seen.add(item.id)
    const words = text(item.text, 'an item', MAX_ITEM)
    if (words === null) {
      throw refusal('item_required', 'An item needs some text', 422)
    }
    const was = old.get(item.id)
    if (item.done && was?.done) {
      return { id: item.id, text: words, done: true, done_by: was.done_by, done_at: was.done_at }
    }
    return item.done
      ? { id: item.id, text: words, done: true, done_by: me.id, done_at: now }
      : { id: item.id, text: words, done: false, done_by: null, done_at: null }
  })
}

function priority (kind: ElementKind, value: string | null | undefined): BoardElement['priority'] {
  if (kind !== 'recommendation') {
    if (value) {
      throw refusal('priority_not_allowed', 'Only a recommendation has a priority', 422)
    }
    return null
  }
  if (!value) {
    return 'medium'
  }
  if (value !== 'low' && value !== 'medium' && value !== 'high') {
    throw refusal('bad_priority', 'The priority can be: low, medium, high', 422)
  }
  return value
}

function completeness (kind: ElementKind, list: readonly BoardItem[], before: string | null, now: string) {
  const complete = kind === 'task' ? list.length > 0 && list.every(i => i.done) : null
  return { complete, completed_at: complete ? (before ?? now) : null }
}

/** Whether the person may change this element: its author, the station's owner, or an admin. */
export function canEdit (element: Pick<BoardElement, 'created_by'>, visit: VisitOut, stationId: string, me: Me): boolean {
  const station = visit.stations.find(s => s.station_id === stationId)
  return me.admin || element.created_by.id === me.id || station?.owner.id === me.id
}

/** A new element, as the server would answer a create (version 1). */
export function buildElement (
  body: BoardElementIn, visit: VisitOut, stationId: string, me: Me, now: string,
): BoardElement {
  const kind = body.kind
  const list = items(kind, body.items, [], me, now)
  const done = completeness(kind, list, null, now)
  return {
    id: body.id,
    visit_id: visit.id,
    station_id: stationId,
    kind,
    title: text(body.title, 'the title', MAX_TITLE, true) ?? '',
    description: text(body.description, 'the description', MAX_DESCRIPTION),
    items: list,
    complete: done.complete,
    completed_at: done.completed_at,
    priority: priority(kind, body.priority),
    request_ref: null,
    config_version_ids: [],
    config_versions: [],
    version_due: false,
    media: Object.fromEntries(SECTIONS[kind].map(s => [s, [] as BoardMedia[]])),
    shared: body.shared ?? SHARED[kind],
    created_by: { id: me.id, name: me.name },
    created_at: now,
    updated_at: now,
    version: 1,
    can_edit: true,
  }
}

function comparable (e: Pick<BoardElement, 'title' | 'description' | 'items' | 'priority' | 'shared'>) {
  return JSON.stringify([e.title, e.description, e.items.map(i => [i.id, i.text, i.done]), e.priority, e.shared])
}

/**
 * A save of the whole content. Same content: nothing changes (a retry). Otherwise `version` goes up
 * by one, unless the previous change has not been sent yet and can be folded into it
 * (`foldable`): then the server will move one version for both, so the phone's count must too.
 */
export function applySave (
  element: BoardElement, body: BoardElementPut, me: Me, now: string, foldable: boolean,
): BoardElement {
  if (body.base_version !== element.version) {
    throw refusal('element_changed', 'This was changed on another device', 409, { current: element })
  }
  const list = items(element.kind, body.items, element.items, me, now)
  const done = completeness(element.kind, list, element.completed_at, now)
  const next: BoardElement = {
    ...element,
    title: text(body.title, 'the title', MAX_TITLE, true) ?? '',
    description: text(body.description, 'the description', MAX_DESCRIPTION),
    items: list,
    complete: done.complete,
    completed_at: done.completed_at,
    priority: priority(element.kind, body.priority),
    shared: body.shared,
  }
  if (comparable(next) === comparable(element)) {
    return element
  }
  return { ...next, updated_at: now, version: foldable ? element.version : element.version + 1 }
}

export function withMedia (element: BoardElement, section: string, entry: BoardMedia): BoardElement {
  const sections = SECTIONS[element.kind] as readonly string[]
  if (!sections.includes(section)) {
    throw refusal('bad_section', `A ${element.kind} takes files in: ${sections.join(', ')}`, 422)
  }
  const there = element.media[section] ?? []
  if (Object.values(element.media).flat().some(m => m.media_id === entry.media_id)) {
    return element
  }
  return { ...element, media: { ...element.media, [section]: [...there, entry] }, updated_at: entry.added_at }
}

export function withoutMedia (element: BoardElement, mediaId: string): BoardElement {
  const media = Object.fromEntries(Object.entries(element.media).map(([section, list]) => [section, list.filter(m => m.media_id !== mediaId)]))
  return { ...element, media }
}
