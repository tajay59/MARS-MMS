import type { BoardSummary } from '@/api/models'

/*
  A station's board on a visit (PRD VIS-5, VIS-7; W11-16 to W11-35): the rules its screens share.
  No Vue here.
*/

function count (n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

/** "2 notes · 3 tasks, 1 incomplete · 1 recommendation", or that nothing is recorded yet. */
export function summaryText (board: BoardSummary): string {
  const parts: string[] = []
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
