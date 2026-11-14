import type { ClientReportOut, ClientReportPatch } from '@/api/models'
import { ApiError, NetworkError } from '@/api/problem'

/*
  A client's own report as the page edits it (PRD CRP-1 to CRP-4; AFD J9; W18-9, W18-10). No Vue
  here, so Vitest covers it. The server checks every rule again; these only say so before sending,
  and work out what changed so a save sends only that.
*/

export const TITLE_MAX = 200
export const SUMMARY_MAX = 10_000
export const OBSERVATION_MAX = 5000
export const NOTES_MAX = 5000
export const MAX_IMAGES = 10
export const IMAGE_TYPES = ['image/jpeg', 'image/png']

export interface Model {
  title: string
  reportDate: string // YYYY-MM-DD
  stationIds: string[]
  summary: string
  /** station id -> what was seen there */
  observations: Record<string, string>
  notes: string
}

export function emptyModel (stationIds: string[], today: Date = new Date()): Model {
  return { title: '', reportDate: isoDay(today), stationIds, summary: '', observations: {}, notes: '' }
}

export function isoDay (date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/** The model of a draft the server holds. */
export function modelOf (report: ClientReportOut): Model {
  return {
    title: report.title,
    reportDate: report.report_date,
    stationIds: [...report.station_ids],
    summary: report.form.summary,
    observations: Object.fromEntries(report.form.observations.map(o => [o.station_id, o.text])),
    notes: report.form.data_quality_notes,
  }
}

function sameList (a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((value, i) => value === b[i])
}

/** What to send to change `before` into `now`: only the fields that differ (a draft's `version` is added by the caller). */
export function patchOf (before: Model, now: Model, kind: ClientReportOut['kind']): Omit<ClientReportPatch, 'version'> {
  const patch: Omit<ClientReportPatch, 'version'> = {}
  if (now.title !== before.title) {
    patch.title = now.title
  }
  if (now.reportDate !== before.reportDate && now.reportDate) {
    patch.report_date = now.reportDate
  }
  if (!sameList(now.stationIds, before.stationIds)) {
    patch.station_ids = now.stationIds
  }
  if (kind === 'form') {
    if (now.summary !== before.summary) {
      patch.summary = now.summary
    }
    if (now.notes !== before.notes) {
      patch.data_quality_notes = now.notes
    }
    const covered = now.stationIds
    const seen = (model: Model) => covered.map(id => (model.observations[id] ?? '').trim()).join('\u0000')
    const changed = seen(now) !== seen(before) || !sameList(now.stationIds, before.stationIds)
    if (changed) {
      patch.observations = covered
        .map(id => ({ station_id: id, text: now.observations[id] ?? '' }))
        .filter(o => o.text.trim() !== '')
    }
  }
  return patch
}

export function isEmptyPatch (patch: object): boolean {
  return Object.keys(patch).length === 0
}

export interface Pieces {
  /** A PDF report: the PDF is ready (checked by media). */
  fileReady: boolean
  /** Files still on their way, or failed. */
  filesBusy: boolean
}

/** Why the report can't be sent yet, with the field to point at; null when it can. */
export function submitProblem (kind: ClientReportOut['kind'], model: Model, pieces: Pieces): { field: string, text: string } | null {
  if (!model.title.trim()) {
    return { field: 'title', text: 'Give the report a title.' }
  }
  if (model.stationIds.length === 0) {
    return { field: 'stations', text: 'Choose the stations it covers.' }
  }
  if (kind === 'pdf') {
    if (pieces.filesBusy) {
      return { field: 'file', text: 'Wait for the PDF to finish uploading.' }
    }
    if (!pieces.fileReady) {
      return { field: 'file', text: 'Upload the PDF first.' }
    }
    return null
  }
  if (!model.summary.trim()) {
    return { field: 'summary', text: 'Write a summary.' }
  }
  if (pieces.filesBusy) {
    return { field: 'file', text: 'Wait for the pictures to finish uploading.' }
  }
  return null
}

/** Why this picture can't be added, in words for the person; null when it can. */
export function imageProblem (file: { name: string, size: number, type: string }): string | null {
  const named = /\.(?:jpe?g|png)$/i.test(file.name)
  if (!IMAGE_TYPES.includes(file.type) && !named) {
    return 'Only JPEG and PNG pictures can be added.'
  }
  if (file.size === 0) {
    return 'This file is empty.'
  }
  return null
}

export type SaveState = 'idle' | 'saving' | 'saved' | 'retrying'

/** The words next to the title: Saved at 14:02, Saving…, Not saved yet. Retrying… */
export function saveWords (state: SaveState, at: Date | null): string {
  switch (state) {
    case 'saving': {
      return 'Saving…'
    }
    case 'retrying': {
      return 'Not saved yet. Retrying…'
    }
    case 'saved': {
      return at ? `Saved at ${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}` : 'Saved'
    }
    default: {
      return ''
    }
  }
}

/** What a failed save or send says. `stale` means the server's copy is newer and was read again. */
export function failureWords (error: unknown): { text: string, stale: boolean, gone: boolean } {
  if (error instanceof NetworkError) {
    return { text: 'This needs a connection. What you typed is still here.', stale: false, gone: false }
  }
  if (error instanceof ApiError) {
    if (error.code === 'version_conflict') {
      return { text: 'This report changed in another window. The latest version is on the page now.', stale: true, gone: false }
    }
    if (error.code === 'not_a_draft') {
      return { text: 'This report was already sent, so it cannot be changed. You can add another.', stale: false, gone: true }
    }
    if (error.code === 'request_not_reportable') {
      return { text: 'This request cannot take a report now.', stale: false, gone: true }
    }
    if (error.status === 404) {
      return { text: 'This report could not be found.', stale: false, gone: true }
    }
    if (error.status === 422 || error.status === 409) {
      return { text: error.detail, stale: false, gone: false }
    }
  }
  return { text: 'Something went wrong. Try again.', stale: false, gone: false }
}
