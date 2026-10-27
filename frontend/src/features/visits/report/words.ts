import type { ReportSummary } from '@/api/models'

/*
  What the Report section of a visit says (W16, RPT-1, RPT-3). The words come from the report's
  own record: the PDF's state, whether it is current, and how many files it still waits for.
  No Vue here.
*/

export type ReportTone = 'working' | 'ready' | 'stale' | 'failed'

export interface ReportLook {
  tone: ReportTone
  title: string
  text: string
  /** The PDF can be opened now (it may be an older one: `stale`). */
  canOpen: boolean
  /** Preview would start a new drawing. */
  canDraw: boolean
  /** The button's words. */
  action: string
}

/** The report's version as people write it: "v1". */
export function versionText (report: Pick<ReportSummary, 'version'>): string {
  return `v${report.version}`
}

export function statusText (status: string): string {
  return status === 'draft' ? 'Draft' : status.charAt(0).toUpperCase() + status.slice(1)
}

export function look (report: ReportSummary): ReportLook {
  const { pdf } = report
  if (pdf.state === 'failed') {
    return {
      tone: 'failed',
      title: 'The PDF could not be drawn',
      text: 'Nothing is lost. Try again; if it fails twice, tell an admin.',
      canOpen: pdf.rendered_at !== null && pdf.rendered_at !== undefined,
      canDraw: true,
      action: 'Try again',
    }
  }
  if (pdf.state === 'rendering') {
    return { tone: 'working', title: 'Drawing the PDF…', text: 'This takes under a minute. You can leave this page.', canOpen: pdf.rendered_at !== null && pdf.rendered_at !== undefined, canDraw: false, action: 'Preview' }
  }
  if (pdf.state === 'none') {
    const waiting = report.awaiting_media
    return {
      tone: 'working',
      title: 'Your draft is being made',
      text: waiting > 0
        ? `Waiting for ${waiting} ${waiting === 1 ? 'file' : 'files'} to finish processing. The PDF starts by itself, after 5 minutes at most.`
        : 'The PDF starts by itself in a moment.',
      canOpen: false,
      canDraw: true,
      action: 'Preview now',
    }
  }
  if (pdf.current) {
    const pages = pdf.pages ?? 0
    return { tone: 'ready', title: 'Draft ready', text: pages > 0 ? `${pages} ${pages === 1 ? 'page' : 'pages'}. Drawn from the visit as it is now.` : 'Drawn from the visit as it is now.', canOpen: true, canDraw: false, action: 'Preview' }
  }
  return {
    tone: 'stale',
    title: 'The visit changed since this was drawn',
    text: 'Preview draws it again from the visit as it is now.',
    canOpen: true,
    canDraw: true,
    action: 'Preview',
  }
}

/** The newest version of a visit's report (the API lists newest first), or null before the draft exists. */
export function latest (reports: readonly ReportSummary[]): ReportSummary | null {
  return reports.reduce<ReportSummary | null>((best, r) => !best || r.version > best.version ? r : best, null)
}

/** Whether the section should look again soon: a draft that is still being made. */
export function isSettling (report: ReportSummary | null): boolean {
  if (!report || report.status !== 'draft') {
    return false
  }
  return report.pdf.state === 'rendering' || report.pdf.state === 'none' || report.awaiting_media > 0
}
