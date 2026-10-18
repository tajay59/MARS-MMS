import type { SensorModelOut } from '@/api/models'
import type { LocationQuery } from 'vue-router'
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
export function matchesModel (model: SensorModelOut, filters: SensorFilters): boolean {
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
