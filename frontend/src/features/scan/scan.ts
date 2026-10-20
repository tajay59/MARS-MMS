import type { QrResolved, StationSummary } from '@/api/models'
import { ApiError, NetworkError } from '@/api/problem'

/*
  Scanning a station label (PRD QR-2 to QR-4; AFD §5.3). No Vue here, so Vitest covers it directly.

  A label holds `<app address>/s/<token>`: an opaque random token, never station data (QR-1). The
  phone's own camera opens that address; the in-app scanner reads the same text and goes to the
  same route.
*/

/** `secrets.token_urlsafe(16)` is 22 characters; the API accepts up to 64 (qr_routes.TokenPath). */
const TOKEN = /^[\w-]{1,64}$/
const SCAN_PATH = /^\/s\/([^/]+)\/?$/

/**
 * The token in a scanned text, or null when the text is not a MARS-MMS label. The host is not
 * compared: labels printed for another environment resolve to 404 ("We can't find that station"),
 * which is the honest answer, and the app only ever navigates to its own `/s/:token` route.
 */
export function tokenFromScan (text: string): string | null {
  let url: URL
  try {
    url = new URL(text.trim())
  } catch {
    return null
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    return null
  }
  const match = SCAN_PATH.exec(url.pathname)
  const token = match?.[1] ? decodeURIComponentSafe(match[1]) : null
  return token !== null && TOKEN.test(token) ? token : null
}

function decodeURIComponentSafe (value: string): string | null {
  try {
    return decodeURIComponent(value)
  } catch {
    return null
  }
}

/** What a scanned page shows (AFD §5.3). `revoked` is the one state that is not an error. */
export type LandingState = 'revoked' | 'missing' | 'offline' | 'failed'

export function landingStateFor (error: unknown): LandingState {
  if (error instanceof NetworkError) {
    return 'offline'
  }
  if (error instanceof ApiError) {
    if (error.status === 410) {
      return 'revoked'
    }
    // Another organization's station looks the same as a missing one (ADR-16); so does a token
    // the API refuses on shape (422)
    if (error.status === 404 || error.status === 422) {
      return 'missing'
    }
  }
  return 'failed'
}

/** Where a resolved label goes: the station page, for staff and for the owning client alike. */
export function stationRoute (resolved: QrResolved): { name: 'stations', params: { id: string } } {
  return { name: 'stations', params: { id: resolved.station_id } }
}

export const MAX_SUGGESTIONS = 8

/**
 * Stations whose code matches what was typed, for the "enter the station code" field. Codes that
 * start with the text come before codes that only contain it; both are sorted by code. Spaces
 * and case are ignored, since the label prints the code in capitals.
 */
export function suggestStations (stations: readonly StationSummary[], typed: string): StationSummary[] {
  const needle = typed.replaceAll(/\s+/g, '').toLowerCase()
  if (!needle) {
    return []
  }
  const starts: StationSummary[] = []
  const contains: StationSummary[] = []
  for (const station of stations) {
    const code = station.code.toLowerCase()
    if (code.startsWith(needle)) {
      starts.push(station)
    } else if (code.includes(needle)) {
      contains.push(station)
    }
  }
  const byCode = (a: StationSummary, b: StationSummary) => a.code.localeCompare(b.code)
  // Fresh arrays: sorting them in place is safe (Array.prototype.toSorted needs iOS 16)
  // eslint-disable-next-line unicorn/no-array-sort
  return [...starts.sort(byCode), ...contains.sort(byCode)].slice(0, MAX_SUGGESTIONS)
}

/** The share of the camera frame's shorter side that the guide square covers. */
export const GUIDE_SHARE = 0.7

/** The square in the middle of a frame that holds the guide: the part of the frame that is read. */
export function guideRegion (width: number, height: number): { x: number, y: number, size: number } {
  const size = Math.round(Math.min(width, height) * GUIDE_SHARE)
  return { x: Math.floor((width - size) / 2), y: Math.floor((height - size) / 2), size }
}

/** The address a label holds: the token and nothing else (QR-1). */
export function scanUrl (origin: string, token: string): string {
  return `${origin.replace(/\/+$/, '')}/s/${token}`
}

/** The end of the address, shown instead of the whole token: `host/s/…Xk3p`. */
export function shortScanUrl (origin: string, token: string): string {
  const host = origin.replace(/^https?:\/\//, '').replace(/\/+$/, '')
  return `${host}/s/…${token.slice(-4)}`
}
