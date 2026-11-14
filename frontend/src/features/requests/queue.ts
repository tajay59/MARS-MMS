import type { QueueItem } from '@/api/models'
import type { LocationQuery } from 'vue-router'
import { CATEGORIES, PRIORITIES } from './requests'

/*
  The queue and the staff picker (PRD REQ-7; AFD J4 step 4, J5 steps 1 and 2; DBD "Queue"). No
  Vue here, so Vitest covers it directly.
*/

/** One filter's options for the panel; `any` is how many requests the other filters leave */
export interface FilterGroup {
  field: 'country' | 'priority' | 'category'
  label: string
  any: number
  options: { value: string, label: string, count: number }[]
}

export interface QueueFilters {
  q: string
  country: string | null
  priority: string | null
  category: string | null
}

function one (value: LocationQuery[string]): string | null {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' && first.trim() ? first.trim() : null
}

/** The queue's filters from the URL: anything unknown is dropped. */
export function queueFiltersFrom (query: LocationQuery): QueueFilters {
  const priority = one(query.priority)
  const category = one(query.category)
  return {
    q: one(query.q) ?? '',
    country: one(query.country),
    priority: PRIORITIES.some(p => p.value === priority) ? priority : null,
    category: CATEGORIES.some(c => c.value === category) ? category : null,
  }
}

export function queueQueryFrom (filters: QueueFilters): Record<string, string | undefined> {
  return {
    q: filters.q.trim() || undefined,
    country: filters.country ?? undefined,
    priority: filters.priority ?? undefined,
    category: filters.category ?? undefined,
  }
}

function matchesQueue (item: QueueItem, filters: QueueFilters, skip: keyof QueueFilters | null = null): boolean {
  const q = filters.q.trim().toLowerCase()
  if (skip !== 'q' && q) {
    const text = [item.ref, item.title, ...item.stations.map(s => s.code)].map(t => t.toLowerCase())
    if (!text.some(t => t.includes(q))) {
      return false
    }
  }
  if (skip !== 'country' && filters.country && !item.stations.some(s => s.country === filters.country)) {
    return false
  }
  if (skip !== 'priority' && filters.priority && item.priority !== filters.priority) {
    return false
  }
  return !(skip !== 'category' && filters.category && item.category !== filters.category)
}

export function filterQueue (items: readonly QueueItem[], filters: QueueFilters): QueueItem[] {
  return items.filter(item => matchesQueue(item, filters))
}

/** Each option of one filter, counted over what the other filters leave (so the numbers add up). */
export function countBy (
  items: readonly QueueItem[], filters: QueueFilters, field: 'country' | 'priority' | 'category',
): Map<string, number> {
  const counts = new Map<string, number>()
  for (const item of items) {
    if (!matchesQueue(item, filters, field)) {
      continue
    }
    const values = field === 'country'
      ? new Set(item.stations.map(s => s.country))
      : new Set([item[field]])
    for (const value of values) {
      counts.set(value, (counts.get(value) ?? 0) + 1)
    }
  }
  return counts
}

/** How long a request has waited: "5 minutes", "5 hours", "6 days". Never 0 of anything. */
export function waitingLabel (since: string | null, now: Date = new Date()): string {
  if (!since) {
    return '—'
  }
  const minutes = Math.max(1, Math.floor((now.getTime() - new Date(since).getTime()) / 60_000))
  if (minutes < 60) {
    return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours} ${hours === 1 ? 'hour' : 'hours'}`
  }
  const days = Math.floor(hours / 24)
  return `${days} ${days === 1 ? 'day' : 'days'}`
}

// --- Choosing staff to assign ----------------------------------------------------------------

export interface StaffPerson {
  id: string
  name: string
  roles: string[]
}

export interface StaffOption extends StaffPerson {
  open: number
  chosen: boolean
}

/** Technicians and admins, once each (someone with both roles is one person), by name. */
export function assignable (users: readonly (StaffPerson & { status: string })[]): StaffPerson[] {
  const seen = new Map<string, StaffPerson>()
  for (const user of users) {
    if (user.status === 'active' && user.roles.some(r => r === 'technician' || r === 'admin')) {
      seen.set(user.id, { id: user.id, name: user.name, roles: user.roles })
    }
  }
  // Fresh array: sorting it in place is safe, and toSorted needs iOS 16
  // eslint-disable-next-line unicorn/no-array-sort
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name))
}

export function staffOptions (
  people: readonly StaffPerson[], workload: Readonly<Record<string, number>>,
  chosen: ReadonlySet<string>, search: string,
): StaffOption[] {
  const q = search.trim().toLowerCase()
  return people
    .filter(p => !q || p.name.toLowerCase().includes(q))
    .map(p => ({ ...p, open: workload[p.id] ?? 0, chosen: chosen.has(p.id) }))
}

export function openLabel (n: number): string {
  return `${n} open ${n === 1 ? 'request' : 'requests'}`
}

export function roleLabel (roles: readonly string[]): string {
  return roles.includes('admin') ? 'Admin' : 'Technician'
}

/** Same people, whatever the order: nothing to save. */
export function sameStaff (a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every(id => b.includes(id))
}
