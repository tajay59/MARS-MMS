import type { BoardMedia, ElementKind, ElementSection } from '@/api/models'
import type { CaptureTime } from '@/offline/exif'
import { ApiError } from '@/api/problem'
import { failureOf } from './failures'
import { zonedToUtc } from './visits'

/*
  Files on the elements of a station's board (PRD VIS-5; W11-27, W11-12): the rules the upload
  queue and the element sheet share. No Vue here.
*/

export type MediaKind = BoardMedia['kind']

/** The sections an element of each kind takes files in (TRD §3.2.3). */
export const SECTIONS: Record<ElementKind, readonly ElementSection[]> = {
  note: ['main'],
  task: ['before', 'after'],
  recommendation: ['main'],
  config: ['before', 'after'],
}

export const SECTION_LABEL: Record<ElementSection, string> = {
  main: 'Photos and video',
  before: 'Before',
  after: 'After',
}

/** The reference media files an upload under; the server checks the same string (TRD §5.3). */
export function ownerRef (visitId: string, stationId: string, elementId: string, section: ElementSection): string {
  return `visit:${visitId}:station:${stationId}:element:${elementId}:${section}`
}

/**
 * Media's kind for a picked file: a photo or a video, or, where an element takes any file (Config),
 * `config` for everything else. Null when the element does not take it.
 */
export function kindOf (file: Pick<File, 'type' | 'name'>, anyFile = false): MediaKind | null {
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
  return anyFile ? 'config' : null
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

/** A section's files, oldest first. */
export function inOrder (media: readonly BoardMedia[]): BoardMedia[] {
  return media.toSorted((a, b) => (a.captured_at ?? a.added_at).localeCompare(b.captured_at ?? b.added_at))
}

const REFUSALS: Record<string, string> = {
  wrong_owner: 'That file was uploaded for something else. Add it again from here.',
  not_yours: 'That file was uploaded by someone else.',
  wrong_kind: 'Only photos and videos can go here.',
  bad_section: 'That file can’t go in this section.',
  unknown_file: 'We can’t find that upload. Choose the file again.',
  file_not_uploaded: 'The upload didn’t finish. Choose the file again.',
  caption_too_long: 'A caption can be up to 300 characters.',
  captured_in_future: 'The photo’s time is in the future. Check the phone’s clock.',
  not_editor: 'Only the person who added this, or the station’s owner, can change it.',
  element_deleted: 'This was deleted.',
  not_started: 'Start the visit first.',
  visit_cancelled: 'This visit was cancelled.',
  locked: 'The visit report has been finalized. Ask an admin to reopen it.',
}

/** The sentence for a refused add, caption, hide or remove, or null for anything unknown. */
export function mediaRefusal (code: string): string | null {
  return REFUSALS[code] ?? null
}

/** What to tell the person when a change to an element's files fails. */
export function mediaFailure (error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const known = mediaRefusal(error.code)
    if (known) {
      return known
    }
  }
  return failureOf(error, fallback).message
}
