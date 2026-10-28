import type { RequestDetail } from '@/api/models'
import { ApiError, NetworkError } from '@/api/problem'
import { formatDate } from '@/app/format'

/*
  What the client sees of a review (PRD REQ-12 to REQ-14; AFD J8; decisions W18-2, W18-6). No Vue
  here, so Vitest covers it. The server decides everything; these only choose the words and say
  which of the states of a request's review the page is looking at.
*/

export const REASON_MIN = 5
export const REASON_MAX = 1000

export type ReviewState
  /** In Client Review: the client may answer. */
  = | { kind: 'open', closesOn: string | null, waited: number }
  /** Closed on a client's signature. */
    | { kind: 'accepted', by: string | null, at: string }
  /** Nobody answered in time. */
    | { kind: 'auto_closed', at: string }
  /** The client sent it back and the technicians have it again. */
    | { kind: 'returned', at: string }
  /** An admin reopened a report: the review begins again when the corrected report is final. */
    | { kind: 'corrected' }
  /** Not (yet) reviewable. */
    | { kind: 'none' }

const WORKING = new Set(['assigned', 'scheduled', 'in_progress', 'reopened'])
const DAY_MS = 86_400_000

/** Whole days since `since`, never negative. */
export function daysSince (since: string | null, now: Date = new Date()): number {
  if (!since) {
    return 0
  }
  return Math.max(0, Math.floor((now.getTime() - new Date(since).getTime()) / DAY_MS))
}

export function reviewState (detail: Pick<RequestDetail, 'status' | 'verification' | 'milestones' | 'review_started_at' | 'auto_close_at'>, now: Date = new Date()): ReviewState {
  const answer = detail.verification
  switch (detail.status) {
    case 'client_review': {
      return { kind: 'open', closesOn: detail.auto_close_at, waited: daysSince(detail.review_started_at, now) }
    }
    case 'closed': {
      if (answer?.outcome === 'auto_closed') {
        return { kind: 'auto_closed', at: answer.at }
      }
      if (answer?.outcome === 'accepted') {
        return { kind: 'accepted', by: answer.typed_name ?? answer.by?.name ?? null, at: answer.at }
      }
      return { kind: 'none' }
    }
    default: {
      if (!WORKING.has(detail.status)) {
        return { kind: 'none' }
      }
      if (answer?.outcome === 'rejected') {
        return { kind: 'returned', at: answer.at }
      }
      // There was a review once and it is not on now: a report was reopened
      return detail.milestones.review_started_at ? { kind: 'corrected' } : { kind: 'none' }
    }
  }
}

export interface Notice {
  tone: 'info' | 'warning' | 'error' | 'success'
  title: string
  text: string
  /** The page should read the request again (what it showed is out of date). */
  reload: boolean
}

/** The banner a review page shows instead of its two buttons. Null while the client may answer. */
export function noticeFor (state: ReviewState): Notice | null {
  switch (state.kind) {
    case 'open': {
      return null
    }
    case 'accepted': {
      return { tone: 'success', title: 'Work accepted.', text: `${state.by ? `${state.by} signed it off` : 'It was signed off'} on ${formatDate(state.at)}. The request is closed.`, reload: false }
    }
    case 'auto_closed': {
      return { tone: 'info', title: `Closed automatically on ${formatDate(state.at)}.`, text: 'Nobody answered the review in time. The close-out report says so. You can still add a client report.', reload: false }
    }
    case 'returned': {
      return { tone: 'info', title: 'You sent the work back.', text: `The technicians have it again since ${formatDate(state.at)}. You will be asked to review it when they finish.`, reload: false }
    }
    case 'corrected': {
      return { tone: 'info', title: 'A corrected report is on its way.', text: 'You will be asked to review again when it is final. The days start again then.', reload: false }
    }
    default: {
      return { tone: 'info', title: 'There is nothing to review yet.', text: 'You will be told when the work is ready for your review.', reload: false }
    }
  }
}

/** "Waiting 3 days", "Waiting less than a day". */
export function waitingText (days: number): string {
  if (days < 1) {
    return 'Waiting less than a day'
  }
  return `Waiting ${days} ${days === 1 ? 'day' : 'days'}`
}

/** What a failed answer says, and whether the page must look again (W18-2, W18-6). */
export function answerFailure (error: unknown): Notice {
  if (error instanceof NetworkError) {
    return { tone: 'warning', title: 'This needs a connection.', text: 'Reviewing and signing are done online. Reconnect, then try again.', reload: false }
  }
  if (error instanceof ApiError) {
    if (error.code === 'review_changed') {
      return { tone: 'warning', title: 'The reports changed while you were reviewing.', text: 'A corrected report is final. Please read them again before you answer.', reload: true }
    }
    if (error.code === 'bad_transition') {
      return { tone: 'info', title: 'This request is no longer in Client Review.', text: 'Someone at your organization may have answered already.', reload: true }
    }
    if (error.status === 422 && error.detail) {
      return { tone: 'error', title: 'Your answer was not accepted.', text: error.detail, reload: false }
    }
    if (error.status === 404) {
      return { tone: 'info', title: 'This request could not be found.', text: 'It may have been removed, or the link is not complete.', reload: false }
    }
  }
  return { tone: 'error', title: 'Something went wrong.', text: 'Your answer was not sent. Try again.', reload: false }
}

/** Why the reason can't be sent yet, in words; null when it can. */
export function reasonProblem (text: string): string | null {
  const length = text.trim().length
  if (length < REASON_MIN) {
    return `Tell them why, in at least ${REASON_MIN} characters.`
  }
  if (length > REASON_MAX) {
    return `Keep it under ${REASON_MAX.toLocaleString('en-GB')} characters.`
  }
  return null
}

/** "74 of 1,000". */
export function reasonCount (text: string): string {
  return `${text.trim().length.toLocaleString('en-GB')} of ${REASON_MAX.toLocaleString('en-GB')}`
}
