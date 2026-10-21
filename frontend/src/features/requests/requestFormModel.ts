import type { RequestDetail, RequestIn, RequestPatch } from '@/api/models'
import type { ApiError } from '@/api/problem'

/*
  The new-request and edit-request form (PRD REQ-1, REQ-2, REQ-11). Pure functions, so Vitest
  covers the rules. The server owns them (domain/requests/rules.py): these only catch the
  common mistakes before a round trip, with the same words.
*/

export const MAX_TITLE = 200
export const MAX_DESCRIPTION = 5000
export const MAX_STATIONS = 20

export interface FormValues {
  /** An admin names the organization; a client's is their own. */
  orgId: string | null
  stationIds: string[]
  title: string
  description: string
  category: string
  priority: string
}

export type FieldKey = 'orgId' | 'stationIds' | 'title' | 'description' | 'category' | 'priority'
export type FieldErrors = Partial<Record<FieldKey, string>>

export function emptyValues (stationIds: string[] = []): FormValues {
  return { orgId: null, stationIds, title: '', description: '', category: 'fault', priority: 'normal' }
}

export function valuesOf (request: RequestDetail): FormValues {
  return {
    orgId: request.org_id,
    stationIds: request.stations.map(s => s.id),
    title: request.title,
    description: request.description,
    category: request.category,
    priority: request.priority,
  }
}

/** Mistakes a person can fix before sending; the first one in form order gets the focus. */
export function validate (values: FormValues, options: { admin: boolean, editing: boolean }): FieldErrors {
  const errors: FieldErrors = {}
  if (options.admin && !options.editing && !values.orgId) {
    errors.orgId = 'Choose the organization'
  }
  if (values.stationIds.length === 0) {
    errors.stationIds = 'Pick at least one station'
  } else if (values.stationIds.length > MAX_STATIONS) {
    errors.stationIds = `Pick up to ${MAX_STATIONS} stations`
  }
  const title = values.title.trim()
  if (!title) {
    errors.title = 'Add a title'
  } else if (title.length > MAX_TITLE) {
    errors.title = `Keep it under ${MAX_TITLE} characters`
  }
  const description = values.description.trim()
  if (!description) {
    errors.description = 'Describe the problem'
  } else if (description.length > MAX_DESCRIPTION) {
    errors.description = `Keep it under ${MAX_DESCRIPTION} characters`
  }
  return errors
}

/** The new request. `id` is made on the device, so sending it again can't make a second request. */
export function createBody (
  values: FormValues, id: string, options: { admin: boolean, mediaIds?: string[] },
): RequestIn {
  return {
    id,
    org_id: options.admin ? values.orgId : null,
    title: values.title.trim(),
    description: values.description.trim(),
    category: values.category as RequestIn['category'],
    priority: values.priority as RequestIn['priority'],
    station_ids: values.stationIds,
    media_ids: options.mediaIds ?? [],
  }
}

/** Only what changed, with the version the editor was looking at. */
export function patchBody (values: FormValues, request: RequestDetail): RequestPatch {
  const body: RequestPatch = { version: request.version }
  if (values.title.trim() !== request.title) {
    body.title = values.title.trim()
  }
  if (values.description.trim() !== request.description) {
    body.description = values.description.trim()
  }
  if (values.category !== request.category) {
    body.category = values.category as RequestPatch['category']
  }
  if (values.priority !== request.priority) {
    body.priority = values.priority as RequestPatch['priority']
  }
  const before = request.stations.map(s => s.id)
  if (values.stationIds.length !== before.length || values.stationIds.some((id, i) => id !== before[i])) {
    body.station_ids = values.stationIds
  }
  return body
}

export function isUnchanged (values: FormValues, request: RequestDetail): boolean {
  return Object.keys(patchBody(values, request)).length === 1
}

export type SaveProblem
  = | { kind: 'stale' }
    | { kind: 'fields', errors: FieldErrors, message: string | null }
    | { kind: 'other', message: string }

const API_FIELDS: Record<string, FieldKey> = {
  org_id: 'orgId', station_ids: 'stationIds', title: 'title', description: 'description',
  category: 'category', priority: 'priority',
}

/** What a failed save means for the form (the answers are in api/requests/request_routes.py). */
export function problemOf (error: ApiError, what = 'the request'): SaveProblem {
  if (error.code === 'version_conflict' || error.code === 'request_changed') {
    return { kind: 'stale' }
  }
  const named = error.field ? API_FIELDS[error.field] : undefined
  if (named) {
    return { kind: 'fields', errors: { [named]: error.detail }, message: null }
  }
  const errors: FieldErrors = {}
  for (const [field, message] of Object.entries(error.fieldErrors())) {
    const key = API_FIELDS[field]
    if (key) {
      errors[key] = message
    }
  }
  if (Object.keys(errors).length > 0) {
    return { kind: 'fields', errors, message: null }
  }
  return error.status === 422 || error.status === 409
    ? { kind: 'fields', errors: {}, message: error.detail }
    : { kind: 'other', message: `We couldn’t save ${what}. Try again in a moment.` }
}
