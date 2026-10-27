import type { ReportOut, ReportSignature } from '@/api/models'

/*
  What the report editor shows and who may do what (W17, RPT-2, RPT-4 to RPT-6; boards 4 to 6 of
  the W16 sheet and the W17 sheet). The server decides every rule again; these only decide which
  buttons to offer, in words from the plan. No Vue here.
*/

/** Photos that print in one station's body; the rest go in the appendix (TRD 11.1). */
export const BODY_LIMIT = 6

export interface Item { id: string, text: string, done: boolean }
export interface Media { media_id: string, kind: string, filename: string, caption?: string | null }
export interface Element {
  id: string
  kind: 'task' | 'note' | 'recommendation' | 'config'
  title: string
  description?: string | null
  items: Item[]
  priority?: string | null
  shared: boolean
  request_ref?: string | null
  config_versions: { version?: number | null }[]
  media: Record<string, Media[]>
}
export interface Station { station_id: string, code: string, name: string, time_zone?: string | null, elements: Element[] }
export interface Selection { station_id: string, element_id: string, section: string, media_id: string, caption?: string | null, in_body: boolean }
export interface Narrative {
  summary: string
  recommendations: string
  follow_up: string
  stations: { station_id: string, work_performed: string }[]
}
export interface Content {
  facts: { visit: { staff: { id: string, name: string }[], lead_staff_id: string, request_ref?: string | null, request_title?: string | null }, stations: Station[] }
  narrative: Narrative
  media_selection: Selection[]
}

/** The report's content, or null while the draft is still being prepared. */
export function contentOf (report: Pick<ReportOut, 'content'>): Content | null {
  const content = report.content as Partial<Content>
  return content.facts && content.narrative ? content as Content : null
}

// --- who may do what ---

export interface Who { id: string, isAdmin: boolean }

export function attended (report: Pick<ReportOut, 'staff_ids'>, who: Who): boolean {
  return report.staff_ids.includes(who.id)
}

export function isLead (report: Pick<ReportOut, 'lead_staff_id'>, who: Who): boolean {
  return report.lead_staff_id === who.id
}

/** Attending staff and admins edit a draft. */
export function mayEdit (report: Pick<ReportOut, 'status' | 'staff_ids'>, who: Who): boolean {
  return report.status === 'draft' && (who.isAdmin || attended(report, who))
}

export function validSignatures (report: Pick<ReportOut, 'signatures'>): ReportSignature[] {
  return report.signatures.filter(s => s.valid)
}

export function mySignature (report: Pick<ReportOut, 'signatures'>, who: Who): ReportSignature | undefined {
  return validSignatures(report).find(s => s.signer_id === who.id)
}

/** Only people who attended sign, and once each (W17-5). */
export function maySign (report: Pick<ReportOut, 'status' | 'staff_ids' | 'signatures'>, who: Who): boolean {
  return report.status === 'draft' && attended(report, who) && !mySignature(report, who)
}

export function leadSigned (report: Pick<ReportOut, 'signatures' | 'lead_staff_id'>): boolean {
  return validSignatures(report).some(s => s.signer_id === report.lead_staff_id)
}

/** The lead or an admin, once the lead has signed this version. */
export function mayFinalize (report: Pick<ReportOut, 'status' | 'signatures' | 'lead_staff_id'>, who: Who): boolean {
  return report.status === 'draft' && leadSigned(report) && (who.isAdmin || isLead(report, who))
}

/** An admin reopens a final report that nothing has replaced. */
export function mayReopen (report: Pick<ReportOut, 'status'>, who: Who): boolean {
  return report.status === 'final' && who.isAdmin
}

// --- the board, as the report sees it ---

export interface Fact {
  id: string
  station: string
  kind: Element['kind']
  title: string
  line: string
  /** Prints in the report. A staff-only element does not (W17-1). */
  printed: boolean
}

const KIND_WORDS: Record<Element['kind'], string> = { task: 'Task', note: 'Note', recommendation: 'Recommendation', config: 'Config' }

function mediaCount (element: Element): number {
  return Object.values(element.media).reduce((sum, list) => sum + list.length, 0)
}

function line (element: Element): string {
  const parts: string[] = [KIND_WORDS[element.kind], element.shared ? 'shared' : 'staff only']
  if (element.kind === 'task' && element.items.length > 0) {
    const done = element.items.filter(i => i.done).length
    parts.push(`${done} of ${element.items.length} items done`)
    if (done < element.items.length) {
      parts.push('not finished')
    }
  }
  if (element.kind === 'recommendation' && element.priority) {
    parts.push(element.priority)
  }
  if (element.kind === 'config' && element.config_versions.length > 0) {
    parts.push(`version ${element.config_versions.map(v => v.version).join(', ')}`)
  }
  const files = mediaCount(element)
  if (files > 0) {
    parts.push(`${files} ${files === 1 ? 'file' : 'files'}`)
  }
  return parts.join(' · ')
}

/** Every element of the visit's boards with whether it prints, shared ones first within a station. */
export function factsOf (content: Content): Fact[] {
  return content.facts.stations.flatMap(station => station.elements.map(e => ({
    id: e.id,
    station: station.code,
    kind: e.kind,
    title: e.title,
    line: line(e),
    printed: e.shared,
  })))
}

export interface Photo {
  mediaId: string
  stationId: string
  filename: string
  /** The caption in this report (it starts as the board's and changes here only). */
  caption: string
  inBody: boolean
}

export interface PhotoGroup { stationId: string, code: string, photos: Photo[], inBody: number, full: boolean }

/** The photos that can print, by station, with how many of the body's six are used. */
export function photoGroups (content: Content): PhotoGroup[] {
  const names = new Map<string, string>()
  for (const station of content.facts.stations) {
    for (const element of station.elements) {
      for (const list of Object.values(element.media)) {
        for (const m of list) {
          names.set(m.media_id, m.filename)
        }
      }
    }
  }
  return content.facts.stations.flatMap(station => {
    const photos = content.media_selection
      .filter(s => s.station_id === station.station_id)
      .map(s => ({
        mediaId: s.media_id,
        stationId: s.station_id,
        filename: names.get(s.media_id) ?? 'Photo',
        caption: s.caption ?? '',
        inBody: s.in_body,
      }))
    if (photos.length === 0) {
      return []
    }
    const inBody = photos.filter(p => p.inBody).length
    return [{ stationId: station.station_id, code: station.code, photos, inBody, full: inBody >= BODY_LIMIT }]
  })
}

// --- words ---

/** Why a signature no longer counts, as the person reads it. `cleared_by` is a person's id, `facts` or `reopen`. */
export function clearedBecause (sig: Pick<ReportSignature, 'cleared_by'>, people: Record<string, string>): string {
  if (sig.cleared_by === 'facts') {
    return 'a fact changed on the board'
  }
  if (sig.cleared_by === 'reopen') {
    return 'the report was reopened'
  }
  const name = sig.cleared_by ? people[sig.cleared_by] : undefined
  return name ? `report edited by ${name}` : 'the report was edited'
}

/** What the page says when a finalize stopped (`finalize_error` on the draft). */
export function stoppedWords (error: string | null | undefined): { title: string, text: string, tone: 'warning' | 'error' } | null {
  switch (error) {
    case 'facts_changed': {
      return { title: 'Finalizing stopped because the board changed.', text: 'A fact on the board changed after you started, so the signatures were cleared. Read the changes in the report, then sign and finalize again.', tone: 'warning' }
    }
    case 'lock_failed': {
      return { title: 'The visit’s boards could not be locked.', text: 'Nothing changed and your signatures are kept. Try again in a minute.', tone: 'error' }
    }
    case 'render_failed': {
      return { title: 'The PDF couldn’t be made.', text: 'Your signatures are kept and the boards are open again. Try again; if it fails twice, tell an admin.', tone: 'error' }
    }
    default: {
      return null
    }
  }
}

export function statusLabel (report: Pick<ReportOut, 'status' | 'version'>): string {
  const word = { draft: 'Draft', finalizing: 'Finalizing', final: 'Final', superseded: 'Superseded' }[report.status] ?? report.status
  return `${word} v${report.version}`
}
