import type { JobOut, StationSummary } from '@/api/models'

/*
  The label tool (PRD QR-6; DBD "Admin"). The sheet is drawn on the server; this file holds the
  rules the page shows before asking (pages, limits, the phone) and the polling of the job.
  No Vue here, so Vitest covers it directly.
*/

export const PER_PAGE = 10 // 2 x 5 labels of 98 x 55 mm on A4 (W7-4; report/domain/labels.py)
export const MAX_STATIONS = 200 // 20 pages; the same limit as the report service's

const PHONE = /^[+(]?\d[\d ()-]{3,28}\d$/

export function pagesFor (count: number): number {
  return Math.ceil(count / PER_PAGE)
}

/** `1 page · 10 labels to a page`. */
export function sheetNote (count: number): string {
  const pages = pagesFor(count)
  return `${pages} ${pages === 1 ? 'page' : 'pages'} · ${PER_PAGE} labels to a page · 98 × 55 mm`
}

/** An error for the contact phone, or null when it is empty or fine (the server checks it again). */
export function phoneProblem (value: string): string | null {
  const phone = value.trim()
  if (!phone) {
    return null
  }
  if (phone.length > 30 || !PHONE.test(phone)) {
    return 'Use digits, spaces, brackets and dashes, for example +1 876 555 0100'
  }
  return null
}

/** The stations the picker lists for a search and a country, by code. */
export function pickable (stations: readonly StationSummary[], search: string, country: string | null): StationSummary[] {
  const q = search.trim().toLowerCase()
  return stations.filter(s =>
    (!country || s.country === country)
    && (!q || s.code.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)),
  )
}

export function isFinished (job: JobOut): boolean {
  return job.status === 'done' || job.status === 'failed'
}

export interface PollOptions {
  /** Wait between asks, in ms; the last value repeats. */
  delays?: readonly number[]
  /** Give up after this many asks (the job stays on the server). */
  maxAsks?: number
  signal?: AbortSignal
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>
}

export class PollGaveUp extends Error {
  constructor () {
    super('The label sheet is taking longer than usual')
    this.name = 'PollGaveUp'
  }
}

function wait (ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason as Error)
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    function onAbort (): void {
      clearTimeout(timer)
      reject(signal?.reason as Error)
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

/** Asks for the job until it is done or has failed. A failed ask (a dropped connection) is asked
    again; only the caller's abort and running out of asks end the polling early. */
export async function pollJob (
  ask: (id: string, signal?: AbortSignal) => Promise<JobOut>,
  id: string,
  options: PollOptions = {},
): Promise<JobOut> {
  const { delays = [800, 1500, 2500], maxAsks = 60, signal, sleep = wait } = options
  for (let n = 0; n < maxAsks; n++) {
    try {
      const job = await ask(id, signal)
      if (isFinished(job)) {
        return job
      }
    } catch (error) {
      if (signal?.aborted) {
        throw error
      }
    }
    await sleep(delays[Math.min(n, delays.length - 1)] ?? 2500, signal)
  }
  throw new PollGaveUp()
}
