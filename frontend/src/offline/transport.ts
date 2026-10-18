/*
  The browser's side of a part upload: one PUT to a presigned URL on the files host, and the state
  of the network around it. No Vue, no Pinia, no DOM beyond these globals, so the same engine can
  run from the sync runner and, later, the service worker (pwa skill: the sync core stays free of UI).

  The service worker never sees these requests: they go to another origin and the worker only
  routes the precache and navigations. The CSP allows the files host in `connect-src`.
*/

export class PartError extends Error {
  /** 0 when the request never got an answer (offline, connection reset, timeout). */
  readonly status: number
  constructor (status: number) {
    super(status === 0 ? 'No connection' : `The store answered ${status}`)
    this.name = 'PartError'
    this.status = status
  }
}

export type SendPart = (
  url: string, body: Blob, signal: AbortSignal, onProgress: (loaded: number) => void,
) => Promise<void>

/** PUT with XMLHttpRequest, because `fetch` has no upload progress. No custom headers, so the
 *  presigned signature and the CORS preflight stay as simple as they can be. */
export const sendPartXhr: SendPart = (url, body, signal, onProgress) => new Promise((resolve, reject) => {
  const xhr = new XMLHttpRequest()
  const abort = () => xhr.abort()
  signal.addEventListener('abort', abort, { once: true })
  const done = () => signal.removeEventListener('abort', abort)
  xhr.open('PUT', url)
  xhr.timeout = 5 * 60 * 1000
  xhr.upload.addEventListener('progress', e => onProgress(e.loaded))
  xhr.addEventListener('load', () => {
    done()
    if (xhr.status >= 200 && xhr.status < 300) {
      onProgress(body.size)
      resolve()
    } else {
      reject(new PartError(xhr.status))
    }
  })
  const lost = () => {
    done()
    reject(new PartError(0))
  }
  xhr.addEventListener('error', lost)
  xhr.addEventListener('timeout', lost)
  xhr.addEventListener('abort', () => {
    done()
    reject(signal.reason instanceof Error ? signal.reason : new DOMException('Aborted', 'AbortError'))
  })
  xhr.send(body)
})

export interface Network {
  /** Resolves once the app can try again: online, and (iOS suspends scripts in the background)
   *  in the foreground. Resolves at once when both already hold. */
  ready: (signal: AbortSignal) => Promise<void>
}

export const browserNetwork: Network = {
  ready (signal) {
    const usable = () => navigator.onLine && document.visibilityState !== 'hidden'
    if (usable()) {
      return Promise.resolve()
    }
    return new Promise((resolve, reject) => {
      const stop = () => {
        window.removeEventListener('online', check)
        document.removeEventListener('visibilitychange', check)
        signal.removeEventListener('abort', aborted)
      }
      const check = () => {
        if (usable()) {
          stop()
          resolve()
        }
      }
      const aborted = () => {
        stop()
        reject(signal.reason instanceof Error ? signal.reason : new DOMException('Aborted', 'AbortError'))
      }
      window.addEventListener('online', check)
      document.addEventListener('visibilitychange', check)
      signal.addEventListener('abort', aborted, { once: true })
    })
  },
}

/** One upload of one file at a time, across tabs (Web Locks). Returns null when another tab
 *  already holds it. Falls back to running unguarded where Web Locks don't exist. */
export async function withUploadLock<T> (name: string, run: () => Promise<T>): Promise<T | null> {
  if (!('locks' in navigator) || !navigator.locks) {
    return run()
  }
  return navigator.locks.request(name, { ifAvailable: true }, async lock => lock ? run() : null)
}

export function sleep (ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason instanceof Error ? signal.reason : new DOMException('Aborted', 'AbortError'))
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', aborted)
      resolve()
    }, ms)
    const aborted = () => {
      clearTimeout(timer)
      reject(signal?.reason instanceof Error ? signal.reason : new DOMException('Aborted', 'AbortError'))
    }
    signal?.addEventListener('abort', aborted, { once: true })
  })
}
