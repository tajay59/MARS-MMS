import type { ClientReportOut, ReportSummary } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import { canAddClientReport, clientReportLook, clientReportSub, closeoutBeingMade, closeoutsOf, isSettling, kindLabel, linkProblem, visitReportsOf } from '../reports'

function report (over: Partial<ReportSummary> = {}): ReportSummary {
  return {
    id: 'r1', type: 'closeout', subject_ref: 'request:q1', visit_id: null, request_id: 'q1', number: 'CO-2026-0042', version: 1,
    status: 'final', pdf: { state: 'ready', current: true }, awaiting_media: 0, created_at: '2026-10-05T11:00:00Z', updated_at: '2026-10-05T11:00:00Z', ...over,
  } as ReportSummary
}

function client (over: Partial<ClientReportOut> = {}): ClientReportOut {
  return { id: 'c1', status: 'submitted', kind: 'form', render: 'ready', report_date: '2026-09-30', submitted_by: { id: 'u', name: 'Una Client' }, can_edit: false, ...over } as ClientReportOut
}

describe('who can add a client report', () => {
  it('is any request that reached the work, and a closed one', () => {
    for (const status of ['approved', 'assigned', 'in_progress', 'client_review', 'reopened', 'closed']) {
      expect(canAddClientReport(status)).toBe(true)
    }
    for (const status of ['submitted', 'denied', 'cancelled']) {
      expect(canAddClientReport(status)).toBe(false)
    }
  })
})

describe('the close-out reports', () => {
  it('leads with the newest final version and lists the replaced ones after it', () => {
    const found = closeoutsOf([
      report({ id: 'a', version: 1, status: 'superseded' }),
      report({ id: 'b', version: 2, status: 'final' }),
      report({ id: 'x', type: 'visit', version: 9 }),
    ])
    expect(found.current?.id).toBe('b')
    expect(found.replaced.map(r => r.id)).toEqual(['a'])
  })

  it('has none before the first is made', () => {
    expect(closeoutsOf([])).toEqual({ current: null, replaced: [] })
  })

  it('is being made for a few minutes after the request closed, and then says nothing', () => {
    const closed = { status: 'closed', milestones: { closed_at: '2026-10-05T11:00:00Z' } } as never
    const none = { current: null, replaced: [] }
    expect(closeoutBeingMade(closed, none, new Date('2026-10-05T11:03:00Z'))).toBe(true)
    expect(closeoutBeingMade(closed, none, new Date('2026-10-05T11:20:00Z'))).toBe(false)
    expect(closeoutBeingMade(closed, { current: report(), replaced: [] }, new Date('2026-10-05T11:03:00Z'))).toBe(false)
    expect(closeoutBeingMade({ status: 'assigned', milestones: {} } as never, none)).toBe(false)
  })
})

describe('the visit reports', () => {
  it('keeps the newest version of each visit, in number order', () => {
    const list = [
      report({ id: 'v2b', type: 'visit', visit_id: 'v2', number: 'VR-2026-0042-02', version: 2 }),
      report({ id: 'v2a', type: 'visit', visit_id: 'v2', number: 'VR-2026-0042-02', version: 1 }),
      report({ id: 'v1a', type: 'visit', visit_id: 'v1', number: 'VR-2026-0042-01', version: 1 }),
    ]
    expect(visitReportsOf(list).map(r => r.id)).toEqual(['v1a', 'v2b'])
  })
})

describe('where a client report stands', () => {
  it('is a draft until it is sent, a file for a PDF, then follows the PDF for a form', () => {
    expect(clientReportLook(client({ status: 'draft', render: 'none' }))).toBe('draft')
    expect(clientReportLook(client({ kind: 'pdf', render: 'none' }))).toBe('file')
    expect(clientReportLook(client({ render: 'rendering' }))).toBe('making')
    expect(clientReportLook(client({ render: 'ready' }))).toBe('ready')
    expect(clientReportLook(client({ render: 'failed' }))).toBe('failed')
  })

  it('has its own words', () => {
    expect(kindLabel('form')).toBe('Online form')
    expect(kindLabel('pdf')).toBe('PDF')
    const date = (iso: string) => iso
    expect(clientReportSub(client(), date)).toBe('2026-09-30 · Una Client')
    expect(clientReportSub(client({ status: 'draft', submitted_by: null }), date)).toBe('2026-09-30 · not sent yet')
  })

  it('looks again while a PDF is being made', () => {
    expect(isSettling([client()], false)).toBe(false)
    expect(isSettling([client({ render: 'rendering' })], false)).toBe(true)
    expect(isSettling([], true)).toBe(true)
  })
})

describe('what a failed link says', () => {
  it('names a missing connection, a PDF still being made and a report that is gone', () => {
    expect(linkProblem(new NetworkError('x'))).toContain('connection')
    expect(linkProblem(new ApiError(409, { code: 'no_pdf', detail: 'x' }))).toContain('still being made')
    expect(linkProblem(new ApiError(404, { code: 'not_found', detail: 'x' }))).toContain('could not be found')
    expect(linkProblem(new Error('boom'))).toBe('The report could not be opened. Try again.')
  })
})
