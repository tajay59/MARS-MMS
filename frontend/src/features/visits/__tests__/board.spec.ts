import type { BoardElement, BoardMedia, BoardSummary } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/problem'
import { boardFailure, changed, counts, cover, createBody, currentOf, draftOf, filesText, initials, KIND, moved, progress, putBody, shown, summaryText, titleProblem } from '../board'

function board (fields: Partial<BoardSummary> = {}): BoardSummary {
  return { note: 0, task: 0, recommendation: 0, config: 0, incomplete_tasks: 0, cover: null, ...fields }
}

function media (id: string, kind: BoardMedia['kind'] = 'image', added = '2026-10-22T13:00:00Z'): BoardMedia {
  return {
    media_id: id, kind, filename: `${id}.jpg`, size_bytes: 10, caption: null, captured_at: null,
    added_by: { id: 'u1', name: 'Andrea Clarke' }, added_at: added, hidden: false,
  }
}

function element (fields: Partial<BoardElement> = {}): BoardElement {
  return {
    id: 'e1', visit_id: 'v1', station_id: 's1', kind: 'note', title: 'Water inside the enclosure',
    description: null, items: [], complete: null, completed_at: null, priority: null, request_ref: null,
    config_version_ids: [], config_versions: [], version_due: false, media: { main: [] }, shared: false,
    created_by: { id: 'u1', name: 'Andrea Clarke' }, created_at: '2026-10-22T13:00:00Z',
    updated_at: '2026-10-22T13:00:00Z', version: 1, can_edit: true, ...fields,
  }
}

describe('summaryText', () => {
  it('says when nothing is recorded yet', () => {
    expect(summaryText(board())).toBe('Nothing recorded yet')
  })

  it('counts each kind and says how many tasks are incomplete', () => {
    expect(summaryText(board({ note: 2, task: 3, incomplete_tasks: 1, recommendation: 1, config: 1 })))
      .toBe('2 notes · 3 tasks, 1 incomplete · 1 recommendation · 1 configuration')
    expect(summaryText(board({ task: 1 }))).toBe('1 task')
  })
})

describe('the kinds', () => {
  it('share tasks and recommendations by default, and only Config takes any file', () => {
    expect(Object.fromEntries(Object.entries(KIND).map(([k, v]) => [k, [v.sharedByDefault, v.anyFile]]))).toEqual({
      note: [false, false], task: [true, false], recommendation: [true, false], config: [false, true],
    })
  })
})

describe('the board', () => {
  const list = [
    element({ id: 'a', kind: 'task', created_at: '2026-10-22T13:00:00Z' }),
    element({ id: 'b', kind: 'note', created_at: '2026-10-22T14:00:00Z' }),
    element({ id: 'c', kind: 'task', created_at: '2026-10-22T15:00:00Z' }),
  ]

  it('counts each kind', () => {
    expect(counts(list)).toEqual({ all: 3, note: 1, task: 2, recommendation: 0, config: 0 })
  })

  it('shows the newest first and a filter keeps one kind', () => {
    expect(shown(list, 'all').map(e => e.id)).toEqual(['c', 'b', 'a'])
    expect(shown(list, 'task').map(e => e.id)).toEqual(['c', 'a'])
    expect(shown(list, 'config')).toEqual([])
  })
})

describe('a sticky note', () => {
  it('names its files', () => {
    expect(filesText(element())).toBe('No files')
    expect(filesText(element({ media: { main: [media('p1'), media('p2')] } }))).toBe('2 photos')
    expect(filesText(element({ media: { main: [media('p1'), media('v1', 'video')] } }))).toBe('2 files')
    expect(filesText(element({ kind: 'config', media: { before: [media('f1', 'config')], after: [media('f2', 'config')] } }))).toBe('1 before · 1 after')
  })

  it('shows the newest photo or video, never a logger file', () => {
    const el = element({ kind: 'config', media: { before: [media('old', 'image', '2026-10-22T13:00:00Z')], after: [media('f', 'config', '2026-10-22T16:00:00Z'), media('new', 'video', '2026-10-22T15:00:00Z')] } })
    expect(cover(el)?.media_id).toBe('new')
    expect(cover(element())).toBeNull()
  })

  it('counts a task’s ticked items', () => {
    expect(progress([{ done: true }, { done: false }, { done: true }])).toEqual({ done: 2, total: 3, percent: 67 })
    expect(progress([])).toEqual({ done: 0, total: 0, percent: 0 })
  })

  it('writes the author’s initials', () => {
    expect(initials('Andrea Clarke')).toBe('AC')
    expect(initials('Devon')).toBe('D')
    expect(initials('  ')).toBe('?')
  })
})

describe('saving', () => {
  it('sends the whole content with the version the sheet started from', () => {
    const saved = element({ kind: 'task', items: [{ id: 'i1', text: 'Clean', done: true, done_by: 'u1', done_at: '2026-10-22T13:10:00Z' }], version: 3 })
    const draft = draftOf(saved)
    expect(changed(draft, saved)).toBe(false)
    draft.title = '  Clean the funnel  '
    draft.description = ' '.repeat(3)
    expect(changed(draft, saved)).toBe(true)
    expect(putBody(draft, saved.version)).toEqual({
      title: 'Clean the funnel', description: null, items: [{ id: 'i1', text: 'Clean', done: true }],
      priority: null, shared: false, base_version: 3, device_id: null,
    })
  })

  it('makes a new element with its device-made id and no version', () => {
    const body = createBody('n1', 'recommendation', { title: 'Guy wires', description: '', items: [], priority: 'high', shared: true })
    expect(body).toEqual({ id: 'n1', kind: 'recommendation', title: 'Guy wires', description: null, items: [], priority: 'high', shared: true, device_id: null })
    expect('base_version' in body).toBe(false)
  })

  it('treats trailing spaces as no change', () => {
    const saved = element({ description: 'Seal cracked' })
    const draft = { ...draftOf(saved), description: 'Seal cracked  ' }
    expect(changed(draft, saved)).toBe(false)
  })

  it('needs a title of up to 80 characters', () => {
    expect(titleProblem('  ')).toBe('Give it a title.')
    expect(titleProblem('x'.repeat(81))).toContain('80')
    expect(titleProblem('Mast')).toBeNull()
  })

  it('moves an item up or down, and leaves the ends where they are', () => {
    expect(moved(['a', 'b', 'c'], 1, -1)).toEqual(['b', 'a', 'c'])
    expect(moved(['a', 'b', 'c'], 1, 1)).toEqual(['a', 'c', 'b'])
    expect(moved(['a', 'b', 'c'], 0, -1)).toEqual(['a', 'b', 'c'])
    expect(moved(['a', 'b', 'c'], 2, 1)).toEqual(['a', 'b', 'c'])
  })
})

describe('refusals', () => {
  it('has words for the board’s refusals and finds the saved copy in a conflict', () => {
    const current = element({ title: 'Saved elsewhere', version: 4 })
    const conflict = new ApiError(409, { status: 409, code: 'element_changed', detail: 'x', current })
    expect(boardFailure(conflict, 'fallback')).toContain('another device')
    expect(currentOf(conflict)?.version).toBe(4)
    expect(currentOf(new ApiError(409, { status: 409, code: 'locked', detail: 'x' }))).toBeNull()
    expect(boardFailure(new ApiError(403, { status: 403, code: 'not_editor', detail: 'x' }), 'f')).toContain('station’s owner')
  })
})
