import type { DownloadOut } from '@/api/models'

/*
  Ten-minute links for a model's photos (W6-12). A thumbnail in the list and the same picture in
  the gallery ask for the same link, so a link is kept in memory until just before it expires. It
  is never written to storage and never reaches the service worker (TRD §7.6); a page reload asks
  again.
*/

type Fetcher = (documentId: string) => Promise<Pick<DownloadOut, 'url' | 'expires_at'>>

interface Kept {
  url: Promise<string>
  /** ms since the epoch after which the link must be asked for again */
  until: number
}

const SPARE_MS = 60_000
const kept = new Map<string, Kept>()

/** The link for a photo: from memory while it is good, else asked for once however many ask. */
export function photoUrl (documentId: string, fetcher: Fetcher, now: number = Date.now()): Promise<string> {
  const have = kept.get(documentId)
  if (have && have.until > now) {
    return have.url
  }
  const url = fetcher(documentId).then(link => {
    const expires = Date.parse(link.expires_at)
    kept.set(documentId, { url: Promise.resolve(link.url), until: Number.isNaN(expires) ? now : expires - SPARE_MS })
    return link.url
  })
  // Until the answer is in, everyone asking shares this one request; a failure is not remembered
  kept.set(documentId, { url, until: Number.POSITIVE_INFINITY })
  url.catch(() => {
    if (kept.get(documentId)?.url === url) {
      kept.delete(documentId)
    }
  })
  return url
}

/** For a different person signing in on this device, and for tests. */
export function forgetPhotoLinks (): void {
  kept.clear()
}
