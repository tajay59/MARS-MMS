// Checklist templates (PRD VIS-8, AFD /admin/checklists, W10): what the editor does with a draft.
// Pure functions, so Vitest covers them without a screen.

import type { ChecklistItem, ChecklistTemplate } from '@/api/models'
import { ApiError, NetworkError } from '@/api/problem'

export const MAX_ITEMS = 60
export const MAX_LABEL = 200
export const MAX_HELP = 500
export const MAX_NAME = 100

/** One item as the editor holds it. `key` tells rows apart while typing; `id` is the server's, kept across versions. */
export interface DraftItem {
  key: string
  id: string | null
  label: string
  help: string
}

export interface Draft {
  name: string
  active: boolean
  items: DraftItem[]
}

/** What a new template is for: a station type, or one sensor model's add-on. */
export interface Scope {
  kind: 'type' | 'model'
  type: string
  modelId: string | null
}

export function emptyScope (): Scope {
  return { kind: 'type', type: '', modelId: null }
}

let counter = 0

export function blankItem (): DraftItem {
  counter++
  return { key: `new-${counter}`, id: null, label: '', help: '' }
}

export function draftOf (template: ChecklistTemplate | null): Draft {
  if (template === null) {
    return { name: '', active: true, items: [blankItem()] }
  }
  return {
    name: template.name,
    active: template.active,
    items: template.items.map((item: ChecklistItem) => ({ key: item.id, id: item.id, label: item.label, help: item.help ?? '' })),
  }
}

/** Has anything been changed since the draft was made from `template`? */
export function isDirty (draft: Draft, template: ChecklistTemplate | null): boolean {
  const base = draftOf(template)
  if (draft.name.trim() !== base.name.trim() || draft.active !== base.active) {
    return true
  }
  if (draft.items.length !== base.items.length) {
    return true
  }
  return draft.items.some((item, i) => {
    const was = base.items[i]
    return item.id !== was?.id || item.label.trim() !== was.label.trim() || item.help.trim() !== was.help.trim()
  })
}

/** Which rows changed, for the tint: an item that is new, edited or moved from where it was. */
export function changedKeys (draft: Draft, template: ChecklistTemplate | null): Set<string> {
  const base = draftOf(template).items
  const changed = new Set<string>()
  for (const [i, item] of draft.items.entries()) {
    const was = base[i]
    if (item.id === null || item.id !== was?.id || item.label.trim() !== was.label.trim() || item.help.trim() !== was.help.trim()) {
      changed.add(item.key)
    }
  }
  return changed
}

/** What stops a save: empty name, no items, an item with no name. */
export function problemsOf (draft: Draft, scope?: Scope): string[] {
  const problems: string[] = []
  if (scope && (scope.kind === 'type' ? scope.type.trim() === '' : !scope.modelId)) {
    problems.push(scope.kind === 'type' ? 'Say which station type it is for' : 'Choose the sensor model')
  }
  if (draft.name.trim() === '') {
    problems.push('Give the template a name')
  }
  if (draft.items.length === 0) {
    problems.push('Add at least one item')
  }
  if (draft.items.some(item => item.label.trim() === '')) {
    problems.push('Every item needs a name')
  }
  return problems
}

export function move<T> (list: readonly T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) {
    return [...list]
  }
  const copy = [...list]
  const [taken] = copy.splice(from, 1)
  copy.splice(to, 0, taken as T)
  return copy
}

/** The items as the API takes them: ids kept, text trimmed, empty help left out. */
export function itemsForApi (draft: Draft): { id?: string, label: string, help: string | null }[] {
  return draft.items.map(item => ({
    ...(item.id ? { id: item.id } : {}),
    label: item.label.trim(),
    help: item.help.trim() || null,
  }))
}

/** "Station type · AWS" or "Sensor model · add-on". */
export function scopeLabel (template: Pick<ChecklistTemplate, 'station_type' | 'sensor_model_id' | 'sensor_model_name'>): string {
  return template.station_type ? `Station type · ${template.station_type}` : 'Sensor model · add-on'
}

/** What the "Applies to" field says: the type, or the model by name. */
export function appliesTo (template: Pick<ChecklistTemplate, 'station_type' | 'sensor_model_name'>): string {
  return template.station_type ? `Stations of type ${template.station_type}` : `Sensor model · ${template.sensor_model_name ?? 'unknown'}`
}

export function itemCount (n: number): string {
  return `${n} ${n === 1 ? 'item' : 'items'}`
}

/** The message a failed save or load shows, in the DBD's plain voice. */
export function failureText (error: unknown): { text: string, reload: boolean } {
  if (error instanceof NetworkError) {
    return { text: 'This needs a connection. Try again when you have signal.', reload: false }
  }
  if (error instanceof ApiError) {
    if (error.code === 'version_conflict') {
      return { text: 'Someone saved a newer version while you were editing. Reload to see it; your changes here are not saved.', reload: true }
    }
    if (error.code === 'template_exists') {
      return { text: 'There is already an active template for that. Make the other one inactive first.', reload: false }
    }
    if (error.status === 422) {
      return { text: error.detail, reload: false }
    }
    if (error.status === 403 || error.status === 404) {
      return { text: 'That template is not available to you.', reload: false }
    }
  }
  return { text: 'We could not save that. Try again.', reload: false }
}

/** Search the pane's list by name, type or model. */
export function matches (template: ChecklistTemplate, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) {
    return true
  }
  return [template.name, template.station_type, template.sensor_model_name]
    .some(text => (text ?? '').toLowerCase().includes(q))
}

/** The station types in use, once each and A to Z, for the type field's suggestions. */
export function typesOf (stations: readonly { type: string | null }[]): string[] {
  const types = new Set<string>()
  for (const station of stations) {
    if (station.type) {
      types.add(station.type)
    }
  }
  // Fresh array: sorting it in place is safe, and toSorted needs iOS 16
  // eslint-disable-next-line unicorn/no-array-sort
  return [...types].sort((a, b) => a.localeCompare(b))
}
