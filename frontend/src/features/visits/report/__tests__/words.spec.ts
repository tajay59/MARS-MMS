import type { ReportSummary } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { isSettling, latest, look, statusText, versionText } from '../words'

function report (over: Partial<ReportSummary> = {}, pdf: Partial<ReportSummary['pdf']> = {}): ReportSummary {
  return {
    id: 'r1',
    type: 'visit',
    subject_ref: 'visit:v1',
    visit_id: 'v1',
    request_id: 'q1',
    number: 'VR-2026-0042-02',
    version: 1,
    status: 'draft',
    awaiting_media: 0,
    drafted_at: null,
    created_at: '2026-10-23T20:00:00Z',
    updated_at: '2026-10-23T20:00:00Z',
    pdf: { state: 'none', current: false, pages: null, rendered_at: null, error: null, ...pdf },
    ...over,
  } as ReportSummary
}

describe('look', () => {
  it('says the draft is being made, and for how many files it waits', () => {
    expect(look(report()).title).toBe('Your draft is being made')
    expect(look(report({ awaiting_media: 1 })).text).toContain('Waiting for 1 file ')
    expect(look(report({ awaiting_media: 3 })).text).toContain('Waiting for 3 files ')
    expect(look(report())).toMatchObject({ canOpen: false, canDraw: true, action: 'Preview now' })
  })

  it('says it is drawing, and keeps an older drawing open-able', () => {
    expect(look(report({}, { state: 'rendering' }))).toMatchObject({ tone: 'working', canOpen: false, canDraw: false })
    expect(look(report({}, { state: 'rendering', rendered_at: '2026-10-23T20:05:00Z' })).canOpen).toBe(true)
  })

  it('is ready when the PDF is current, with its pages', () => {
    expect(look(report({}, { state: 'ready', current: true, pages: 1 }))).toMatchObject({ tone: 'ready', canOpen: true, canDraw: false })
    expect(look(report({}, { state: 'ready', current: true, pages: 1 })).text).toContain('1 page.')
    expect(look(report({}, { state: 'ready', current: true, pages: 4 })).text).toContain('4 pages')
  })

  it('offers to draw again when the visit changed since', () => {
    expect(look(report({}, { state: 'ready', current: false, pages: 2 }))).toMatchObject({ tone: 'stale', canOpen: true, canDraw: true })
  })

  it('offers Try again when drawing failed', () => {
    expect(look(report({}, { state: 'failed' }))).toMatchObject({ tone: 'failed', canDraw: true, action: 'Try again', canOpen: false })
  })

  it('says a report is being finalized, and then that it is final and can be opened', () => {
    expect(look(report({ status: 'finalizing' }))).toMatchObject({ tone: 'working', title: 'Finalizing…', canOpen: false, canDraw: false })
    expect(look(report({ status: 'final' }))).toMatchObject({ tone: 'ready', title: 'Final report', canOpen: true, canDraw: false })
    expect(look(report({ status: 'superseded' }))).toMatchObject({ title: 'Superseded report', canOpen: true, canDraw: false })
  })
})

describe('the rest', () => {
  it('writes the version and status', () => {
    expect(versionText({ version: 2 })).toBe('v2')
    expect(statusText('draft')).toBe('Draft')
    expect(statusText('final')).toBe('Final')
    expect(statusText('finalizing')).toBe('Finalizing')
  })

  it('takes the newest version', () => {
    expect(latest([])).toBeNull()
    expect(latest([report({ id: 'a', version: 1 }), report({ id: 'b', version: 3 }), report({ id: 'c', version: 2 })])?.id).toBe('b')
  })

  it('keeps looking only while a draft is being made', () => {
    expect(isSettling(null)).toBe(false)
    expect(isSettling(report())).toBe(true)
    expect(isSettling(report({}, { state: 'rendering' }))).toBe(true)
    expect(isSettling(report({ awaiting_media: 2 }, { state: 'ready', current: true }))).toBe(true)
    expect(isSettling(report({}, { state: 'ready', current: true }))).toBe(false)
    expect(isSettling(report({ status: 'final' }))).toBe(false)
    expect(isSettling(report({ status: 'finalizing' }))).toBe(true)
  })
})
