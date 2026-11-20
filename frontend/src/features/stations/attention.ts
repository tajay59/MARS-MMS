import type { RequestSummary, StationSummary, VisitOut } from '@/api/models'
import type { LocationQuery } from 'vue-router'
import { mdiCalendarAlertOutline, mdiCalendarClockOutline } from '@mdi/js'
import { formatShortDate } from '@/app/format'
import { stationStatusIcons } from '@/app/theme/icons'
import { dueState } from './stations'

/*
  The Needs attention list of /stations (approved "AWS-MMS Stations redesign"; surface brief in
  .impeccable/surfaces/). No Vue here. Only facts the system holds go in a row: the status staff
  set, the next calibration due date, the last visit, and the station's open visits and requests.
  The app receives no weather data, so nothing here says when a station last sent any.
*/

export type Problem = 'offline' | 'degraded' | 'overdue' | 'idle'

/** Most urgent first: a station shows under its worst problem. */
export const PROBLEMS: readonly Problem[] = ['offline', 'degraded', 'overdue', 'idle']

export const IDLE_DAYS = 90
const DAY = 86_400_000

export const problemLook: Record<Problem, { label: string, short: string, chip: string, mark: string, icon: string }> = {
  offline: { label: 'Offline', short: 'Offline', chip: 'bg-error-container text-on-error-container', mark: 'text-station-offline', icon: stationStatusIcons.offline },
  degraded: { label: 'Degraded', short: 'Degraded', chip: 'bg-warning-container text-on-warning-container', mark: 'text-station-degraded', icon: stationStatusIcons.degraded },
  overdue: { label: 'Calibration overdue', short: 'Calibration overdue', chip: 'bg-error-container text-on-error-container', mark: 'text-error', icon: mdiCalendarAlertOutline },
  idle: { label: `No visit in ${IDLE_DAYS} days`, short: `No visit in ${IDLE_DAYS} days`, chip: 'bg-surface-200 text-surface-700', mark: 'text-station-decommissioned', icon: mdiCalendarClockOutline },
}

export function isProblem (value: unknown): value is Problem {
  return PROBLEMS.includes(value as Problem)
}

function daysSince (iso: string, now: Date): number {
  return Math.floor((now.getTime() - new Date(iso).getTime()) / DAY)
}

/**
 * What is wrong with a station, worst first. Decommissioned stations have nothing to fix. A
 * station never visited is not "idle": imported stations have no visits in this system yet.
 */
export function problemsOf (station: StationSummary, now: Date): Problem[] {
  if (station.status === 'decommissioned') {
    return []
  }
  const found: Problem[] = []
  if (station.status === 'offline' || station.status === 'degraded') {
    found.push(station.status)
  }
  if (dueState(station.next_calibration_due_at, now) === 'overdue') {
    found.push('overdue')
  }
  if (station.last_visit_at && daysSince(station.last_visit_at, now) >= IDLE_DAYS) {
    found.push('idle')
  }
  return found
}

export function problemCounts (stations: readonly StationSummary[], now: Date): Record<Problem, number> {
  const counts: Record<Problem, number> = { offline: 0, degraded: 0, overdue: 0, idle: 0 }
  for (const s of stations) {
    for (const p of problemsOf(s, now)) {
      counts[p]++
    }
  }
  return counts
}

// --- The open work at each station ------------------------------------------------------------

export const OPEN_REQUEST_STATUSES = ['submitted', 'approved', 'assigned', 'scheduled', 'in_progress', 'client_review', 'reopened'] as const

export interface OpenVisit { id: string, ref: string, status: 'planned' | 'started', plannedStart: string, timeZone: string | null }
export interface OpenRequest { id: string, ref: string, status: string, updatedAt: string }

export interface Work {
  visits: Map<string, OpenVisit>
  requests: Map<string, OpenRequest>
}

export function emptyWork (): Work {
  return { visits: new Map(), requests: new Map() }
}

/** Per station: the started visit, else the next planned one; the request changed last. */
export function workFrom (visits: readonly VisitOut[], requests: readonly RequestSummary[]): Work {
  const work = emptyWork()
  for (const v of visits) {
    if (v.status !== 'planned' && v.status !== 'started') {
      continue
    }
    for (const s of v.stations) {
      const had = work.visits.get(s.station_id)
      const candidate: OpenVisit = { id: v.id, ref: v.ref, status: v.status, plannedStart: v.planned_start, timeZone: s.time_zone ?? null }
      const better = !had
        || (candidate.status === 'started' && had.status !== 'started')
        || (candidate.status === had.status && candidate.plannedStart < had.plannedStart)
      if (better) {
        work.visits.set(s.station_id, candidate)
      }
    }
  }
  for (const r of requests) {
    if (!(OPEN_REQUEST_STATUSES as readonly string[]).includes(r.status)) {
      continue
    }
    for (const s of r.stations) {
      const had = work.requests.get(s.id)
      if (!had || r.updated_at > had.updatedAt) {
        work.requests.set(s.id, { id: r.id, ref: r.ref, status: r.status, updatedAt: r.updated_at })
      }
    }
  }
  return work
}

// --- Rows -------------------------------------------------------------------------------------

export type NextStep
  = | { kind: 'visit', id: string, label: 'Open the visit' }
    | { kind: 'request', id: string, label: 'Open the request' }
    | { kind: 'raise', stationId: string, label: 'Raise a request' }

export interface AttentionRow {
  station: StationSummary
  problem: Problem
  /** One sentence: the problem and its fact, then the open work. */
  fact: string
  /** The reference of the open work, shown with the organization. */
  workRef: string | null
  /** The station's other problems, worst first ("Also calibration overdue"). */
  also: Problem[]
  next: NextStep | null
}

/** The next step: open what is already under way, else raise a request; nothing for those who can't act. */
export function nextStep (stationId: string, work: Work, canAct: boolean): NextStep | null {
  if (!canAct) {
    return null
  }
  const visit = work.visits.get(stationId)
  if (visit) {
    return { kind: 'visit', id: visit.id, label: 'Open the visit' }
  }
  const request = work.requests.get(stationId)
  if (request) {
    return { kind: 'request', id: request.id, label: 'Open the request' }
  }
  return { kind: 'raise', stationId, label: 'Raise a request' }
}

function problemText (station: StationSummary, problem: Problem, now: Date): string {
  const tz = station.time_zone
  switch (problem) {
    case 'offline':
    case 'degraded': {
      const visit = station.last_visit_at ? `last visit ${formatShortDate(station.last_visit_at, tz, now)}` : 'no visit yet'
      return `Marked ${problem} · ${visit}`
    }
    case 'overdue': {
      const days = daysSince(station.next_calibration_due_at!, now)
      const when = formatShortDate(station.next_calibration_due_at, tz, now)
      return days < 1 ? `Calibration overdue since today (${when})` : `Calibration ${days} ${days === 1 ? 'day' : 'days'} overdue (due ${when})`
    }
    case 'idle': {
      return `Last visited ${daysSince(station.last_visit_at!, now)} days ago (${formatShortDate(station.last_visit_at, tz, now)})`
    }
  }
}

function workText (stationId: string, work: Work, now: Date): { text: string, ref: string } | null {
  const visit = work.visits.get(stationId)
  if (visit) {
    return visit.status === 'started'
      ? { text: 'visit under way', ref: visit.ref }
      : { text: `visit planned for ${formatShortDate(visit.plannedStart, visit.timeZone, now)}`, ref: visit.ref }
  }
  const request = work.requests.get(stationId)
  if (request) {
    return { text: request.status === 'submitted' ? 'request waiting for approval' : 'request open', ref: request.ref }
  }
  return null
}

/** How bad a row is inside its problem: the longest overdue or unvisited first, then by code. */
function weight (row: AttentionRow, now: Date): number {
  const s = row.station
  if (row.problem === 'overdue') {
    return daysSince(s.next_calibration_due_at!, now)
  }
  if (row.problem === 'idle') {
    return daysSince(s.last_visit_at!, now)
  }
  // Offline or degraded with nothing under way comes before the ones already being handled
  return row.workRef ? 0 : 1
}

export function attentionRows (stations: readonly StationSummary[], work: Work, now: Date, canAct: boolean, only: Problem | null = null): AttentionRow[] {
  const rows: AttentionRow[] = []
  for (const station of stations) {
    const found = problemsOf(station, now)
    const problem = only ? (found.includes(only) ? only : null) : (found[0] ?? null)
    if (!problem) {
      continue
    }
    const open = workText(station.id, work, now)
    const base = problemText(station, problem, now)
    // With work under way, an offline or degraded row says that instead of the last visit
    const lead = problem === 'offline' || problem === 'degraded' ? `Marked ${problem}` : base
    rows.push({
      station,
      problem,
      fact: open ? `${lead} · ${open.text}` : base,
      workRef: open?.ref ?? null,
      also: found.filter(p => p !== problem),
      next: nextStep(station.id, work, canAct),
    })
  }
  return rows.toSorted((a, b) =>
    PROBLEMS.indexOf(a.problem) - PROBLEMS.indexOf(b.problem)
    || weight(b, now) - weight(a, now)
    || a.station.code.localeCompare(b.station.code))
}

// --- The page's state in the URL ---------------------------------------------------------------

export type StationsView = 'attention' | 'all'

/** `?view=all` shows the register; a link that arrives with a filter (an organization's stations) does too. */
export function viewFrom (query: LocationQuery): StationsView {
  if (query.view === 'all' || query.view === 'attention') {
    return query.view
  }
  return ['status', 'org', 'country', 'type', 'parameter'].some(k => typeof query[k] === 'string' && query[k]) ? 'all' : 'attention'
}

export function problemFrom (query: LocationQuery): Problem | null {
  return isProblem(query.problem) ? query.problem : null
}
