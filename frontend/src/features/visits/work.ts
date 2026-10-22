import type { WorkOut } from '@/api/models'
import { ApiError } from '@/api/problem'
import { type Failure, failureOf } from './failures'

/*
  Words for a station's work record (PRD VIS-7; W11). The record holds typed data; the visit page
  shows what was done as sentences, and what the server refuses as a message a person can act on.
  No Vue here.
*/

type Row = Record<string, unknown>

export interface Segment {
  text: string
  /** A serial or other reference, shown in the mono face. */
  mono?: boolean
  bold?: boolean
}

export interface ActionSentence {
  id: string
  segments: Segment[]
  /** The line under it: why a unit left, the result of a check, or the technician's note. */
  detail: string | null
  /** False for the actions that are notes only (clean, repair): the inventory did not change. */
  changesInventory: boolean
}

const REMOVAL: Record<string, string> = {
  faulty: 'The old unit went to repair (faulty).',
  calibration: 'The unit went back to stock for calibration.',
  retired: 'The unit was retired.',
  other: 'The unit went back to stock.',
}

const RESULT: Record<string, string> = {
  pass: 'passed',
  adjusted: 'adjusted',
  fail: 'failed',
}

function text (value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function serial (value: unknown): Segment {
  return { text: text(value) ?? 'unknown unit', mono: true }
}

function sensorOf (row: Row, noun = 'sensor'): Segment[] {
  const parameter = text(row.parameter)
  return parameter ? [{ text: parameter, bold: true }, { text: ` ${noun} ` }] : [{ text: `${noun} ` }]
}

function calibrationDetail (row: Row): string | null {
  const calibration = row.calibration as Row | null | undefined
  const instrument = calibration?.reference_instrument as Row | null | undefined
  const name = text(instrument?.name)
  return name ? `Checked against ${name}.` : null
}

/** One sensor action as a sentence: "Replaced AT sensor V-23001 with V-23044". */
export function actionSentence (row: Row): ActionSentence {
  const id = String(row.id ?? '')
  const note = text(row.note)
  const reason = REMOVAL[String(row.removal_reason ?? '')] ?? null
  switch (row.action) {
    case 'replace': {
      return {
        id, changesInventory: true, detail: [reason, note].filter(Boolean).join(' ') || null,
        segments: [{ text: 'Replaced ' }, ...sensorOf(row), serial(row.old_serial), { text: ' with ' }, serial(row.new_serial)],
      }
    }
    case 'install': {
      return {
        id, changesInventory: true, detail: note,
        segments: [{ text: 'Installed ' }, ...sensorOf(row), serial(row.new_serial)],
      }
    }
    case 'remove': {
      return {
        id, changesInventory: true, detail: [reason, note].filter(Boolean).join(' ') || null,
        segments: [{ text: 'Removed ' }, ...sensorOf(row), serial(row.old_serial)],
      }
    }
    case 'calibrate': {
      const calibration = row.calibration as Row | null | undefined
      const result = RESULT[String(calibration?.result ?? '')]
      const method = calibration?.method === 'field_adjust' ? 'field adjustment' : 'field check'
      return {
        id, changesInventory: true, detail: [calibrationDetail(row), note].filter(Boolean).join(' ') || null,
        segments: [
          { text: 'Calibrated ' }, ...sensorOf(row), serial(row.old_serial ?? row.new_serial),
          ...(result ? [{ text: ': ' }, { text: result, bold: true }, { text: ` (${method})` }] : []),
        ],
      }
    }
    case 'clean':
    case 'repair': {
      return {
        id, changesInventory: false, detail: note ?? 'A note only; the inventory did not change.',
        segments: [{ text: row.action === 'clean' ? 'Cleaned ' : 'Repaired ' }, ...sensorOf(row), serial(row.old_serial ?? row.new_serial)],
      }
    }
    default: {
      return { id, changesInventory: false, detail: note, segments: [{ text: 'Sensor work' }] }
    }
  }
}

export function actionSentences (work: Pick<WorkOut, 'sensor_actions'>): ActionSentence[] {
  return work.sensor_actions.map(row => actionSentence(row))
}

/** The plain text of a sentence, for a screen reader label and tests. */
export function plain (sentence: ActionSentence): string {
  return sentence.segments.map(s => s.text).join('')
}

const SEVERITY: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High' }

export function severityLabel (value: unknown): string {
  return SEVERITY[String(value)] ?? 'Medium'
}

export const RESULT_LABEL: Record<string, string> = {
  ok: 'OK',
  fixed: 'Fixed',
  issue: 'Issue',
  na: 'Not applicable',
}

export const CONDITION_LABEL: Record<string, string> = {
  operational: 'Operational',
  degraded: 'Degraded',
  offline: 'Offline',
}

/** How the check-up stands: counts for the summary line above the checklist. */
export function checklistSummary (rows: readonly { result: string | null }[]): string {
  if (rows.length === 0) {
    return 'No checklist'
  }
  const count = (result: string) => rows.filter(r => r.result === result).length
  const answered = rows.filter(r => r.result !== null).length
  const parts = [`${answered} of ${rows.length} answered`]
  if (count('issue') > 0) {
    parts.push(`${count('issue')} with an issue`)
  }
  if (count('fixed') > 0) {
    parts.push(`${count('fixed')} fixed`)
  }
  return parts.join(', ')
}

export interface ChecklistGroup {
  /** The heading above the rows; null for rows with none. */
  title: string | null
  rows: WorkOut['checklist']
}

/**
 * The checklist as it reads: the template's rows under their own headings in the order the template
 * gave them, then the items the technician added on the visit (VIS-8) under one heading.
 */
export function checklistGroups (rows: WorkOut['checklist']): ChecklistGroup[] {
  const groups: ChecklistGroup[] = []
  for (const row of rows.filter(r => !r.ad_hoc)) {
    const title = row.group ?? null
    const last = groups.at(-1)
    if (last && last.title === title) {
      last.rows.push(row)
    } else {
      groups.push({ title, rows: [row] })
    }
  }
  const added = rows.filter(r => r.ad_hoc)
  if (added.length > 0) {
    groups.push({ title: 'Added on the visit', rows: added })
  }
  return groups
}

/** "Yes, 1 Oct 2026 to 22 Oct 2026", "Yes", or "No". */
export function downloadedSentence (
  data: WorkOut['data_downloaded'], formatDay: (iso: string) => string,
): string {
  if (!data || !data.done) {
    return 'No'
  }
  if (data.from && data.to) {
    return `Yes, ${formatDay(data.from)} to ${formatDay(data.to)}`
  }
  return 'Yes'
}

/** The server's detail with a full stop, so another sentence can follow it. */
function sentence (detail: string): string {
  return /[.!?]$/.test(detail) ? detail : `${detail}.`
}

const WORK_CONFLICTS: Record<string, string> = {
  work_changed: 'This record was changed since you opened it. Your edits were not saved. Reload to see the current record, then make them again.',
  model_required: 'Say which model that sensor is. Nothing was saved.',
  config_files_not_ready: 'A configuration file is still being checked. Try again in a moment.',
  config_version_immutable: 'A configuration version can’t be changed once it is saved. Add a new one instead.',
  not_started: 'Start the visit first.',
  locked: 'The visit report has been finalized. Ask an admin to reopen it.',
}

/**
 * What a refused save of the work record says (board 5). The server names the unit and the later
 * change, and what to do about it, in its own words; this adds what happened to the record.
 */
export function workFailure (error: unknown, fallback = 'Could not save the record. Try again.'): Failure {
  if (error instanceof ApiError) {
    if (error.code === 'sensor_changed_later') {
      return {
        message: `${sentence(error.detail)} Nothing was saved, so your record is as you left it.`,
        reload: true,
      }
    }
    const known = WORK_CONFLICTS[error.code]
    if (known) {
      return { message: known, reload: error.code === 'work_changed' || error.code === 'locked' }
    }
    if (error.status === 422) {
      return { message: `${sentence(error.detail)} Nothing was saved.`, reload: false, field: error.field ?? undefined }
    }
  }
  return failureOf(error, fallback)
}
