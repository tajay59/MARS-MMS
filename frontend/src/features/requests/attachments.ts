import { formatBytes } from '@/features/stations/documents'

/*
  PDFs on a request or a comment (PRD REQ-3, REQ-9; W9-8). No Vue here, so Vitest covers it. The
  server checks the same limits (domain/requests/comments.py): these only say so before the upload.
*/

export const MAX_FILES = 5
export const MAX_FILE_BYTES = 25 * 1024 * 1024

/** Why this file can't be attached, in words for the person; null when it can. */
export function pdfProblem (file: { name: string, size: number }): string | null {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    return 'Only PDF files can be attached.'
  }
  if (file.size === 0) {
    return 'This file is empty.'
  }
  if (file.size > MAX_FILE_BYTES) {
    return `This file is ${formatBytes(file.size)}. The most that can be attached is 25 MB.`
  }
  return null
}

export interface DraftLike {
  problem: string | null
  upload: { state: string } | null
}

/** A file is ready once media has checked it; until then Post and Submit wait (W9-8). */
export function isReady (draft: DraftLike): boolean {
  return draft.problem === null && draft.upload?.state === 'ready'
}

export function allReady (drafts: readonly DraftLike[]): boolean {
  return drafts.every(d => isReady(d))
}

/** What the chip says under the name. */
export function chipText (draft: DraftLike & { size: number, upload: { state: string, phase?: string, sent: number, total: number, waiting: string | null, error: string | null } | null }): string {
  if (draft.problem) {
    return draft.problem
  }
  const u = draft.upload
  if (!u) {
    return formatBytes(draft.size)
  }
  switch (u.state) {
    case 'ready': {
      return `${formatBytes(draft.size)} · Ready`
    }
    case 'failed': {
      return u.error ?? 'The upload did not finish.'
    }
    case 'checking': {
      return `${formatBytes(draft.size)} · Checking…`
    }
    case 'arrived': {
      return `${formatBytes(draft.size)} · Checking…`
    }
    default: {
      if (u.waiting === 'network') {
        return `${formatBytes(draft.size)} · Waiting for a connection…`
      }
      if (u.phase === 'hashing') {
        return `${formatBytes(draft.size)} · Preparing…`
      }
      const pct = u.total > 0 ? Math.min(99, Math.floor((u.sent / u.total) * 100)) : 0
      return `${formatBytes(draft.size)} · Uploading ${pct}%`
    }
  }
}

/** How long a comment can still be changed: "12 minutes left", or null when it is fixed. */
export function editLeft (until: string | null, now: Date = new Date()): string | null {
  if (!until) {
    return null
  }
  const minutes = Math.ceil((new Date(until).getTime() - now.getTime()) / 60_000)
  if (minutes <= 0) {
    return null
  }
  return minutes === 1 ? '1 minute left' : `${minutes} minutes left`
}
