import type { ClientReportOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import { emptyModel, failureWords, imageProblem, isEmptyPatch, isoDay, modelOf, patchOf, saveWords, submitProblem } from '../clientReport'

function draft (over: Partial<ClientReportOut> = {}): ClientReportOut {
  return {
    id: 'c1', request_id: 'q1', kind: 'form', status: 'draft', title: 'Check', report_date: '2026-09-30', station_ids: ['s1', 's2'],
    form: { summary: 'Steady', observations: [{ station_id: 's1', text: 'Worn cups' }], data_quality_notes: 'Gap', images: [] }, ...over,
  } as ClientReportOut
}

describe('the model of a draft', () => {
  it('starts with every station of the request and today', () => {
    const model = emptyModel(['s1', 's2'], new Date(2026, 8, 30))
    expect(model).toEqual({ title: '', reportDate: '2026-09-30', stationIds: ['s1', 's2'], summary: '', observations: {}, notes: '' })
    expect(isoDay(new Date(2026, 0, 5))).toBe('2026-01-05')
  })

  it('is read back from what the server holds', () => {
    const model = modelOf(draft())
    expect(model.observations).toEqual({ s1: 'Worn cups' })
    expect(model.notes).toBe('Gap')
    expect(model.stationIds).toEqual(['s1', 's2'])
  })
})

describe('what a save sends', () => {
  const before = modelOf(draft())

  it('sends nothing when nothing changed', () => {
    expect(isEmptyPatch(patchOf(before, { ...before }, 'form'))).toBe(true)
  })

  it('sends only the fields that differ', () => {
    expect(patchOf(before, { ...before, title: 'Check 2' }, 'form')).toEqual({ title: 'Check 2' })
    expect(patchOf(before, { ...before, summary: 'Steady, one gap', notes: '' }, 'form')).toEqual({ summary: 'Steady, one gap', data_quality_notes: '' })
  })

  it('sends the notes of the covered stations, leaving blanks out', () => {
    const now = { ...before, observations: { s1: 'Worn cups', s2: '  ' } }
    expect(patchOf(before, now, 'form').observations).toBeUndefined()
    const changed = { ...before, observations: { s1: 'Worn cups', s2: 'Dusty' } }
    expect(patchOf(before, changed, 'form').observations).toEqual([
      { station_id: 's1', text: 'Worn cups' }, { station_id: 's2', text: 'Dusty' },
    ])
  })

  it('sends the notes again when the stations change, so one for a dropped station goes', () => {
    const now = { ...before, stationIds: ['s2'] }
    const patch = patchOf(before, now, 'form')
    expect(patch.station_ids).toEqual(['s2'])
    expect(patch.observations).toEqual([])
  })

  it('leaves the form out of a PDF report', () => {
    expect(patchOf(before, { ...before, summary: 'x', title: 'T' }, 'pdf')).toEqual({ title: 'T' })
  })
})

describe('when a report may be sent', () => {
  const model = modelOf(draft())
  const ready = { fileReady: true, filesBusy: false }

  it('needs a title, a station and the kind’s own part', () => {
    expect(submitProblem('form', { ...model, title: ' ' }, ready)?.field).toBe('title')
    expect(submitProblem('form', { ...model, stationIds: [] }, ready)?.field).toBe('stations')
    expect(submitProblem('form', { ...model, summary: '' }, ready)?.field).toBe('summary')
    expect(submitProblem('form', model, ready)).toBeNull()
  })

  it('waits for a PDF, and for files still on their way', () => {
    expect(submitProblem('pdf', model, { fileReady: false, filesBusy: false })?.text).toBe('Upload the PDF first.')
    expect(submitProblem('pdf', model, { fileReady: false, filesBusy: true })?.text).toContain('finish uploading')
    expect(submitProblem('pdf', model, ready)).toBeNull()
    expect(submitProblem('form', model, { fileReady: false, filesBusy: true })?.field).toBe('file')
  })
})

describe('which pictures can be added', () => {
  it('takes JPEG and PNG', () => {
    expect(imageProblem({ name: 'a.jpg', size: 10, type: 'image/jpeg' })).toBeNull()
    expect(imageProblem({ name: 'a.PNG', size: 10, type: '' })).toBeNull()
    expect(imageProblem({ name: 'a.gif', size: 10, type: 'image/gif' })).toContain('JPEG and PNG')
    expect(imageProblem({ name: 'a.jpg', size: 0, type: 'image/jpeg' })).toBe('This file is empty.')
  })
})

describe('the words next to the title', () => {
  it('says where a save stands', () => {
    expect(saveWords('idle', null)).toBe('')
    expect(saveWords('saving', null)).toBe('Saving…')
    expect(saveWords('retrying', null)).toBe('Not saved yet. Retrying…')
    expect(saveWords('saved', new Date(2026, 9, 5, 9, 3))).toBe('Saved at 09:03')
  })
})

describe('what a failure says', () => {
  const problem = (status: number, code: string, detail = 'x') => new ApiError(status, { code, detail })

  it('keeps the typed text for a missing connection', () => {
    expect(failureWords(new NetworkError('x')).text).toContain('still here')
  })

  it('reads the report again after a version clash', () => {
    expect(failureWords(problem(409, 'version_conflict')).stale).toBe(true)
  })

  it('stops for a report that was already sent, or a request that cannot take one', () => {
    expect(failureWords(problem(409, 'not_a_draft')).gone).toBe(true)
    expect(failureWords(problem(409, 'request_not_reportable')).gone).toBe(true)
    expect(failureWords(problem(404, 'not_found')).gone).toBe(true)
  })

  it('shows the server’s words for a refused field, and a plain line otherwise', () => {
    expect(failureWords(problem(422, 'required', 'Write a summary')).text).toBe('Write a summary')
    expect(failureWords(new Error('boom')).text).toBe('Something went wrong. Try again.')
  })
})
