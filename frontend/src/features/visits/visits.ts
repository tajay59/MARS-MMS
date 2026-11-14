import type { VisitAction, VisitOut, VisitStatus } from '@/api/models'
import { mdiCalendarOutline, mdiCancel, mdiCheckCircleOutline, mdiPlayCircleOutline } from '@mdi/js'

/*
  Visits: the list, the visit page and its forms (PRD VIS-1 to VIS-4, VIS-9, VIS-11; AFD J5; W10).
  No Vue here, so Vitest covers it directly.

  Dates are stored in UTC (rule 8). A form takes them in the zone of the first station of the
  visit and shows that zone beside the fields; each station on the page shows its own local time.
*/

export const VISIT_STATUSES: readonly VisitStatus[] = ['planned', 'started', 'ended', 'cancelled']

interface Look {
  label: string
  icon: string
  /** Whole class names, so Tailwind sees them. Not a request status colour: those are reserved. */
  chip: string
}

export const visitLook: Record<VisitStatus, Look> = {
  planned: { label: 'Planned', icon: mdiCalendarOutline, chip: 'bg-surface-100 text-surface-800' },
  started: { label: 'Started', icon: mdiPlayCircleOutline, chip: 'bg-primary-100 text-primary-800 dark:bg-primary-800 dark:text-primary-100' },
  ended: { label: 'Ended', icon: mdiCheckCircleOutline, chip: 'bg-surface-100 text-surface-800' },
  cancelled: { label: 'Cancelled', icon: mdiCancel, chip: 'bg-surface-100 text-surface-600 line-through' },
}

export function lookOfVisit (status: string): Look {
  return visitLook[(VISIT_STATUSES as readonly string[]).includes(status) ? status as VisitStatus : 'cancelled']
}

export function canDo (visit: Pick<VisitOut, 'actions'>, action: VisitAction): boolean {
  return visit.actions.includes(action)
}

/** Planned and started visits are live: they hold their stations (W10-5). */
export function isLive (status: string): boolean {
  return status === 'planned' || status === 'started'
}

// --- Times in a zone ---------------------------------------------------------------------------

const LOCAL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/

function partsIn (ms: number, zone: string): Record<string, number> {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: zone, year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', second: 'numeric', hourCycle: 'h23',
  }).formatToParts(new Date(ms))
  const out: Record<string, number> = {}
  for (const p of parts) {
    if (p.type !== 'literal') {
      out[p.type] = Number(p.value)
    }
  }
  return out
}

/** The zone's offset from UTC at `ms`, in milliseconds (America/Jamaica: -5 h). */
function offsetAt (ms: number, zone: string): number {
  const p = partsIn(ms, zone)
  return Date.UTC(p.year!, p.month! - 1, p.day!, p.hour!, p.minute!, p.second!) - Math.floor(ms / 1000) * 1000
}

/** `2026-10-22T08:00` typed in `zone` as the UTC instant it means (ISO, to the minute). */
export function zonedToUtc (local: string, zone: string): string | null {
  const match = LOCAL.exec(local)
  if (!match) {
    return null
  }
  const [, y, mo, d, h, mi] = match.map(Number) as [number, number, number, number, number, number]
  const wall = Date.UTC(y, mo - 1, d, h, mi)
  try {
    // Two passes: the offset can differ at the instant we first guess (a clock change nearby)
    let utc = wall - offsetAt(wall, zone)
    utc = wall - offsetAt(utc, zone)
    return new Date(utc).toISOString()
  } catch {
    return null
  }
}

/** The instant as `2026-10-22T08:00` on a wall clock in `zone`, for a `datetime-local` field. */
export function utcToZoned (iso: string, zone: string): string {
  const ms = new Date(iso).getTime()
  if (Number.isNaN(ms)) {
    return ''
  }
  const p = partsIn(ms, zone)
  const two = (n: number) => String(n).padStart(2, '0')
  return `${p.year}-${two(p.month!)}-${two(p.day!)}T${two(p.hour!)}:${two(p.minute!)}`
}

function zoneOrUndefined (zone: string | null | undefined): string | undefined {
  return zone || undefined
}

const SHORT_MONTHS = /\bSept\b/

/** `Thu 22 Oct, 08:00` in `zone` (the viewer's own when absent). */
export function formatWhen (iso: string | null | undefined, zone?: string | null): string {
  if (!iso) {
    return '—'
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  const text = new Intl.DateTimeFormat('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    hourCycle: 'h23', timeZone: zoneOrUndefined(zone),
  }).format(date)
  // en-GB writes `Thu, 22 Oct, 08:00` or `Thu 22 Oct, 08:00` by ICU version; DBD has no comma after the weekday
  return text.replace(SHORT_MONTHS, 'Sep').replace(/^(\w{3}),\s/, '$1 ')
}

/** Just the time: `08:12`. */
export function formatClock (iso: string | null | undefined, zone?: string | null): string {
  if (!iso) {
    return '—'
  }
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? '—'
    : new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: zoneOrUndefined(zone) }).format(date)
}

/** `Thu 22 Oct, 08:00 to Fri 23 Oct, 16:00`; the second half is a bare time when the day is the same. */
export function formatRange (startIso: string, endIso: string, zone?: string | null): string {
  const sameDay = utcToZonedSafe(startIso, zone).slice(0, 10) === utcToZonedSafe(endIso, zone).slice(0, 10)
  return `${formatWhen(startIso, zone)} to ${sameDay ? formatClock(endIso, zone) : formatWhen(endIso, zone)}`
}

function utcToZonedSafe (iso: string, zone: string | null | undefined): string {
  return zone ? utcToZoned(iso, zone) : iso.slice(0, 16)
}

/** The short name of the zone at that instant (`EST`), for the line under the dates. */
export function zoneLabel (zone: string, at: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'short' })
      .formatToParts(at)
      .find(p => p.type === 'timeZoneName')
      ?.value ?? zone
  } catch {
    return zone
  }
}

/** The zone of a visit's first station: the one its dates are written in. */
export function visitZone (visit: Pick<VisitOut, 'stations'>): string | null {
  return visit.stations.find(s => s.time_zone)?.time_zone ?? null
}

// --- The schedule form -------------------------------------------------------------------------

export const MAX_DAYS = 31

export interface ScheduleValues {
  start: string
  end: string
  staffIds: string[]
  leadId: string | null
  /** station id -> owner id; a station that is not a key is not on the visit */
  owners: Record<string, string>
}

export interface ScheduleErrors {
  start?: string
  end?: string
  staff?: string
  stations?: string
}

/** What is wrong with the form, in the words the page shows; empty when it can be sent. */
export function validateSchedule (values: ScheduleValues, zone: string, now: Date = new Date()): ScheduleErrors {
  const errors: ScheduleErrors = {}
  const start = zonedToUtc(values.start, zone)
  const end = zonedToUtc(values.end, zone)
  if (!start) {
    errors.start = 'Choose when it starts'
  }
  if (!end) {
    errors.end = 'Choose when it ends'
  }
  if (start && end) {
    const span = new Date(end).getTime() - new Date(start).getTime()
    if (span <= 0) {
      errors.end = 'The visit must end after it starts'
    } else if (span > MAX_DAYS * 86_400_000) {
      errors.end = `A visit lasts at most ${MAX_DAYS} days`
    }
  }
  if (start && new Date(start).getTime() < now.getTime() - 86_400_000) {
    errors.start = 'That is in the past'
  }
  if (values.staffIds.length === 0) {
    errors.staff = 'Pick at least one person'
  }
  const stations = Object.keys(values.owners)
  if (stations.length === 0) {
    errors.stations = 'Pick at least one station'
  } else if (stations.some(id => !values.staffIds.includes(values.owners[id]!))) {
    errors.stations = 'Each station’s owner must be one of the people attending'
  }
  return errors
}

/** Takes someone off the visit: the lead passes to the first person left, and their stations to the lead. */
export function withoutPerson (values: ScheduleValues, id: string): ScheduleValues {
  const staffIds = values.staffIds.filter(s => s !== id)
  const leadId = values.leadId === id ? (staffIds[0] ?? null) : values.leadId
  const owners: Record<string, string> = {}
  for (const [station, owner] of Object.entries(values.owners)) {
    const next = owner === id ? leadId : owner
    if (next) {
      owners[station] = next
    }
  }
  return { ...values, staffIds, leadId, owners }
}

// --- Lists -------------------------------------------------------------------------------------

export interface VisitFilters {
  q: string
  /** `mine`: visits I attend; `all`: everyone's (staff who may see all). */
  scope: 'mine' | 'all'
}

export function matchesVisit (visit: VisitOut, q: string): boolean {
  const text = q.trim().toLowerCase()
  if (!text) {
    return true
  }
  return [visit.ref, visit.request_ref ?? '', visit.request_title ?? '', ...visit.stations.flatMap(s => [s.station_code ?? '', s.station_name ?? ''])]
    .some(t => t.toLowerCase().includes(text))
}

/** Live visits soonest first, then the finished ones newest first. */
export function sortVisits (visits: readonly VisitOut[]): VisitOut[] {
  const live = visits.filter(v => isLive(v.status))
  const done = visits.filter(v => !isLive(v.status))
  // Fresh arrays: sorting them in place is safe, and toSorted needs iOS 16

  live.sort((a, b) => a.planned_start.localeCompare(b.planned_start))

  done.sort((a, b) => b.planned_start.localeCompare(a.planned_start))
  return [...live, ...done]
}

/** `Kingston Harbour, Montego Bay` for a card's second line. */
export function stationNames (visit: Pick<VisitOut, 'stations'>): string {
  return visit.stations.map(s => s.station_name ?? s.station_code ?? '').filter(Boolean).join(', ')
}

export function names (people: readonly { name: string }[]): string {
  return people.map(p => p.name).join(', ')
}

// --- A person's row on a station ----------------------------------------------------------------

/** What a station row says in the Times column. */
export function stationTimes (visit: Pick<VisitOut, 'status' | 'planned_start'>, station: VisitOut['stations'][number]): string {
  const zone = station.time_zone
  if (station.departed_at) {
    return `Arrived ${formatClock(station.arrived_at, zone)}, left ${formatClock(station.departed_at, zone)}`
  }
  if (station.arrived_at) {
    return `Arrived ${formatClock(station.arrived_at, zone)}`
  }
  if (visit.status === 'planned') {
    return `Planned for ${formatWhen(visit.planned_start, zone)}`
  }
  return visit.status === 'started' ? 'Not arrived' : '—'
}
