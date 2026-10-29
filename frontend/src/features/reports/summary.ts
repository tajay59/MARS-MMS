import type { SummaryIn, SummaryJob, SummaryKind, SummaryType } from '@/api/models'

/*
  Summary reports (PRD SUM-1 to SUM-3, CAL-4; AFD J10; decisions W19-8 to W19-10). No Vue here,
  so Vitest covers it directly.

  A period is two plain dates. The server turns them into UTC times at 00:00 in the report's
  zone (America/Jamaica), so a month means the same thing to everyone.
*/

/** The groups in the pane, in order; a type the server sends that is not here lands in Other. */
const GROUPS: readonly { label: string, types: readonly string[] }[] = [
  { label: 'Stations', types: ['station_history', 'station_asset', 'configuration_history', 'network_status'] },
  { label: 'Calibration and sensors', types: ['calibration_due', 'sensor_reliability'] },
  { label: 'Requests and people', types: ['client_activity', 'request_turnaround', 'technician_workload'] },
  { label: 'Maintenance', types: ['monthly_summary', 'annual_summary'] },
]

export interface Group {
  label: string
  types: SummaryType[]
}

export function grouped (types: readonly SummaryType[]): Group[] {
  const known = new Set(GROUPS.flatMap(g => g.types))
  const out: Group[] = GROUPS.map(g => ({
    label: g.label,
    types: g.types.map(key => types.find(t => t.type === key)).filter((t): t is SummaryType => t !== undefined),
  })).filter(g => g.types.length > 0)
  const other = types.filter(t => !known.has(t.type))
  return other.length > 0 ? [...out, { label: 'Other', types: other }] : out
}

export interface Form {
  from: string
  to: string
  org: string | null
  country: string | null
  stations: string[]
  format: 'pdf' | 'csv'
  dueInDays: number
}

export function emptyForm (now: Date = new Date()): Form {
  return { ...lastMonth(now), org: null, country: null, stations: [], format: 'pdf', dueInDays: 30 }
}

function iso (year: number, month: number, day: number): string {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function lastDay (year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate()
}

/** The previous calendar month as two dates. */
export function lastMonth (now: Date): { from: string, to: string } {
  const month = now.getMonth() === 0 ? 12 : now.getMonth()
  const year = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear()
  return { from: iso(year, month, 1), to: iso(year, month, lastDay(year, month)) }
}

/** From 1 January of this year to today. */
export function thisYear (now: Date): { from: string, to: string } {
  return { from: iso(now.getFullYear(), 1, 1), to: iso(now.getFullYear(), now.getMonth() + 1, now.getDate()) }
}

export function lastYear (now: Date): { from: string, to: string } {
  const year = now.getFullYear() - 1
  return { from: iso(year, 1, 1), to: iso(year, 12, 31) }
}

export const PRESETS: readonly { key: string, label: string, make: (now: Date) => { from: string, to: string } }[] = [
  { key: 'last-month', label: 'Last month', make: lastMonth },
  { key: 'this-year', label: 'This year', make: thisYear },
  { key: 'last-year', label: 'Last year', make: lastYear },
]

const MAX_DAYS = 1096

/** What is wrong with the form, in words that say the fix; null when it can be sent. */
export function problemWith (form: Form, usesPeriod: boolean): string | null {
  if (!usesPeriod) {
    return null
  }
  if (!form.from || !form.to) {
    return 'Choose the first and last day.'
  }
  if (form.to < form.from) {
    return 'The last day is before the first day. Swap them.'
  }
  const days = (Date.parse(form.to) - Date.parse(form.from)) / 86_400_000 + 1
  return days > MAX_DAYS ? 'Choose a period of up to three years.' : null
}

/** The request for the server. A client sends no organization: the server uses theirs. */
export function bodyFor (kind: SummaryKind, usesPeriod: boolean, form: Form, client: boolean): SummaryIn {
  return {
    type: kind,
    format: form.format,
    from: usesPeriod ? form.from : null,
    to: usesPeriod ? form.to : null,
    org_id: client ? null : form.org,
    country: form.country,
    station_ids: form.stations.length > 0 ? form.stations : null,
    due_in_days: kind === 'calibration_due' ? form.dueInDays : 30,
  }
}

export interface JobLook {
  /** 'making' while the worker has it, 'ready' with a file, 'failed' with a reason. */
  state: 'making' | 'ready' | 'failed'
  label: string
}

export function lookOfJob (job: Pick<SummaryJob, 'status'>): JobLook {
  switch (job.status) {
    case 'done': {
      return { state: 'ready', label: 'Ready' }
    }
    case 'failed': {
      return { state: 'failed', label: 'Could not be made' }
    }
    default: {
      return { state: 'making', label: job.status === 'queued' ? 'Waiting' : 'Making it' }
    }
  }
}

export function isActive (job: Pick<SummaryJob, 'status'>): boolean {
  return job.status === 'queued' || job.status === 'running'
}

const FAILURES: Record<string, string> = {
  too_large: 'Too many rows. Choose a shorter period or fewer stations.',
  station_not_found: 'A station in this report is not available any more.',
  unavailable: 'The report service could not be reached. Try again.',
  render_failed: 'The report could not be drawn. Try again, and tell an admin if it happens again.',
}

export function failureWords (code: string | null | undefined): string {
  return (code && FAILURES[code]) || FAILURES.render_failed
}

/** `1 Jan to 30 Sep 2026` for a job's period; empty for a report that has none. */
export function periodWords (from: string | null | undefined, to: string | null | undefined): string {
  if (!from || !to) {
    return 'Today'
  }
  const short = (value: string, year: boolean): string => new Date(`${value}T12:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short', ...(year ? { year: 'numeric' } : {}), timeZone: 'UTC',
  }).replace('Sept', 'Sep')
  const sameYear = from.slice(0, 4) === to.slice(0, 4)
  return `${short(from, !sameYear)} to ${short(to, true)}`
}

/** The groups' order is the pane's; the first type is what a page opens with. */
export function firstType (types: readonly SummaryType[]): SummaryKind | null {
  return grouped(types)[0]?.types[0]?.type ?? null
}
