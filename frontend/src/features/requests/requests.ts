import type { RequestAction, RequestDetail, RequestHistoryEntry, RequestStatus, RequestSummary } from '@/api/models'
import type { LocationQuery } from 'vue-router'
import { formatDate } from '@/app/format'
import { requestStatusIcons } from '@/app/theme/icons'

/*
  Requests: the list, the form and the request page (PRD REQ-1 to REQ-16; DBD "Requests list",
  "New request", "Request page"). No Vue here, so Vitest covers it directly.
*/

export const STATUSES: readonly RequestStatus[] = [
  'submitted', 'approved', 'assigned', 'scheduled', 'in_progress', 'client_review', 'reopened',
  'closed', 'denied', 'cancelled',
]

export function isStatus (value: unknown): value is RequestStatus {
  return typeof value === 'string' && (STATUSES as readonly string[]).includes(value)
}

interface Look {
  label: string
  icon: string
  /** The chip: the status colour pair (DBD Status colours), with its word and icon. */
  chip: string
  /** The timeline dot: the same pair on a round dot. */
  dot: string
}

// Whole class names, so Tailwind sees them. Submitted is outlined: new, not yet looked at.
export const statusLook: Record<RequestStatus, Look> = {
  submitted: { label: 'Submitted', icon: requestStatusIcons.submitted, chip: 'bg-status-submitted text-on-status-submitted border border-surface-500', dot: 'bg-status-submitted text-on-status-submitted border border-surface-500' },
  approved: { label: 'Approved', icon: requestStatusIcons.approved, chip: 'bg-status-approved text-on-status-approved', dot: 'bg-status-approved text-on-status-approved' },
  assigned: { label: 'Assigned', icon: requestStatusIcons.assigned, chip: 'bg-status-assigned text-on-status-assigned', dot: 'bg-status-assigned text-on-status-assigned' },
  scheduled: { label: 'Scheduled', icon: requestStatusIcons.scheduled, chip: 'bg-status-scheduled text-on-status-scheduled', dot: 'bg-status-scheduled text-on-status-scheduled' },
  in_progress: { label: 'In progress', icon: requestStatusIcons.in_progress, chip: 'bg-status-in-progress text-on-status-in-progress', dot: 'bg-status-in-progress text-on-status-in-progress' },
  client_review: { label: 'Client Review', icon: requestStatusIcons.client_review, chip: 'bg-status-client-review text-on-status-client-review', dot: 'bg-status-client-review text-on-status-client-review' },
  reopened: { label: 'Reopened', icon: requestStatusIcons.reopened, chip: 'bg-status-reopened text-on-status-reopened', dot: 'bg-status-reopened text-on-status-reopened' },
  closed: { label: 'Closed', icon: requestStatusIcons.closed, chip: 'bg-status-closed text-on-status-closed', dot: 'bg-status-closed text-on-status-closed' },
  denied: { label: 'Denied', icon: requestStatusIcons.denied, chip: 'bg-status-denied text-on-status-denied', dot: 'bg-status-denied text-on-status-denied' },
  cancelled: { label: 'Cancelled', icon: requestStatusIcons.cancelled, chip: 'bg-status-cancelled text-on-status-cancelled', dot: 'bg-status-cancelled text-on-status-cancelled' },
}

/** The look of a status from the API (a plain string there); an unknown one shows as cancelled. */
export function lookOf (status: string): Look {
  return statusLook[isStatus(status) ? status : 'cancelled']
}

export const CATEGORIES = [
  { value: 'fault', label: 'Fault' },
  { value: 'communications', label: 'Communications' },
  { value: 'power', label: 'Power' },
  { value: 'calibration', label: 'Calibration' },
  { value: 'relocation', label: 'Relocation' },
  { value: 'inspection', label: 'Inspection' },
  { value: 'other', label: 'Other' },
] as const

export const PRIORITIES = [
  { value: 'low', label: 'Low' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
] as const

export type Category = (typeof CATEGORIES)[number]['value']
export type Priority = (typeof PRIORITIES)[number]['value']

export function categoryLabel (value: string): string {
  return CATEGORIES.find(c => c.value === value)?.label ?? value
}

export function priorityLabel (value: string): string {
  return PRIORITIES.find(p => p.value === value)?.label ?? value
}

/** High and Urgent stand out in the list; Low and Normal are the usual and show only on the page. */
export function showsInList (priority: string): boolean {
  return priority === 'high' || priority === 'urgent'
}

export const priorityChip: Record<string, string> = {
  high: 'bg-warning-container text-on-warning-container',
  urgent: 'bg-error-container text-on-error-container',
  normal: 'bg-surface-100 text-surface-700',
  low: 'bg-surface-100 text-surface-700',
}

/** `JM-KIN-001`, or `JM-KIN-001 +2` for a request about several stations. */
export function stationsLabel (request: Pick<RequestSummary, 'stations'>): string {
  const [first] = request.stations
  if (!first) {
    return '—'
  }
  return request.stations.length > 1 ? `${first.code} +${request.stations.length - 1}` : first.code
}

// --- Filters, kept in the URL so a reload or a shared link keeps them (DBD "Lists") ------------

export type CreatedPreset = 'any' | '7' | '30' | 'year'

export const CREATED_PRESETS: readonly { value: CreatedPreset, label: string }[] = [
  { value: 'any', label: 'Any date' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: 'year', label: 'This year' },
]

export interface RequestFilters {
  q: string
  status: RequestStatus | null
  org: string | null
  country: string | null
  category: string | null
  priority: string | null
  created: CreatedPreset
}

function one (value: LocationQuery[string]): string | null {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' && first.trim() ? first.trim() : null
}

export function filtersFrom (query: LocationQuery): RequestFilters {
  const status = one(query.status)
  const created = one(query.created)
  const category = one(query.category)
  const priority = one(query.priority)
  return {
    q: one(query.q) ?? '',
    status: isStatus(status) ? status : null,
    org: one(query.org),
    country: one(query.country),
    category: CATEGORIES.some(c => c.value === category) ? category : null,
    priority: PRIORITIES.some(p => p.value === priority) ? priority : null,
    created: CREATED_PRESETS.some(p => p.value === created) ? created as CreatedPreset : 'any',
  }
}

/** The query for `filters`, leaving out empty ones. */
export function queryFrom (filters: RequestFilters): Record<string, string | undefined> {
  return {
    q: filters.q.trim() || undefined,
    status: filters.status ?? undefined,
    org: filters.org ?? undefined,
    country: filters.country ?? undefined,
    category: filters.category ?? undefined,
    priority: filters.priority ?? undefined,
    created: filters.created === 'any' ? undefined : filters.created,
  }
}

export function extraFilterCount (filters: RequestFilters): number {
  return [filters.org, filters.country, filters.category, filters.priority, filters.created === 'any' ? null : filters.created]
    .filter(Boolean)
    .length
}

/** The first moment a `created` preset includes. */
export function createdSince (preset: CreatedPreset, now: Date = new Date()): number | null {
  switch (preset) {
    case '7': {
      return now.getTime() - 7 * 86_400_000
    }
    case '30': {
      return now.getTime() - 30 * 86_400_000
    }
    case 'year': {
      return Date.UTC(now.getUTCFullYear(), 0, 1)
    }
    default: {
      return null
    }
  }
}

/** Every filter but status: the status options count what these leave. */
export function matchesOthers (request: RequestSummary, filters: RequestFilters, now: Date = new Date()): boolean {
  const q = filters.q.trim().toLowerCase()
  if (q) {
    const text = [request.ref, request.title, ...request.stations.map(s => s.code)].map(t => t.toLowerCase())
    if (!text.some(t => t.includes(q))) {
      return false
    }
  }
  if (filters.org && request.org_id !== filters.org) {
    return false
  }
  if (filters.country && !request.stations.some(s => s.country === filters.country)) {
    return false
  }
  if (filters.category && request.category !== filters.category) {
    return false
  }
  if (filters.priority && request.priority !== filters.priority) {
    return false
  }
  const since = createdSince(filters.created, now)
  return since === null || new Date(request.created_at).getTime() >= since
}

export function matches (request: RequestSummary, filters: RequestFilters, now: Date = new Date()): boolean {
  return (!filters.status || request.status === filters.status) && matchesOthers(request, filters, now)
}

export function facetsOf (requests: readonly RequestSummary[]): { orgs: { id: string, name: string }[], countries: string[] } {
  const orgs = new Map<string, string>()
  const countries = new Set<string>()
  for (const r of requests) {
    orgs.set(r.org_id, r.org_name ?? r.org_id)
    for (const s of r.stations) {
      countries.add(s.country)
    }
  }
  return {
    // Fresh arrays: sorting them in place is safe, and toSorted needs iOS 16
    // eslint-disable-next-line unicorn/no-array-sort
    orgs: [...orgs].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name)),
    // eslint-disable-next-line unicorn/no-array-sort
    countries: [...countries].sort(),
  }
}

// --- The request page ----------------------------------------------------------------------------

/** The seven stages of a request that runs its course, in order (PRD §5.1). */
export const STAGES: readonly RequestStatus[] = [
  'submitted', 'approved', 'assigned', 'scheduled', 'in_progress', 'client_review', 'closed',
]

export interface TimelineStep {
  status: RequestStatus
  at: string | null
  /** The request is here now. */
  current: boolean
  /** Not reached yet: drawn hollow and grey. */
  future: boolean
}

/**
 * The status timeline (DBD): each stage reached with when it was, the stages still to come as
 * hollow steps, and for a denied or cancelled request the line ends where it stopped. A stage
 * that was skipped (a request can go from Assigned to In progress with no Scheduled) is left out.
 */
export function timelineOf (history: readonly RequestHistoryEntry[], status: RequestStatus): TimelineStep[] {
  const reached = new Map<string, string>()
  for (const entry of history) {
    if (!reached.has(entry.to_status)) {
      reached.set(entry.to_status, entry.at)
    }
  }
  const ended = status === 'denied' || status === 'cancelled'
  if (ended) {
    const steps: TimelineStep[] = STAGES
      .filter(stage => reached.has(stage))
      .map(stage => ({ status: stage, at: reached.get(stage) ?? null, current: false, future: false }))
    steps.push({ status, at: reached.get(status) ?? null, current: true, future: false })
    return steps
  }
  const here = STAGES.indexOf(status)
  return STAGES
    .map((stage, index) => ({ stage, index }))
    .filter(({ stage, index }) => reached.has(stage) || index >= here)
    .map(({ stage, index }) => ({
      status: stage,
      at: reached.get(stage) ?? null,
      current: stage === status,
      future: !reached.has(stage) && index > here,
    }))
}

/** What the banner under the header says (at most one: DBD "Request page"). */
export interface Banner {
  tone: 'info' | 'error' | 'neutral'
  title: string
  body?: string
  /** A client in Client Review is offered the review page (W18, AFD J8). */
  review?: boolean
}

/** In Client Review: the client is offered the review page, staff are told who is waited for (W18). */
function reviewBanner (detail: RequestDetail, isClient: boolean): Banner {
  const closes = detail.auto_close_at ? ` on ${formatDate(detail.auto_close_at)}` : ''
  return isClient
    ? { tone: 'info', title: 'The work is done and ready for your review.', body: `If nobody at your organization answers, the request closes by itself${closes}.`, review: true }
    : { tone: 'info', title: 'Waiting for the client’s review', body: `The client was asked to review the work. If nobody answers, the request closes by itself${closes}.` }
}

/** Closed: how it was closed, when the client answered or the clock did (W18). */
function closedBanner (detail: RequestDetail): Banner | null {
  const answer = detail.verification
  if (answer?.outcome === 'auto_closed') {
    return { tone: 'info', title: `Closed automatically on ${formatDate(answer.at)}`, body: 'Nobody answered the review in time. The close-out report says so.' }
  }
  return answer?.outcome === 'accepted'
    ? { tone: 'info', title: `Closed. Accepted by ${answer.typed_name ?? answer.by?.name ?? 'the client'} on ${formatDate(answer.at)}`, body: 'The close-out report is on the Reports tab.' }
    : null
}

export function bannerFor (detail: RequestDetail, isClient: boolean): Banner | null {
  const by = (status: string) => detail.status_history.find(h => h.to_status === status)
  switch (detail.status) {
    case 'submitted': {
      return isClient
        ? { tone: 'info', title: 'Waiting for approval', body: 'We’ll tell you when an admin has looked at it. You can still change it or cancel it.' }
        : { tone: 'info', title: 'Waiting for approval', body: `Submitted by ${detail.requested_by?.name ?? 'a client'}${detail.org_name ? `, ${detail.org_name}` : ''}.` }
    }
    case 'approved': {
      return isClient
        ? { tone: 'info', title: 'Approved', body: 'It is waiting for a technician to take it on.' }
        : { tone: 'info', title: 'In the queue', body: 'Nobody has claimed this request. Assign someone, or leave it for a technician to claim.' }
    }
    case 'assigned': {
      const staff = detail.assigned_staff.map(p => p.name)
      return staff.length > 0
        ? { tone: 'info', title: isClient ? 'A technician is on it' : 'Assigned', body: `${isClient ? 'Assigned to' : 'On it:'} ${joinNames(staff)}.` }
        : null
    }
    case 'client_review': {
      return reviewBanner(detail, isClient)
    }
    case 'closed': {
      return closedBanner(detail)
    }
    case 'denied': {
      return { tone: 'error', title: `Denied${by('denied')?.by ? ` by ${by('denied')?.by?.name}` : ''}`, body: detail.denial_reason ? `Reason: ${detail.denial_reason}` : undefined }
    }
    case 'cancelled': {
      return { tone: 'neutral', title: `Cancelled${by('cancelled')?.by ? ` by ${by('cancelled')?.by?.name}` : ''}`, body: detail.cancel_reason ? `Reason: ${detail.cancel_reason}` : undefined }
    }
    default: {
      return null
    }
  }
}

/** "A", "A and B", "A, B and C". */
export function joinNames (names: readonly string[]): string {
  if (names.length <= 1) {
    return names.join('')
  }
  return `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
}

export function can (detail: Pick<RequestDetail, 'actions'>, action: RequestAction): boolean {
  return detail.actions.includes(action)
}
