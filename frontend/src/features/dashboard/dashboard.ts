import type { AdminDashboard, ClientDashboard, Dashboard, DashboardView, RequestStatus, TechnicianDashboard } from '@/api/models'

/*
  The dashboards (PRD SUM-4 to SUM-6, CAL-4, CAL-6; DBD "Dashboards"; decision W19-7). No Vue here,
  so Vitest covers it directly.

  A tile is a number that links to a filtered list. A tile that needs action gets a coloured edge
  (amber or red) only while its number is above zero; a zero stays plain.
*/

/** The view a role lands on; an admin may also ask for the technician's. */
export function ownView (roles: readonly string[]): DashboardView {
  if (roles.includes('admin') || roles.includes('viewer')) {
    return 'admin'
  }
  return roles.includes('technician') ? 'technician' : 'client'
}

export type Tone = 'none' | 'amber' | 'red'

/** The edge of a tile: reserved for things that need someone, so a zero is never coloured. */
export function toneOf (count: number | null | undefined, tone: Exclude<Tone, 'none'>): Tone {
  return count !== null && count !== undefined && count > 0 ? tone : 'none'
}

export const toneClass: Record<Tone, string> = {
  none: 'border-l-transparent',
  amber: 'border-l-warning',
  red: 'border-l-error',
}

/** The fill of one status's bar: the status's own text colour, never a decoration colour. */
export const barFill: Record<string, string> = {
  submitted: 'bg-on-status-submitted',
  approved: 'bg-on-status-approved',
  assigned: 'bg-on-status-assigned',
  scheduled: 'bg-on-status-scheduled',
  in_progress: 'bg-on-status-in-progress',
  client_review: 'bg-on-status-client-review',
  reopened: 'bg-on-status-reopened',
}

/** The longest bar is full width; the rest are in proportion (never wider than their share). */
export function barWidths (counts: readonly { status: string, count: number }[]): Record<string, number> {
  const most = Math.max(1, ...counts.map(c => c.count))
  return Object.fromEntries(counts.map(c => [c.status, Math.round((c.count / most) * 100)]))
}

export function isAdminView (d: Dashboard): d is AdminDashboard {
  return d.view === 'admin'
}

export function isTechnicianView (d: Dashboard): d is TechnicianDashboard {
  return d.view === 'technician'
}

export function isClientView (d: Dashboard): d is ClientDashboard {
  return d.view === 'client'
}

/** Open requests a client has: every status that is not finished. */
export const OPEN_STATUSES: readonly RequestStatus[] = [
  'submitted', 'approved', 'assigned', 'scheduled', 'in_progress', 'client_review', 'reopened',
]

export function isOpen (status: string): boolean {
  return (OPEN_STATUSES as readonly string[]).includes(status)
}

/** A count for people: thousands with a comma. */
export function count (n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : n.toLocaleString('en-GB')
}

/** "3 days" or "today" for a draft waiting to be finalized. */
export function waiting (days: number): string {
  if (days <= 0) {
    return 'today'
  }
  return days === 1 ? '1 day' : `${days} days`
}
