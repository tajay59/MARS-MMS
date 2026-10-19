import type { DocumentOut, DocumentPatch } from '@/api/models'
import type { ApiError } from '@/api/problem'

/*
  "Edit details" on a document (PRD DOC-4; approved mock-up "W6 forms"). No Vue here, so Vitest
  covers it directly. The file itself never changes (upload a new version instead), and who may
  see it stays in the row's menu, so a title fix can't change that.
*/

export const TITLE_MAX = 120
export const VERSION_LABEL_MAX = 60
export const DESCRIPTION_MAX = 2000

export interface DetailValues {
  title: string
  docType: string
  versionLabel: string
  language: string | null
  description: string
}

export type DetailField = keyof DetailValues
export type DetailErrors = Partial<Record<DetailField, string>>

export type DetailProblem
  = | { kind: 'stale' }
    | { kind: 'fields', errors: DetailErrors, message: string | null }
    | { kind: 'other', message: string }

type Details = Pick<DocumentOut, 'title' | 'doc_type' | 'version_label' | 'language' | 'description'>

export function detailValues (doc: Details): DetailValues {
  return {
    title: doc.title,
    docType: doc.doc_type,
    versionLabel: doc.version_label ?? '',
    language: doc.language ?? null,
    description: doc.description ?? '',
  }
}

export function validateDetails (v: DetailValues): DetailErrors {
  const e: DetailErrors = {}
  if (!v.title.trim()) {
    e.title = 'Enter a title'
  } else if (v.title.trim().length > TITLE_MAX) {
    e.title = `Use at most ${TITLE_MAX} characters`
  }
  if (!v.docType) {
    e.docType = 'Choose a type'
  }
  if (v.versionLabel.trim().length > VERSION_LABEL_MAX) {
    e.versionLabel = `Use at most ${VERSION_LABEL_MAX} characters`
  }
  if (v.description.trim().length > DESCRIPTION_MAX) {
    e.description = `Use at most ${DESCRIPTION_MAX} characters`
  }
  return e
}

/**
 * Whether two copies of a document have the same details. The file's checks finish in the
 * background and move its version, so a newer copy with the same details is not someone else's edit.
 */
export function sameDetails (a: Details, b: Details): boolean {
  return JSON.stringify(detailValues(a)) === JSON.stringify(detailValues(b))
}

function blank (value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** Only what changed, with the version the person was looking at; null when nothing did. */
export function detailsPatchBody (v: DetailValues, was: DocumentOut): DocumentPatch | null {
  const body: DocumentPatch = { version: was.version }
  let changed = false
  if (v.title.trim() !== was.title) {
    body.title = v.title.trim()
    changed = true
  }
  if (v.docType !== was.doc_type) {
    body.doc_type = v.docType
    changed = true
  }
  if (blank(v.versionLabel) !== (was.version_label ?? null)) {
    body.version_label = blank(v.versionLabel)
    changed = true
  }
  if (v.language !== (was.language ?? null)) {
    body.language = v.language
    changed = true
  }
  if (blank(v.description) !== (was.description ?? null)) {
    body.description = blank(v.description)
    changed = true
  }
  return changed ? body : null
}

const API_FIELDS: Record<string, DetailField> = {
  title: 'title',
  doc_type: 'docType',
  version_label: 'versionLabel',
  language: 'language',
  description: 'description',
}

export function detailsProblem (error: ApiError): DetailProblem {
  if (error.status === 409) {
    return { kind: 'stale' }
  }
  const errors: DetailErrors = {}
  for (const [field, message] of Object.entries(error.fieldErrors())) {
    const key = API_FIELDS[field]
    if (key) {
      errors[key] = message
    }
  }
  if (Object.keys(errors).length > 0) {
    return { kind: 'fields', errors, message: null }
  }
  return error.status === 422
    ? { kind: 'fields', errors: {}, message: error.detail }
    : { kind: 'other', message: 'We couldn’t save the details. Try again in a moment.' }
}
