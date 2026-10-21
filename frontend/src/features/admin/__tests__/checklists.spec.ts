import type { ChecklistTemplate } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import {
  appliesTo,
  blankItem,
  changedKeys,
  draftOf,
  failureText,
  isDirty,
  itemCount,
  itemsForApi,
  matches,
  move,
  problemsOf,
  scopeLabel,
  typesOf,
} from '../checklists/checklists'

function template (patch: Partial<ChecklistTemplate> = {}): ChecklistTemplate {
  return {
    id: 'fam-1', name: 'Automatic weather station visit', station_type: 'AWS', sensor_model_id: null,
    sensor_model_name: null, version: 3, is_current: true, active: true,
    items: [
      { id: 'i1', label: 'Mast', help: null },
      { id: 'i2', label: 'Battery voltage', help: 'Note it' },
    ],
    created_at: '2026-10-14T09:00:00Z', ...patch,
  }
}

describe('a draft', () => {
  it('starts as one empty item for a new template and as the template for an existing one', () => {
    const fresh = draftOf(null)
    expect(fresh.name).toBe('')
    expect(fresh.active).toBe(true)
    expect(fresh.items).toHaveLength(1)
    const draft = draftOf(template())
    expect(draft.items.map(i => i.label)).toEqual(['Mast', 'Battery voltage'])
    expect(draft.items[1]).toMatchObject({ id: 'i2', help: 'Note it' })
  })

  it('is dirty only after a real change', () => {
    const t = template()
    const draft = draftOf(t)
    expect(isDirty(draft, t)).toBe(false)
    draft.items[0]!.label = '  Mast  ' // spaces around do not count
    expect(isDirty(draft, t)).toBe(false)
    draft.items[0]!.label = 'Mast and tower'
    expect(isDirty(draft, t)).toBe(true)
  })

  it('is dirty when the name, the switch, the order or the number of items changes', () => {
    const t = template()
    const renamed = draftOf(t)
    renamed.name = 'Visit'
    expect(isDirty(renamed, t)).toBe(true)
    const off = draftOf(t)
    off.active = false
    expect(isDirty(off, t)).toBe(true)
    const reordered = draftOf(t)
    reordered.items = move(reordered.items, 0, 1)
    expect(isDirty(reordered, t)).toBe(true)
    const added = draftOf(t)
    added.items.push(blankItem())
    expect(isDirty(added, t)).toBe(true)
    expect(isDirty(draftOf(null), null)).toBe(false)
  })

  it('says which rows to tint', () => {
    const t = template()
    const draft = draftOf(t)
    draft.items[1]!.label = 'Battery and charger'
    draft.items.push(blankItem())
    const changed = changedKeys(draft, t)
    expect(changed.has('i1')).toBe(false)
    expect(changed.has('i2')).toBe(true)
    expect(changed.size).toBe(2)
  })

  it('lists what stops a save', () => {
    const draft = draftOf(null)
    expect(problemsOf(draft)).toEqual(['Give the template a name', 'Every item needs a name'])
    draft.name = 'Visit'
    draft.items[0]!.label = 'Mast'
    expect(problemsOf(draft)).toEqual([])
    draft.items = []
    expect(problemsOf(draft)).toEqual(['Add at least one item'])
  })

  it('sends ids for items that have one, trimmed text, and no empty help', () => {
    const draft = draftOf(template())
    draft.items[0]!.label = ' Mast '
    draft.items.push({ ...blankItem(), label: 'Datalogger clock', help: '  ' })
    expect(itemsForApi(draft)).toEqual([
      { id: 'i1', label: 'Mast', help: null },
      { id: 'i2', label: 'Battery voltage', help: 'Note it' },
      { label: 'Datalogger clock', help: null },
    ])
  })
})

describe('move', () => {
  it('moves one item and leaves the list alone when the move makes no sense', () => {
    expect(move(['a', 'b', 'c'], 0, 2)).toEqual(['b', 'c', 'a'])
    expect(move(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b'])
    expect(move(['a', 'b'], 0, 0)).toEqual(['a', 'b'])
    expect(move(['a', 'b'], 0, 5)).toEqual(['a', 'b'])
    expect(move(['a', 'b'], -1, 1)).toEqual(['a', 'b'])
  })
})

describe('words', () => {
  it('names the scope and what it applies to', () => {
    expect(scopeLabel(template())).toBe('Station type · AWS')
    const addOn = template({ station_type: null, sensor_model_id: 'm1', sensor_model_name: 'Vaisala HMP155' })
    expect(scopeLabel(addOn)).toBe('Sensor model · add-on')
    expect(appliesTo(template())).toBe('Stations of type AWS')
    expect(appliesTo(addOn)).toBe('Sensor model · Vaisala HMP155')
    expect(itemCount(1)).toBe('1 item')
    expect(itemCount(12)).toBe('12 items')
  })

  it('searches by name, type and model', () => {
    const t = template()
    expect(matches(t, '')).toBe(true)
    expect(matches(t, 'weather')).toBe(true)
    expect(matches(t, 'aws')).toBe(true)
    expect(matches(t, 'radar')).toBe(false)
    expect(matches(template({ station_type: null, sensor_model_name: 'Vaisala HMP155' }), 'hmp')).toBe(true)
  })

  it('explains a failed save in plain words', () => {
    expect(failureText(new ApiError(409, { code: 'version_conflict' }))).toMatchObject({ reload: true })
    expect(failureText(new ApiError(409, { code: 'template_exists' })).text).toContain('already an active template')
    expect(failureText(new ApiError(422, { detail: 'Add at least one item' })).text).toBe('Add at least one item')
    expect(failureText(new ApiError(404, null)).reload).toBe(false)
    expect(failureText(new NetworkError(new Error('x'))).text).toContain('needs a connection')
    expect(failureText(new Error('boom')).text).toContain('Try again')
  })
})

describe('station types', () => {
  it('lists each type in use once, A to Z, without the empty ones', () => {
    expect(typesOf([{ type: 'Synoptic' }, { type: 'AWS' }, { type: null }, { type: 'AWS' }])).toEqual(['AWS', 'Synoptic'])
    expect(typesOf([])).toEqual([])
  })
})
