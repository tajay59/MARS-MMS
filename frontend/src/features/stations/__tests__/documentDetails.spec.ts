import type { DocumentOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/problem'
import { detailsPatchBody, detailsProblem, detailValues, sameDetails, validateDetails } from '../documentDetails'

function doc (patch: Partial<DocumentOut> = {}): DocumentOut {
  return {
    id: 'd1',
    scope: 'station',
    scope_id: 's1',
    doc_type: 'site_drawing',
    title: 'Site drawing',
    version_label: 'v2',
    language: 'en',
    description: 'After the rebuild.',
    client_visible: false,
    media_id: 'f1',
    filename: 'drawing.pdf',
    size_bytes: 1200,
    supersedes_id: null,
    is_current: true,
    status: 'available',
    scan_status: 'clean',
    uploaded_by: 'Tech One',
    created_at: '2026-01-01T00:00:00Z',
    version: 4,
    ...patch,
  } as DocumentOut
}

describe('document details', () => {
  it('needs a title and a type', () => {
    expect(validateDetails({ ...detailValues(doc()), title: ' ' }).title).toBe('Enter a title')
    expect(validateDetails({ ...detailValues(doc()), docType: '' }).docType).toBe('Choose a type')
    expect(validateDetails(detailValues(doc()))).toEqual({})
  })

  it('holds the same limits as the server', () => {
    const v = detailValues(doc())
    expect(validateDetails({ ...v, title: 'x'.repeat(121) }).title).toBe('Use at most 120 characters')
    expect(validateDetails({ ...v, versionLabel: 'x'.repeat(61) }).versionLabel).toBe('Use at most 60 characters')
    expect(validateDetails({ ...v, description: 'x'.repeat(2001) }).description).toBe('Use at most 2000 characters')
  })

  it('sends nothing when nothing changed', () => {
    expect(detailsPatchBody(detailValues(doc()), doc())).toBeNull()
    expect(detailsPatchBody({ ...detailValues(doc()), title: '  Site drawing ' }, doc())).toBeNull()
  })

  it('sends only what changed, with the version', () => {
    const v = detailValues(doc())
    expect(detailsPatchBody({ ...v, title: 'Kingston Harbour site drawing' }, doc())).toEqual({
      version: 4,
      title: 'Kingston Harbour site drawing',
    })
    expect(detailsPatchBody({ ...v, docType: 'installation', language: 'es' }, doc())).toEqual({
      version: 4,
      doc_type: 'installation',
      language: 'es',
    })
  })

  it('clears an optional field by sending null', () => {
    const v = detailValues(doc())
    expect(detailsPatchBody({ ...v, versionLabel: '', description: ' ', language: null }, doc())).toEqual({
      version: 4,
      version_label: null,
      description: null,
      language: null,
    })
    const bare = doc({ version_label: null, language: null, description: null })
    expect(detailValues(bare)).toMatchObject({ versionLabel: '', language: null, description: '' })
    expect(detailsPatchBody(detailValues(bare), bare)).toBeNull()
  })

  it('says what a failed save means', () => {
    expect(detailsProblem(new ApiError(409, { code: 'conflict', detail: 'The document changed' }))).toEqual({ kind: 'stale' })
    const invalid = new ApiError(422, { code: 'validation_error', errors: [{ loc: ['body', 'title'], msg: 'Too long' }] })
    expect(detailsProblem(invalid)).toEqual({ kind: 'fields', errors: { title: 'Too long' }, message: null })
    expect(detailsProblem(new ApiError(422, { code: 'invalid_type', detail: 'Not a station document type' }))).toEqual({
      kind: 'fields',
      errors: {},
      message: 'Not a station document type',
    })
    expect(detailsProblem(new ApiError(500, null)).kind).toBe('other')
  })
})

describe('same details', () => {
  it('ignores what the file’s checks change and sees what a person changed', () => {
    expect(sameDetails(doc(), doc({ version: 5, status: 'available', scan_status: 'clean' }))).toBe(true)
    expect(sameDetails(doc(), doc({ title: 'Other' }))).toBe(false)
    expect(sameDetails(doc({ description: null }), doc({ description: '' }))).toBe(true)
  })
})
