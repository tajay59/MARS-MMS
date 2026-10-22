import type { BoardSummary } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { summaryText } from '../board'

function board (fields: Partial<BoardSummary> = {}): BoardSummary {
  return { note: 0, task: 0, recommendation: 0, config: 0, incomplete_tasks: 0, cover: null, ...fields }
}

describe('summaryText', () => {
  it('says when nothing is recorded yet', () => {
    expect(summaryText(board())).toBe('Nothing recorded yet')
  })

  it('counts each kind and says how many tasks are incomplete', () => {
    expect(summaryText(board({ note: 2, task: 3, incomplete_tasks: 1, recommendation: 1, config: 1 })))
      .toBe('2 notes · 3 tasks, 1 incomplete · 1 recommendation · 1 configuration')
    expect(summaryText(board({ task: 1 }))).toBe('1 task')
    expect(summaryText(board({ config: 2 }))).toBe('2 configurations')
  })
})
