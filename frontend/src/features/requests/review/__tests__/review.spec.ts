import type { RequestDetail } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import { answerFailure, daysSince, noticeFor, reasonCount, reasonProblem, reviewState, waitingText } from '../review'

type Detail = Pick<RequestDetail, 'status' | 'verification' | 'milestones' | 'review_started_at' | 'auto_close_at'>

function detail (over: Partial<Detail> = {}): Detail {
  return { status: 'client_review', verification: null, milestones: {}, review_started_at: '2026-10-01T12:00:00Z', auto_close_at: '2026-10-31T12:00:00Z', ...over }
}

const NOW = new Date('2026-10-04T13:00:00Z')

describe('which state of the review the page is in', () => {
  it('is open while the request is in Client Review, with the days waited', () => {
    expect(reviewState(detail(), NOW)).toEqual({ kind: 'open', closesOn: '2026-10-31T12:00:00Z', waited: 3 })
  })

  it('is accepted, by the name that was typed', () => {
    const verification = { outcome: 'accepted', at: '2026-10-05T16:00:00Z', typed_name: 'Una Client', by: { id: 'u', name: 'Una C.' }, comment: null } as Detail['verification']
    expect(reviewState(detail({ status: 'closed', verification }), NOW)).toEqual({ kind: 'accepted', by: 'Una Client', at: '2026-10-05T16:00:00Z' })
  })

  it('is auto closed when the clock closed it', () => {
    const verification = { outcome: 'auto_closed', at: '2026-10-31T12:00:00Z', typed_name: null, by: null, comment: null } as Detail['verification']
    expect(reviewState(detail({ status: 'closed', verification }), NOW).kind).toBe('auto_closed')
  })

  it('is returned after a rejection while the technicians have it again', () => {
    const verification = { outcome: 'rejected', at: '2026-10-05T16:00:00Z', typed_name: null, by: null, comment: 'Wrong mast' } as Detail['verification']
    expect(reviewState(detail({ status: 'assigned', verification }), NOW)).toEqual({ kind: 'returned', at: '2026-10-05T16:00:00Z' })
  })

  it('is corrected when a review began once and a report was reopened', () => {
    const open = detail({ status: 'in_progress', review_started_at: null, auto_close_at: null, milestones: { review_started_at: '2026-10-01T12:00:00Z' } })
    expect(reviewState(open, NOW).kind).toBe('corrected')
  })

  it('is none for a request that never reached a review', () => {
    for (const status of ['submitted', 'approved', 'denied', 'cancelled', 'assigned', 'in_progress'] as const) {
      expect(reviewState(detail({ status, review_started_at: null, auto_close_at: null }), NOW).kind).toBe('none')
    }
  })
})

describe('what the banner says', () => {
  it('says nothing while the client may answer', () => {
    expect(noticeFor({ kind: 'open', closesOn: null, waited: 0 })).toBeNull()
  })

  it('says why the answer buttons are gone, in each state', () => {
    expect(noticeFor({ kind: 'accepted', by: 'Una Client', at: '2026-10-05T16:00:00Z' })?.title).toBe('Work accepted.')
    expect(noticeFor({ kind: 'auto_closed', at: '2026-10-31T12:00:00Z' })?.title).toContain('Closed automatically on 31 Oct 2026')
    expect(noticeFor({ kind: 'returned', at: '2026-10-05T16:00:00Z' })?.title).toBe('You sent the work back.')
    expect(noticeFor({ kind: 'corrected' })?.title).toBe('A corrected report is on its way.')
    expect(noticeFor({ kind: 'none' })?.title).toBe('There is nothing to review yet.')
  })
})

describe('the days waited', () => {
  it('counts whole days and never goes negative', () => {
    expect(daysSince('2026-10-04T12:00:00Z', NOW)).toBe(0)
    expect(daysSince('2026-10-01T13:00:00Z', NOW)).toBe(3)
    expect(daysSince('2026-10-09T13:00:00Z', NOW)).toBe(0)
    expect(daysSince(null, NOW)).toBe(0)
  })

  it('reads as words', () => {
    expect(waitingText(0)).toBe('Waiting less than a day')
    expect(waitingText(1)).toBe('Waiting 1 day')
    expect(waitingText(3)).toBe('Waiting 3 days')
  })
})

describe('what a failed answer says', () => {
  const problem = (status: number, code: string, detailText = 'x') => new ApiError(status, { code, detail: detailText })

  it('asks to read the reports again when they changed', () => {
    const notice = answerFailure(problem(409, 'review_changed'))
    expect(notice.title).toBe('The reports changed while you were reviewing.')
    expect(notice.reload).toBe(true)
  })

  it('says the review moved on when the request is not in Client Review any more', () => {
    const notice = answerFailure(problem(409, 'bad_transition'))
    expect(notice.title).toBe('This request is no longer in Client Review.')
    expect(notice.reload).toBe(true)
  })

  it('needs a connection', () => {
    const notice = answerFailure(new NetworkError('offline'))
    expect(notice.tone).toBe('warning')
    expect(notice.reload).toBe(false)
  })

  it('shows the server’s words for a refused signature, and a plain line for anything else', () => {
    expect(answerFailure(problem(422, 'validation_failed', 'The drawing is too large')).text).toBe('The drawing is too large')
    expect(answerFailure(problem(404, 'not_found')).title).toBe('This request could not be found.')
    expect(answerFailure(new Error('boom')).text).toBe('Your answer was not sent. Try again.')
  })
})

describe('the reason for sending the work back', () => {
  it('needs 5 to 1,000 characters once trimmed', () => {
    expect(reasonProblem('  no ')).toContain('at least 5')
    expect(reasonProblem('Wrong mast')).toBeNull()
    expect(reasonProblem('x'.repeat(1000))).toBeNull()
    expect(reasonProblem('x'.repeat(1001))).toContain('under 1,000')
  })

  it('counts what will be sent', () => {
    expect(reasonCount('  Wrong mast ')).toBe('10 of 1,000')
  })
})
