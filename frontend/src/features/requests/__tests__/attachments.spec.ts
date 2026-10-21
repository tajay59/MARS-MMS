import { describe, expect, it } from 'vitest'
import { allReady, chipText, editLeft, isReady, MAX_FILE_BYTES, pdfProblem } from '../attachments'

describe('which files can be attached', () => {
  it('takes PDFs of a sensible size', () => {
    expect(pdfProblem({ name: 'storm-report.pdf', size: 1_200_000 })).toBeNull()
    expect(pdfProblem({ name: 'REPORT.PDF', size: 10 })).toBeNull()
  })

  it('says why not, in words for the person', () => {
    expect(pdfProblem({ name: 'manual.docx', size: 10 })).toBe('Only PDF files can be attached.')
    expect(pdfProblem({ name: 'photo.jpg', size: 10 })).toBe('Only PDF files can be attached.')
    expect(pdfProblem({ name: 'empty.pdf', size: 0 })).toBe('This file is empty.')
    expect(pdfProblem({ name: 'big.pdf', size: MAX_FILE_BYTES + 1 })).toContain('25 MB')
    expect(pdfProblem({ name: 'edge.pdf', size: MAX_FILE_BYTES })).toBeNull()
  })
})

describe('when Post and Submit may go', () => {
  const upload = (state: string) => ({ state })
  it('waits for every file to be checked, and for a bad one to be removed', () => {
    expect(allReady([])).toBe(true)
    expect(allReady([{ problem: null, upload: upload('ready') }])).toBe(true)
    expect(allReady([{ problem: null, upload: upload('ready') }, { problem: null, upload: upload('running') }])).toBe(false)
    expect(allReady([{ problem: null, upload: upload('checking') }])).toBe(false)
    expect(allReady([{ problem: null, upload: upload('failed') }])).toBe(false)
    expect(isReady({ problem: 'Only PDF files can be attached.', upload: null })).toBe(false)
  })
})

describe('what a file chip says', () => {
  const base = { problem: null, size: 1_200_000 }
  const up = (patch: object) => ({ state: 'running', phase: 'sending', sent: 0, total: 100, waiting: null, error: null, ...patch })

  it('tracks the upload from hashing to ready', () => {
    expect(chipText({ ...base, upload: up({ phase: 'hashing' }) })).toContain('Preparing…')
    expect(chipText({ ...base, upload: up({ sent: 62 }) })).toContain('Uploading 62%')
    expect(chipText({ ...base, upload: up({ sent: 100 }) })).toContain('Uploading 99%') // never 100 until it is
    expect(chipText({ ...base, upload: up({ waiting: 'network' }) })).toContain('Waiting for a connection…')
    expect(chipText({ ...base, upload: up({ state: 'arrived' }) })).toContain('Checking…')
    expect(chipText({ ...base, upload: up({ state: 'ready' }) })).toContain('Ready')
    expect(chipText({ ...base, upload: up({ state: 'failed', error: 'The connection kept failing.' }) })).toBe('The connection kept failing.')
  })

  it('shows a problem instead', () => {
    expect(chipText({ problem: 'This file is empty.', size: 0, upload: null })).toBe('This file is empty.')
  })
})

describe('how long a comment can be changed', () => {
  const now = new Date('2026-10-20T12:00:00Z')
  it('counts the minutes left and stops at zero', () => {
    expect(editLeft('2026-10-20T12:12:00Z', now)).toBe('12 minutes left')
    expect(editLeft('2026-10-20T12:00:30Z', now)).toBe('1 minute left')
    expect(editLeft('2026-10-20T11:59:59Z', now)).toBeNull()
    expect(editLeft(null, now)).toBeNull()
  })
})
