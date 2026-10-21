import type { VisitOut } from '@/api/models'
import { ApiError, NetworkError } from '@/api/problem'

/*
  What every visit action says when the server refuses it, in the words the page shows. The
  server decides (rules 2 to 5); this only turns its answer into a sentence. No Vue here.
*/

export interface Failure {
  message: string
  /** The visit changed under the person: show the current one. */
  reload: boolean
  /** The field a message belongs under, when the server named one. */
  field?: string
}

const CONFLICTS: Record<string, string> = {
  visit_cancelled: 'This visit was cancelled. It has been reloaded.',
  already_ended: 'This visit has already ended. It has been reloaded.',
  visit_started: 'This visit has started, so only the station owners can change.',
  not_owner: 'Only the owner of that station can do this.',
  locked: 'Someone else is working on this station.',
  bad_transition: 'Someone else just changed this visit. It has been reloaded.',
  version_conflict: 'Someone else just changed this visit. It has been reloaded.',
  visit_changed: 'Someone else just changed this visit. It has been reloaded.',
  station_in_other_visit: 'One of those stations is already in another planned or started visit of this request.',
  request_not_schedulable: 'This request can’t have a visit right now.',
}

const RELOAD = new Set(['visit_cancelled', 'already_ended', 'bad_transition', 'version_conflict', 'visit_changed', 'not_owner', 'locked'])

export function failureOf (error: unknown, fallback: string): Failure {
  if (error instanceof NetworkError) {
    return { message: 'This needs a connection. Try again when you have signal.', reload: false }
  }
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return { message: 'We can’t find this visit. It may have been removed.', reload: true }
    }
    const known = CONFLICTS[error.code]
    if (known) {
      return { message: known, reload: RELOAD.has(error.code) }
    }
    if (error.status < 500) {
      return { message: error.detail, reload: error.status === 409, field: error.field ?? undefined }
    }
  }
  return { message: fallback, reload: false }
}

/** A visit as the list shows it: its card is its page. */
export function replaceVisit (list: readonly VisitOut[], visit: VisitOut): VisitOut[] {
  return list.some(v => v.id === visit.id) ? list.map(v => v.id === visit.id ? visit : v) : [visit, ...list]
}
