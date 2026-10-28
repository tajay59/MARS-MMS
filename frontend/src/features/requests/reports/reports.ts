import type { ClientReportOut, ReportSummary, RequestDetail } from '@/api/models'
import { ApiError, NetworkError } from '@/api/problem'

/*
  What the Reports tab of a request lists (PRD RPT-8, CRP-5; AFD J8, J9; decisions W18-11, W18-12).
  No Vue here, so Vitest covers it. The three kinds of report each have their own states, and the
  words for them live here.
*/

/** A client may add a report to a request that has reached the work, and to one that is closed. */
const NO_CLIENT_REPORT = new Set(['submitted', 'denied', 'cancelled'])

/** How long after closing the page still says the close-out is being made. */
export const CLOSEOUT_WAIT_MS = 15 * 60_000

export function canAddClientReport (status: string): boolean {
  return !NO_CLIENT_REPORT.has(status)
}

export interface Closeouts {
  /** The version in force: final, the newest. */
  current: ReportSummary | null
  /** Versions a correction replaced, newest first. */
  replaced: ReportSummary[]
}

/** The close-out reports of a request: the newest final one leads, the replaced ones follow. */
export function closeoutsOf (list: readonly ReportSummary[]): Closeouts {
  const mine = list.filter(r => r.type === 'closeout' && (r.status === 'final' || r.status === 'superseded'))
  const byVersion = [...mine].toSorted((a, b) => b.version - a.version)
  return {
    current: byVersion.find(r => r.status === 'final') ?? null,
    replaced: byVersion.filter(r => r.status === 'superseded'),
  }
}

/** True while a closed request has no close-out yet and was closed only a moment ago. */
export function closeoutBeingMade (detail: Pick<RequestDetail, 'status' | 'milestones'>, closeouts: Closeouts, now: Date = new Date()): boolean {
  if (detail.status !== 'closed' || closeouts.current) {
    return false
  }
  const closed = detail.milestones.closed_at
  return !!closed && now.getTime() - new Date(closed).getTime() < CLOSEOUT_WAIT_MS
}

/** The newest version of each visit's report (the API lists newest first), by visit. */
export function visitReportsOf (list: readonly ReportSummary[]): ReportSummary[] {
  const best = new Map<string, ReportSummary>()
  for (const r of list) {
    if (r.type !== 'visit' || !r.visit_id) {
      continue
    }
    const held = best.get(r.visit_id)
    if (!held || r.version > held.version) {
      best.set(r.visit_id, r)
    }
  }
  return [...best.values()].toSorted((a, b) => a.number.localeCompare(b.number))
}

export type ClientReportLook = 'draft' | 'file' | 'making' | 'ready' | 'failed'

/** Where a client report stands, for the chip and the button. */
export function clientReportLook (report: Pick<ClientReportOut, 'status' | 'kind' | 'render'>): ClientReportLook {
  if (report.status === 'draft') {
    return 'draft'
  }
  if (report.kind === 'pdf') {
    return 'file'
  }
  switch (report.render) {
    case 'ready': {
      return 'ready'
    }
    case 'failed': {
      return 'failed'
    }
    default: {
      return 'making'
    }
  }
}

export function kindLabel (kind: ClientReportOut['kind']): string {
  return kind === 'form' ? 'Online form' : 'PDF'
}

/** The words under a client report's title: the date, who sent it, and where it stands. */
export function clientReportSub (report: Pick<ClientReportOut, 'status' | 'report_date' | 'submitted_by' | 'can_edit'>, date: (iso: string) => string): string {
  const day = date(report.report_date)
  if (report.status === 'draft') {
    return `${day} · not sent yet`
  }
  return `${day} · ${report.submitted_by?.name ?? 'a client'}`
}

/** The Reports tab should look again soon: a PDF is being made, or the close-out is. */
export function isSettling (reports: readonly ClientReportOut[], pending: boolean): boolean {
  return pending || reports.some(r => clientReportLook(r) === 'making')
}

/** What a failed request for a report's link says. */
export function linkProblem (error: unknown): string {
  if (error instanceof NetworkError) {
    return 'Needs a connection. Try again with signal.'
  }
  if (error instanceof ApiError) {
    if (error.code === 'no_pdf' || error.code === 'not_ready') {
      return 'The PDF is still being made. Try again in a minute.'
    }
    if (error.status === 404) {
      return 'This report could not be found. It may have been replaced.'
    }
  }
  return 'The report could not be opened. Try again.'
}
