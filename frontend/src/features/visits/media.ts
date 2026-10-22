import type { VisitMedia, VisitOut } from '@/api/models'
import type { CaptureTime } from '@/offline/exif'
import { ApiError } from '@/api/problem'
import { failureOf } from './failures'
import { zonedToUtc } from './visits'

/*
  Photos and video on a visit (PRD VIS-5; W11-10, W11-12): the rules the strip and its add button
  share. No Vue here.
*/

export type Phase = VisitMedia['phase']
export type MediaKind = VisitMedia['kind']

export const PHASES: readonly Phase[] = ['before', 'during', 'after']

export const PHASE_LABEL: Record<Phase, string> = {
  before: 'Before',
  during: 'During',
  after: 'After',
}

/** The reference media files an upload under; the server checks the same string (TRD §5.3). */
export function ownerRef (visitId: string, stationId: string, phase: Phase): string {
  return `visit:${visitId}:station:${stationId}:${phase}`
}

/** Media's kind for a picked file, or null when it is neither a photo nor a video. */
export function kindOf (file: Pick<File, 'type' | 'name'>): MediaKind | null {
  if (file.type.startsWith('image/')) {
    return 'image'
  }
  if (file.type.startsWith('video/')) {
    return 'video'
  }
  // Some Android file pickers leave the type empty
  const extension = file.name.toLowerCase().split('.').pop() ?? ''
  if (['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif'].includes(extension)) {
    return 'image'
  }
  if (['mp4', 'mov', 'm4v', 'webm', '3gp'].includes(extension)) {
    return 'video'
  }
  return null
}

const DAY = 24 * 60 * 60 * 1000

/**
 * When the picture was taken, as the UTC instant the server stores (rule 8). A camera writes local
 * time with no zone and, on newer phones, its offset; without the offset the station's zone is
 * the best guess. A video or a screenshot has no EXIF, so the file's modified time stands in. A
 * time more than a day ahead of the clock is a mistake and is left out.
 */
export function capturedAt (
  file: Pick<File, 'lastModified'>, exif: CaptureTime | null, zone: string | null | undefined, now: Date = new Date(),
): string | null {
  let at: number | null = null
  if (exif) {
    at = exif.offset
      ? Date.parse(`${exif.local}${exif.offset}`)
      : (zone ? Date.parse(zonedToUtc(exif.local.slice(0, 16), zone) ?? '') : Number.NaN)
  }
  if (at === null || Number.isNaN(at)) {
    at = file.lastModified > 0 ? file.lastModified : null
  }
  if (at === null || at > now.getTime() + DAY) {
    return null
  }
  return new Date(at).toISOString()
}

export interface StationMediaView {
  phase: Phase
  items: VisitMedia[]
}

/** A station's media grouped by phase, oldest first within a phase, every phase present. */
export function byPhase (media: readonly VisitMedia[]): StationMediaView[] {
  return PHASES.map(phase => ({
    phase,
    items: media
      .filter(m => m.phase === phase)
      .toSorted((a, b) => (a.captured_at ?? a.added_at).localeCompare(b.captured_at ?? b.added_at)),
  }))
}

export function stationMedia (visit: Pick<VisitOut, 'stations'>, stationId: string): VisitMedia[] {
  return visit.stations.find(s => s.station_id === stationId)?.media ?? []
}

/** What the person may do with the strip, from the visit and the station (the server decides again). */
export function canAddMedia (visit: Pick<VisitOut, 'status' | 'actions' | 'staff'>, userId: string, isAdmin: boolean): boolean {
  if (visit.status !== 'started' && visit.status !== 'ended') {
    return false
  }
  return isAdmin || visit.staff.some(p => p.id === userId)
}

export function canRemoveMedia (item: Pick<VisitMedia, 'added_by'>, userId: string, isAdmin: boolean): boolean {
  return isAdmin || item.added_by.id === userId
}

const REFUSALS: Record<string, string> = {
  wrong_owner: 'That file was uploaded for another station or phase. Add it again from here.',
  not_yours: 'That file was uploaded by someone else.',
  wrong_kind: 'Only photos and videos can go on a visit.',
  unknown_file: 'We can’t find that upload. Choose the file again.',
  file_not_uploaded: 'The upload didn’t finish. Choose the file again.',
  caption_too_long: 'A caption can be up to 300 characters.',
  captured_in_future: 'The photo’s time is in the future. Check the phone’s clock.',
  not_attending: 'Only the people attending this visit can add photos.',
  not_uploader: 'Only the person who added it, or an admin, can remove it.',
  not_started: 'Start the visit first.',
  visit_cancelled: 'This visit was cancelled.',
  locked: 'The visit report has been finalized. Ask an admin to reopen it.',
}

/** The sentence for a refused add, caption, hide or remove, or null for anything unknown. */
export function mediaRefusal (code: string): string | null {
  return REFUSALS[code] ?? null
}

/** What to tell the person when a change to a station's media fails. */
export function mediaFailure (error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const known = mediaRefusal(error.code)
    if (known) {
      return known
    }
  }
  return failureOf(error, fallback).message
}
