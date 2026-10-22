import type { MediaDetail } from '@/api/models'
import { mediaApi } from '@/api/media'

/*
  What the media service says about a photo or video on a visit: where it is in its checks and,
  once it is ready, ten-minute links to its thumbnail and its picture (W11-10, W11-11). A thumbnail
  in a strip and the same file in a menu ask for the same record, so a ready one is kept in memory
  for less than the links last. Nothing is written to storage and nothing reaches the service
  worker (TRD §7.6); a page reload asks again. No Vue here.
*/

type Fetcher = (id: string) => Promise<MediaDetail>

/** Links last ten minutes; ask again well before. */
const KEEP_MS = 8 * 60_000

/** Still on its way to `ready`: look again in a moment. */
const ON_ITS_WAY = new Set(['pending', 'uploaded', 'processing'])

interface Kept {
  detail: Promise<MediaDetail>
  /** ms since the epoch after which it must be asked for again */
  until: number
}

const kept = new Map<string, Kept>()

export function onItsWay (status: string): boolean {
  return ON_ITS_WAY.has(status)
}

/** The record for a file: from memory while its links are good, else asked for once however many ask. */
export function mediaDetail (id: string, fetcher: Fetcher = mediaApi.get, now: number = Date.now()): Promise<MediaDetail> {
  const have = kept.get(id)
  if (have && have.until > now) {
    return have.detail
  }
  const detail = fetcher(id).then(found => {
    // Only a ready file has links worth keeping; one still being checked is asked for again
    if (kept.get(id)?.detail === detail) {
      if (found.status === 'ready') {
        kept.set(id, { detail: Promise.resolve(found), until: now + KEEP_MS })
      } else {
        kept.delete(id)
      }
    }
    return found
  })
  kept.set(id, { detail, until: Number.POSITIVE_INFINITY })
  detail.catch(() => {
    if (kept.get(id)?.detail === detail) {
      kept.delete(id)
    }
  })
  return detail
}

/** A file was removed or replaced: its record is stale. */
export function forgetMedia (id: string): void {
  kept.delete(id)
}

/** For a different person signing in on this device, and for tests. */
export function forgetMediaLinks (): void {
  kept.clear()
}

/**
 * Show a photo or video in a new tab. The tab is opened in the click itself because Safari refuses
 * a window opened after an `await`; the link is asked for fresh, since the one in a thumbnail may
 * be old.
 */
export async function openMedia (id: string, fetcher: Fetcher = mediaApi.get): Promise<void> {
  const tab = globalThis.open('', '_blank')
  try {
    const detail = await fetcher(id)
    const url = detail.urls?.view
    if (!url) {
      throw new Error('not_ready')
    }
    if (tab) {
      tab.opener = null
      tab.location.href = url
    } else {
      globalThis.location.assign(url)
    }
  } catch (error) {
    tab?.close()
    throw error
  }
}

/** m:ss for a clip, from its length in seconds. */
export function clock (seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return ''
  }
  const whole = Math.round(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}
