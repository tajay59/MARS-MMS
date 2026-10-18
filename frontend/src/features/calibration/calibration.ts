import type { DueUnit } from '@/api/models'
import type { LocationQuery } from 'vue-router'

/*
  The calibration due list (PRD CAL-4): every installed sensor that is overdue or due soon, overdue
  first. No Vue here, so Vitest covers it directly.
*/

export const WINDOWS = [30, 60, 90, 180] as const
export type Window = (typeof WINDOWS)[number]

export interface DueFilters {
  within: Window
  org: string | null
  country: string | null
}

function one (value: LocationQuery[string]): string | null {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' && first.trim() ? first.trim() : null
}

export function dueFiltersFrom (query: LocationQuery): DueFilters {
  const within = Number(one(query.within))
  return {
    within: (WINDOWS as readonly number[]).includes(within) ? within as Window : 30,
    org: one(query.org),
    country: one(query.country),
  }
}

export function dueQueryFrom (filters: DueFilters): Record<string, string | undefined> {
  return {
    within: filters.within === 30 ? undefined : String(filters.within),
    org: filters.org ?? undefined,
    country: filters.country ?? undefined,
  }
}

/** The organization and country filters apply here, in the page: the window is the server's. */
export function matchesDue (unit: DueUnit, filters: DueFilters): boolean {
  return (!filters.org || unit.station?.owner_org_id === filters.org)
    && (!filters.country || unit.station?.country === filters.country)
}

const DAY = 86_400_000

/** Whole days from `now` to `dueIso`; negative when it is past. */
export function daysUntil (dueIso: string, now: Date = new Date()): number {
  return Math.floor((new Date(dueIso).getTime() - now.getTime()) / DAY)
}

/** `Overdue 45 days`, `Overdue today`, `Due in 21 days`, `Due tomorrow`. */
export function dueText (dueIso: string, now: Date = new Date()): string {
  const diff = new Date(dueIso).getTime() - now.getTime()
  if (diff < 0) {
    const days = Math.floor(-diff / DAY)
    if (days < 1) {
      return 'Overdue today'
    }
    return `Overdue ${days} ${days === 1 ? 'day' : 'days'}`
  }
  const days = Math.ceil(diff / DAY)
  if (days <= 1) {
    return 'Due tomorrow'
  }
  return `Due in ${days} days`
}

/** Overdue first, longest overdue at the top; then soonest due. */
export function sortDue (units: readonly DueUnit[]): DueUnit[] {
  return units.toSorted((a, b) => a.calibration_due_at.localeCompare(b.calibration_due_at))
}

export function countDue (units: readonly DueUnit[], now: Date = new Date()): { overdue: number, soon: number } {
  const overdue = units.filter(u => new Date(u.calibration_due_at).getTime() < now.getTime()).length
  return { overdue, soon: units.length - overdue }
}
