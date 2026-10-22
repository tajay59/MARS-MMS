import type { SensorModelOut, SensorUnitOut } from '@/api/models'
import type { LocationQuery } from 'vue-router'
import { mdiAntenna, mdiArchiveOutline, mdiBatteryOutline, mdiGauge, mdiMemory, mdiRadioTower, mdiShapeOutline, mdiSolarPanel, mdiWarehouse, mdiWrenchOutline } from '@mdi/js'
import { formatDate } from '@/app/format'
import { kindLabel } from '@/features/stations/stations'

/*
  The sensor catalogue (PRD CAL-1, DOC-1): models by kind, their documents and their units.
  No Vue here, so Vitest covers it directly.
*/

export type KindFilter = 'all' | 'sensor' | 'logger' | 'modem' | 'power'

export const kindFilters: { value: KindFilter, label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'sensor', label: 'Sensors' },
  { value: 'logger', label: 'Loggers' },
  { value: 'modem', label: 'Modems' },
  { value: 'power', label: 'Power' },
]

export interface SensorFilters {
  q: string
  kind: KindFilter
}

function one (value: LocationQuery[string]): string {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' ? first.trim() : ''
}

export function sensorFiltersFrom (query: LocationQuery): SensorFilters {
  const kind = one(query.kind)
  return {
    q: one(query.q),
    kind: kindFilters.some(k => k.value === kind) ? kind as KindFilter : 'all',
  }
}

export function sensorQueryFrom (filters: SensorFilters): Record<string, string | undefined> {
  return { q: filters.q || undefined, kind: filters.kind === 'all' ? undefined : filters.kind }
}

export function inKind (model: Pick<SensorModelOut, 'kind'>, kind: KindFilter): boolean {
  if (kind === 'all') {
    return true
  }
  return kind === 'power' ? model.kind === 'battery' || model.kind === 'solar_panel' : model.kind === kind
}

/** Search on make, model and the parameters it measures. */
export function matchesModel (model: SensorModelOut, filters: Pick<SensorFilters, 'q' | 'kind'>): boolean {
  if (!inKind(model, filters.kind)) {
    return false
  }
  const q = filters.q.toLowerCase()
  if (!q) {
    return true
  }
  return [model.manufacturer, model.model, ...model.parameters].some(t => t.toLowerCase().includes(q))
}

/** `Sensor · AT, RH`, or just `Logger`. */
export function modelLine (model: Pick<SensorModelOut, 'kind' | 'parameters'>): string {
  return [kindLabel(model.kind), model.parameters.join(', ')].filter(Boolean).join(' · ')
}

export const unitStatusLabel: Record<string, string> = {
  in_stock: 'In stock',
  installed: 'Installed',
  in_repair: 'In repair',
  retired: 'Retired',
}

/** The order the catalogue lists a model's units by status. */
const STATUS_ORDER = ['installed', 'in_stock', 'in_repair', 'retired'] as const

export function unitTotal (counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, n) => sum + n, 0)
}

/** `3 units registered`, `1 unit registered`, or `No units yet`. */
export function unitsRegistered (counts: Record<string, number>): string {
  const total = unitTotal(counts)
  if (total === 0) {
    return 'No units yet'
  }
  return `${total} ${total === 1 ? 'unit' : 'units'} registered`
}

/** `1 installed`, `1 in stock`, `1 in repair`: the statuses this model's units are in. */
export function unitBreakdown (counts: Record<string, number>): { status: string, text: string }[] {
  return STATUS_ORDER.flatMap(status => {
    const n = counts[status] ?? 0
    return n > 0 ? [{ status, text: `${n} ${(unitStatusLabel[status] ?? status).toLowerCase()}` }] : []
  })
}

/** How many models each filter would show, for the numbers on the chips. */
export function kindCounts (models: readonly Pick<SensorModelOut, 'kind'>[]): Record<KindFilter, number> {
  const counts = {} as Record<KindFilter, number>
  for (const { value } of kindFilters) {
    counts[value] = models.filter(m => inKind(m, value)).length
  }
  return counts
}

/** The one spec worth a line in the list: the first the model has. */
export function specHint (model: Pick<SensorModelOut, 'specs'>): string | null {
  const first = model.specs[0]
  return first ? first.value : null
}

/**
 * Units within calibration out of those with a due date (`ok` or `due_soon`; `overdue` is not).
 * Null when none of them has an interval, so there is nothing to measure.
 */
export function compliance (units: readonly Pick<SensorUnitOut, 'due_state'>[]): { ok: number, of: number, percent: number } | null {
  const measured = units.filter(u => u.due_state !== null)
  if (measured.length === 0) {
    return null
  }
  const ok = measured.filter(u => u.due_state !== 'overdue').length
  return { ok, of: measured.length, percent: Math.round((ok / measured.length) * 1000) / 10 }
}

/** The unit the status bar starts on: the first one that needs attention, else the first installed. */
export function firstToShow<T extends Pick<SensorUnitOut, 'due_state' | 'status'>> (units: readonly T[]): T | null {
  return units.find(u => u.due_state === 'overdue')
    ?? units.find(u => u.due_state === 'due_soon')
    ?? units.find(u => u.status === 'installed')
    ?? units[0]
    ?? null
}

/** Where a unit is: its station and parameter, or the store or lab. */
export function whereLabel (unit: { status: string, station: { name: string } | null, parameter: string | null }): string {
  if (unit.status === 'installed' && unit.station) {
    return unit.parameter ? `${unit.station.name} · ${unit.parameter}` : unit.station.name
  }
  switch (unit.status) {
    case 'in_stock': {
      return 'Store'
    }
    case 'in_repair': {
      return 'Lab'
    }
    default: {
      return '—'
    }
  }
}

/** The picture shown for a model with no photo: one icon for each kind of part. */
export function kindIcon (kind: string): string {
  switch (kind) {
    case 'sensor': {
      return mdiGauge
    }
    case 'logger': {
      return mdiMemory
    }
    case 'modem': {
      return mdiAntenna
    }
    case 'battery': {
      return mdiBatteryOutline
    }
    case 'solar_panel': {
      return mdiSolarPanel
    }
    default: {
      return mdiShapeOutline
    }
  }
}

/** The icon beside where a unit is: at a station, in the store, in the lab, or retired. */
export function whereIcon (status: string): string {
  switch (status) {
    case 'installed': {
      return mdiRadioTower
    }
    case 'in_stock': {
      return mdiWarehouse
    }
    case 'in_repair': {
      return mdiWrenchOutline
    }
    default: {
      return mdiArchiveOutline
    }
  }
}

const MS_PER_DAY = 86_400_000

/** `Last calibrated 12 Mar 2026 · Pass. Next due 15 Nov 2026 (in 42 days).` */
export function calibrationSentence (
  unit: Pick<SensorUnitOut, 'last_calibrated_at' | 'last_calibration_result' | 'calibration_due_at'>,
  now: Date = new Date(),
): string {
  const result = unit.last_calibration_result
    ? ` · ${unit.last_calibration_result.charAt(0).toUpperCase()}${unit.last_calibration_result.slice(1).replaceAll('_', ' ')}`
    : ''
  const last = unit.last_calibrated_at ? `Last calibrated ${formatDate(unit.last_calibrated_at)}${result}.` : 'Not calibrated yet.'
  if (!unit.calibration_due_at) {
    return `${last} No calibration interval is set.`
  }
  const days = Math.ceil((Date.parse(unit.calibration_due_at) - now.getTime()) / MS_PER_DAY)
  let when = 'due today'
  if (days > 0) {
    when = `in ${days} ${days === 1 ? 'day' : 'days'}`
  } else if (days < 0) {
    when = `${-days} ${days === -1 ? 'day' : 'days'} overdue`
  }
  return `${last} Next due ${formatDate(unit.calibration_due_at)} (${when}).`
}
