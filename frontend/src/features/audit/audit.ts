import type { AuditQuery } from '@/api/audit'
import type { CheckOut } from '@/api/models'
import type { LocationQuery } from 'vue-router'
import { formatDateTime } from '@/app/format'

/*
  The audit log (PRD AUD-4, AUD-5; AFD J10; decisions W19-1, W19-4, W19-5). No Vue here, so Vitest
  covers it directly. The filters are in the address, so a link shares a search.
*/

export interface Filters {
  actor: string
  action: string
  resourceType: string
  org: string | null
  from: string
  to: string
}

export const EMPTY_FILTERS: Filters = { actor: '', action: '', resourceType: '', org: null, from: '', to: '' }

/** What the Resource filter offers: the things the trail is about. */
export const RESOURCE_TYPES: readonly { value: string, label: string }[] = [
  { value: '', label: 'Anything' },
  { value: 'request', label: 'Request' },
  { value: 'visit', label: 'Visit' },
  { value: 'station', label: 'Station' },
  { value: 'report', label: 'Report' },
  { value: 'sensor_unit', label: 'Sensor unit' },
  { value: 'user', label: 'User' },
  { value: 'organization', label: 'Organization' },
  { value: 'audit_log', label: 'Audit log' },
]

function one (value: LocationQuery[string]): string {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' ? first : ''
}

export function filtersFrom (query: LocationQuery): Filters {
  return {
    actor: one(query.actor),
    action: one(query.action),
    resourceType: one(query.rtype),
    org: one(query.org) || null,
    from: one(query.from),
    to: one(query.to),
  }
}

/** The address for `filters`, leaving out empty ones. */
export function queryFrom (filters: Filters): Record<string, string | undefined> {
  return {
    actor: filters.actor.trim() || undefined,
    action: filters.action.trim() || undefined,
    rtype: filters.resourceType || undefined,
    org: filters.org ?? undefined,
    from: filters.from || undefined,
    to: filters.to || undefined,
  }
}

export function activeCount (filters: Filters): number {
  return Object.values(queryFrom(filters)).filter(v => v !== undefined).length
}

/** A local day's start as a UTC instant, for the search window. */
function startOf (day: string): string {
  return new Date(`${day}T00:00:00`).toISOString()
}

/** The search for the server: the last day is included, so the window ends at the next midnight. */
export function toApi (filters: Filters): AuditQuery {
  const until = filters.to ? new Date(`${filters.to}T00:00:00`) : null
  until?.setDate(until.getDate() + 1)
  return {
    actor: filters.actor.trim() || undefined,
    action: filters.action.trim() || undefined,
    resource_type: filters.resourceType || undefined,
    org_id: filters.org ?? undefined,
    since: filters.from ? startOf(filters.from) : undefined,
    until: until?.toISOString(),
  }
}

export interface CheckLook {
  tone: 'info' | 'success' | 'error' | 'warning'
  title: string
  text: string
  /** A check is still going: the page looks again. */
  running: boolean
}

function when (check: CheckOut): string {
  return formatDateTime(check.finished_at ?? check.started_at ?? check.requested_at)
}

/** The banner's words for a check (decision W19-4): where it broke and nothing of the record. */
export function lookOfCheck (check: CheckOut): CheckLook {
  const who = check.requested_by_name ?? 'the nightly check'
  switch (check.status) {
    case 'passed': {
      return {
        tone: 'success', running: false, title: 'The chain is intact.',
        text: `Checked ${when(check)} by ${who}: ${check.checked.toLocaleString('en-GB')} records.`,
      }
    }
    case 'broken': {
      return {
        tone: 'error', running: false,
        title: `The chain breaks at record ${check.first_break_seq?.toLocaleString('en-GB') ?? '?'}.`,
        text: 'Records from there on cannot be trusted. Keep this page, do not restart anything, and tell whoever runs the servers.',
      }
    }
    case 'failed': {
      return { tone: 'warning', running: false, title: 'The check could not finish.', text: 'Check again. If it fails again, tell an admin.' }
    }
    default: {
      const total = check.total ?? 0
      return {
        tone: 'info', running: true, title: check.status === 'queued' ? 'Waiting to check the chain.' : 'Checking the chain.',
        text: total > 0 ? `${check.checked.toLocaleString('en-GB')} of ${total.toLocaleString('en-GB')} records.` : '',
      }
    }
  }
}

/** The start and end of a long id, as the log shows it: `0192f4a8…c31e`. */
export function shortId (id: string): string {
  return id.length > 14 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id
}

/** `Request` for `request`, `Sensor unit` for `sensor_unit`. */
export function resourceLabel (type: string | undefined | null): string {
  if (!type) {
    return '—'
  }
  const text = type.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** The role shown under a name: the most senior one. */
export function roleLabel (roles: readonly string[]): string {
  for (const name of ['admin', 'technician', 'viewer', 'client']) {
    if (roles.includes(name)) {
      return name.charAt(0).toUpperCase() + name.slice(1)
    }
  }
  return roles.length > 0 ? roles[0] ?? '' : 'System'
}

/** A value in a before-and-after table: text as it is, empty as "nothing", anything else as JSON. */
export function showValue (value: unknown): string {
  if ([null, undefined, ''].includes(value as null | undefined | string)) {
    return 'nothing'
  }
  return typeof value === 'string' ? value : JSON.stringify(value)
}

/** The day heading of a History group: `28 Oct 2026`. */
export function dayOf (iso: string | null | undefined): string {
  return iso ? formatDateTime(iso).split(',', 1)[0] ?? '' : ''
}

/** The clock of a History entry: `14:05`. */
export function clockOf (iso: string | null | undefined): string {
  const text = iso ? formatDateTime(iso) : ''
  return /(\d{2}:\d{2})/.exec(text)?.[1] ?? ''
}

/** A file name for the export, from the server's header or the day. */
export function exportName (given: string | null, now: Date = new Date()): string {
  return given ?? `audit-log-${now.toISOString().slice(0, 10).replaceAll('-', '')}.csv`
}
