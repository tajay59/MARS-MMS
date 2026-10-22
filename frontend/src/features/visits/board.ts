import type { BoardElement, BoardElementIn, BoardElementPut, BoardItem, BoardMedia, BoardSummary, ElementKind, ElementSection } from '@/api/models'
import { ApiError } from '@/api/problem'
import { icons } from '@/app/theme/icons'
import { failureOf } from './failures'
import { SECTIONS } from './media'

/*
  A station's board on a visit (PRD VIS-5, VIS-7; W11-16 to W11-35): the rules its screens share.
  No Vue here.
*/

export interface KindLook {
  label: string
  /** The menu's one line about it. */
  hint: string
  icon: string
  /** Tailwind classes: the accent (top edge, icon, label) and the pale tint (sheet header, swatch). */
  accent: string
  edge: string
  tint: string
  /** The accent as a fill: a task's progress bar, a ticked box. */
  fill: string
  /** Shared with the client unless someone switches it off (W11-28). */
  sharedByDefault: boolean
  /** Whether its file sections take any file, not only photos and video. */
  anyFile: boolean
}

export const KINDS: readonly ElementKind[] = ['note', 'task', 'recommendation', 'config']

export const KIND: Record<ElementKind, KindLook> = {
  note: {
    label: 'Note', hint: 'Something you saw, with photos or video', icon: icons.note,
    accent: 'text-on-sticky-note', edge: 'border-t-on-sticky-note', tint: 'bg-sticky-note', fill: 'bg-on-sticky-note', sharedByDefault: false, anyFile: false,
  },
  task: {
    label: 'Task', hint: 'Work to do, with a checklist and before and after photos', icon: icons.task,
    accent: 'text-on-sticky-task', edge: 'border-t-on-sticky-task', tint: 'bg-sticky-task', fill: 'bg-on-sticky-task', sharedByDefault: true, anyFile: false,
  },
  recommendation: {
    label: 'Recommendation', hint: 'Work the client should plan for, with a priority', icon: icons.recommendation,
    accent: 'text-on-sticky-recommendation', edge: 'border-t-on-sticky-recommendation', tint: 'bg-sticky-recommendation', fill: 'bg-on-sticky-recommendation', sharedByDefault: true, anyFile: false,
  },
  config: {
    label: 'Config', hint: 'Logger or modem files, before and after a change', icon: icons.config,
    accent: 'text-on-sticky-config', edge: 'border-t-on-sticky-config', tint: 'bg-sticky-config', fill: 'bg-on-sticky-config', sharedByDefault: false, anyFile: true,
  },
}

export const PRIORITY_LABEL = { low: 'Low', medium: 'Medium', high: 'High' } as const

export const MAX_TITLE = 80
export const MAX_DESCRIPTION = 4000
export const MAX_ITEMS = 50
export const MAX_ITEM = 200

// --- The board ----------------------------------------------------------------------------------

export type BoardFilter = 'all' | ElementKind

export const FILTER_LABEL: Record<BoardFilter, string> = {
  all: 'All', note: 'Notes', task: 'Tasks', recommendation: 'Recommendations', config: 'Config',
}

export function counts (elements: readonly BoardElement[]): Record<BoardFilter, number> {
  const out: Record<BoardFilter, number> = { all: elements.length, note: 0, task: 0, recommendation: 0, config: 0 }
  for (const element of elements) {
    out[element.kind]++
  }
  return out
}

/** Newest first, as the server sends them; a filter keeps one kind. */
export function shown (elements: readonly BoardElement[], filter: BoardFilter): BoardElement[] {
  const list = filter === 'all' ? [...elements] : elements.filter(e => e.kind === filter)
  return list.toSorted((a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id))
}

export function allMedia (element: Pick<BoardElement, 'media'>): BoardMedia[] {
  return Object.values(element.media).flat()
}

/** "4 files", "2 photos", "1 before · 1 after", or "No files". */
export function filesText (element: Pick<BoardElement, 'kind' | 'media'>): string {
  if (element.kind === 'config') {
    const before = element.media.before?.length ?? 0
    const after = element.media.after?.length ?? 0
    return before + after === 0 ? 'No files' : `${before} before · ${after} after`
  }
  const files = allMedia(element)
  if (files.length === 0) {
    return 'No files'
  }
  const photos = files.every(f => f.kind === 'image')
  const noun = photos ? (files.length === 1 ? 'photo' : 'photos') : (files.length === 1 ? 'file' : 'files')
  return `${files.length} ${noun}`
}

/** The newest photo or video on an element, for its sticky note. */
export function cover (element: Pick<BoardElement, 'media'>): BoardMedia | null {
  return allMedia(element)
    .filter(m => m.kind === 'image' || m.kind === 'video')
    .toSorted((a, b) => b.added_at.localeCompare(a.added_at))[0] ?? null
}

export function progress (items: readonly Pick<BoardItem, 'done'>[]): { done: number, total: number, percent: number } {
  const done = items.filter(i => i.done).length
  return { done, total: items.length, percent: items.length === 0 ? 0 : Math.round((done / items.length) * 100) }
}

/** Initials for the author's avatar: "AC" for Andrea Clarke. */
export function initials (name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) {
    return '?'
  }
  return ((parts[0]![0] ?? '') + (parts.length > 1 ? (parts.at(-1)![0] ?? '') : '')).toUpperCase()
}

export function sectionsOf (kind: ElementKind): readonly ElementSection[] {
  return SECTIONS[kind]
}

// --- Saving -------------------------------------------------------------------------------------

/** What the sheet edits; the server's copy is the starting point. */
export interface Draft {
  title: string
  description: string
  items: { id: string, text: string, done: boolean }[]
  priority: BoardElement['priority']
  shared: boolean
}

export function draftOf (element: BoardElement): Draft {
  return {
    title: element.title,
    description: element.description ?? '',
    items: element.items.map(i => ({ id: i.id, text: i.text, done: i.done })),
    priority: element.priority,
    shared: element.shared,
  }
}

export function putBody (draft: Draft, baseVersion: number, deviceId?: string | null): BoardElementPut {
  return {
    title: draft.title.trim(),
    description: draft.description.trim() || null,
    items: draft.items.map(i => ({ id: i.id, text: i.text.trim(), done: i.done })),
    priority: draft.priority,
    shared: draft.shared,
    base_version: baseVersion,
    device_id: deviceId ?? null,
  }
}

/** A new element: its device-made id makes a retry return the one already made (W11-26). */
export function createBody (id: string, kind: ElementKind, draft: Draft, deviceId?: string | null): BoardElementIn {
  const { base_version: _base, ...content } = putBody(draft, 1, deviceId)
  return { id, kind, ...content }
}

/** Whether the draft says something other than what is saved (trimmed, as the server compares). */
export function changed (draft: Draft, element: BoardElement): boolean {
  const saved = draftOf(element)
  return draft.title.trim() !== saved.title
    || (draft.description.trim() || '') !== (saved.description || '')
    || draft.priority !== saved.priority
    || draft.shared !== saved.shared
    || JSON.stringify(draft.items.map(i => [i.id, i.text.trim(), i.done])) !== JSON.stringify(saved.items.map(i => [i.id, i.text, i.done]))
}

/** A field's problem before the server sees it, or null. */
export function titleProblem (title: string): string | null {
  const text = title.trim()
  if (!text) {
    return 'Give it a title.'
  }
  return text.length > MAX_TITLE ? `Keep the title under ${MAX_TITLE} characters.` : null
}

/** Move an item up (-1) or down (+1); the ends stay put. */
export function moved<T> (list: readonly T[], index: number, by: -1 | 1): T[] {
  const to = index + by
  if (to < 0 || to >= list.length) {
    return [...list]
  }
  const out = [...list]
  ;[out[index], out[to]] = [out[to]!, out[index]!]
  return out
}

const REFUSALS: Record<string, string> = {
  element_changed: 'This was changed on another device. Here is the saved copy.',
  element_deleted: 'This was deleted. Nothing you change here will be saved.',
  duplicate_id: 'Something went wrong adding this. Try again.',
  not_editor: 'Only the person who added this, or the station’s owner, can change it.',
  not_attending: 'Only the people attending this visit can add to its board.',
  not_started: 'Start the visit first.',
  visit_cancelled: 'This visit was cancelled.',
  locked: 'The visit report has been finalized. Ask an admin to reopen it.',
  board_full: 'This board is full. Delete something you no longer need first.',
  title_required: 'Give it a title.',
}

/** What to tell the person when a change to the board fails. */
export function boardFailure (error: unknown, fallback: string): string {
  if (error instanceof ApiError && REFUSALS[error.code]) {
    return REFUSALS[error.code]!
  }
  return failureOf(error, fallback).message
}

/** The saved copy a 409 `element_changed` carries, if any. */
export function currentOf (error: unknown): BoardElement | null {
  if (error instanceof ApiError && error.code === 'element_changed') {
    const current = error.body.current
    return current && typeof current === 'object' ? current as BoardElement : null
  }
  return null
}

/** "2 notes · 3 tasks, 1 incomplete · 1 recommendation", or that nothing is recorded yet. */
export function summaryText (board: BoardSummary): string {
  const parts: string[] = []
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  if (board.note > 0) {
    parts.push(count(board.note, 'note', 'notes'))
  }
  if (board.task > 0) {
    const tasks = count(board.task, 'task', 'tasks')
    parts.push(board.incomplete_tasks > 0 ? `${tasks}, ${board.incomplete_tasks} incomplete` : tasks)
  }
  if (board.recommendation > 0) {
    parts.push(count(board.recommendation, 'recommendation', 'recommendations'))
  }
  if (board.config > 0) {
    parts.push(count(board.config, 'configuration', 'configurations'))
  }
  return parts.length > 0 ? parts.join(' · ') : 'Nothing recorded yet'
}
