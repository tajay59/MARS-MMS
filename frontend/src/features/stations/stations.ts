import type { InstalledUnit, StationStatus, StationSummary } from '@/api/models'
import type { LocationQuery } from 'vue-router'
import { formatShortDate } from '@/app/format'
import { stationStatusIcons } from '@/app/theme/icons'

/*
  The stations list and page (PRD STN-5, CAL-3, CAL-4; DBD "Stations list", "Station page").
  No Vue here, so Vitest covers it directly.
*/

export const STATUSES: readonly StationStatus[] = ['operational', 'degraded', 'offline', 'decommissioned']

/** Station status (DBD Status colours): chip colours from the feedback pairs, marker colour fixed. */
export const statusLook: Record<StationStatus, { label: string, icon: string, chip: string, mark: string }> = {
  operational: { label: 'Operational', icon: stationStatusIcons.operational, chip: 'bg-success-container text-on-success-container', mark: 'text-station-operational' },
  degraded: { label: 'Degraded', icon: stationStatusIcons.degraded, chip: 'bg-warning-container text-on-warning-container', mark: 'text-station-degraded' },
  offline: { label: 'Offline', icon: stationStatusIcons.offline, chip: 'bg-error-container text-on-error-container', mark: 'text-station-offline' },
  decommissioned: { label: 'Decommissioned', icon: stationStatusIcons.decommissioned, chip: 'bg-surface-200 text-surface-700', mark: 'text-station-decommissioned' },
}

export function isStatus (value: unknown): value is StationStatus {
  return typeof value === 'string' && (STATUSES as readonly string[]).includes(value)
}

/** The look of a status from the API (a plain string there); an unknown one shows as grey. */
export function lookOf (status: string): (typeof statusLook)[StationStatus] {
  return statusLook[isStatus(status) ? status : 'decommissioned']
}

// --- Calibration due (DBD "Other status sets": green in date, amber within 30 days, red overdue,
// grey no interval) --------------------------------------------------------------------------------

export const DUE_SOON_DAYS = 30 // CAL-4, the same window as the server's
export type DueState = 'overdue' | 'due_soon' | 'ok'

export function dueState (dueIso: string | null | undefined, now: Date = new Date()): DueState | null {
  if (!dueIso) {
    return null
  }
  const due = new Date(dueIso).getTime()
  if (Number.isNaN(due)) {
    return null
  }
  if (due < now.getTime()) {
    return 'overdue'
  }
  return due <= now.getTime() + DUE_SOON_DAYS * 86_400_000 ? 'due_soon' : 'ok'
}

export const dueLook: Record<DueState | 'none', string> = {
  overdue: 'bg-error-container text-on-error-container',
  due_soon: 'bg-warning-container text-on-warning-container',
  ok: 'bg-success-container text-on-success-container',
  none: 'bg-surface-200 text-surface-700',
}

/** `Overdue since 14 Feb`, `Due 5 Nov`, `In date`, `No interval`. */
export function dueLabel (state: DueState | null, dueIso: string | null | undefined, timeZone?: string | null, now: Date = new Date()): string {
  switch (state) {
    case 'overdue': {
      return `Overdue since ${formatShortDate(dueIso, timeZone, now)}`
    }
    case 'due_soon': {
      return `Due ${formatShortDate(dueIso, timeZone, now)}`
    }
    case 'ok': {
      return 'In date'
    }
    default: {
      return 'No interval'
    }
  }
}

// --- Filters, kept in the URL so a reload or a shared link keeps them (DBD "Lists") ------------

export interface StationFilters {
  q: string
  status: StationStatus | null
  org: string | null
  country: string | null
  type: string | null
  parameter: string | null
}

function one (value: LocationQuery[string]): string | null {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' && first.trim() ? first.trim() : null
}

export function filtersFrom (query: LocationQuery): StationFilters {
  const status = one(query.status)
  return {
    q: one(query.q) ?? '',
    status: isStatus(status) ? status : null,
    org: one(query.org),
    country: one(query.country),
    type: one(query.type),
    parameter: one(query.parameter)?.toUpperCase() ?? null,
  }
}

/** The query for `filters`, leaving out empty ones. */
export function queryFrom (filters: StationFilters): Record<string, string | undefined> {
  return {
    q: filters.q.trim() || undefined,
    status: filters.status ?? undefined,
    org: filters.org ?? undefined,
    country: filters.country ?? undefined,
    type: filters.type ?? undefined,
    parameter: filters.parameter ?? undefined,
  }
}

/** Every filter but status: the status buttons count what these leave. */
export function matchesOthers (station: StationSummary, filters: StationFilters): boolean {
  const q = filters.q.trim().toLowerCase()
  // The external ID too: staff paste the old system's device ID (W5-8)
  const text = [station.code, station.name, station.external_id ?? ''].map(t => t.toLowerCase())
  if (q && !text.some(t => t.includes(q))) {
    return false
  }
  if (filters.org && station.owner_org_id !== filters.org) {
    return false
  }
  if (filters.country && station.country !== filters.country) {
    return false
  }
  if (filters.type && station.type !== filters.type) {
    return false
  }
  return !filters.parameter || station.parameters.includes(filters.parameter)
}

export function matches (station: StationSummary, filters: StationFilters): boolean {
  return (!filters.status || station.status === filters.status) && matchesOthers(station, filters)
}

/** How many filters besides search and status are set (the phone's "More filters" count). */
export function extraFilterCount (filters: StationFilters): number {
  return [filters.org, filters.country, filters.type, filters.parameter].filter(Boolean).length
}

/** The options the filters offer, from the stations the person can see. */
export function facetsOf (stations: readonly StationSummary[]): {
  orgs: { value: string, title: string }[]
  countries: string[]
  types: string[]
  parameters: string[]
} {
  const orgs = new Map<string, string>()
  const countries = new Set<string>()
  const types = new Set<string>()
  const parameters = new Set<string>()
  for (const s of stations) {
    orgs.set(s.owner_org_id, s.owner_org_name ?? s.owner_org_id)
    countries.add(s.country)
    if (s.type) {
      types.add(s.type)
    }
    for (const p of s.parameters) {
      parameters.add(p)
    }
  }
  const byText = (a: string, b: string) => a.localeCompare(b)
  return {
    orgs: sorted([...orgs].map(([value, title]) => ({ value, title })), (a, b) => byText(a.title, b.title)),
    countries: sorted([...countries], byText),
    types: sorted([...types], byText),
    parameters: sortParameters([...parameters]),
  }
}

// The common parameters in the order people read them (TRD §5.2), then the rest A–Z
const COMMON = ['AT', 'RH', 'BP', 'RAIN', 'WS', 'WD', 'SR']

/** The common parameters present (shown as chips) and the rest (a searchable field): the real
    stations measure about a hundred (W5-8), too many for a row of chips. */
export function splitParameters (parameters: readonly string[]): { common: string[], other: string[] } {
  const all = sortParameters(parameters)
  return { common: all.filter(p => COMMON.includes(p)), other: all.filter(p => !COMMON.includes(p)) }
}

export function sortParameters (parameters: readonly string[]): string[] {
  const rank = (p: string) => {
    const i = COMMON.indexOf(p)
    return i === -1 ? COMMON.length : i
  }
  return sorted(parameters, (a, b) => rank(a) - rank(b) || a.localeCompare(b))
}

/** A sorted copy (Array.prototype.toSorted needs iOS 16). */
function sorted<T> (items: readonly T[], compare: (a: T, b: T) => number): T[] {
  // A fresh copy: sorting it in place is safe
  // eslint-disable-next-line unicorn/no-array-sort
  return [...items].sort(compare)
}

// --- Installed units ----------------------------------------------------------------------------

export const kinds: Record<string, string> = {
  sensor: 'Sensor',
  logger: 'Logger',
  modem: 'Modem',
  battery: 'Battery',
  solar_panel: 'Solar panel',
  other: 'Other',
}

export function kindLabel (kind: string): string {
  return kinds[kind] ?? kind
}

/** Sensors by parameter as the station lists them, then the other parts by kind. */
export function sortInstalled (units: readonly InstalledUnit[]): InstalledUnit[] {
  const order = sortParameters(units.flatMap(u => u.parameter ? [u.parameter] : []))
  const kindOrder = Object.keys(kinds)
  return sorted(units, (a, b) => {
    if (a.parameter && b.parameter) {
      return order.indexOf(a.parameter) - order.indexOf(b.parameter)
    }
    if (a.parameter || b.parameter) {
      return a.parameter ? -1 : 1
    }
    return kindOrder.indexOf(a.model.kind) - kindOrder.indexOf(b.model.kind) || a.serial.localeCompare(b.serial)
  })
}

export const methodLabel: Record<string, string> = {
  field_check: 'Field check',
  field_adjust: 'Field adjustment',
  lab: 'Lab',
}

/** Calibration result (DBD: green pass, blue adjusted, red fail). */
export const resultLook: Record<string, { label: string, chip: string }> = {
  pass: { label: 'Pass', chip: 'bg-success-container text-on-success-container' },
  adjusted: { label: 'Adjusted', chip: 'bg-info-container text-on-info-container' },
  fail: { label: 'Fail', chip: 'bg-error-container text-on-error-container' },
}
