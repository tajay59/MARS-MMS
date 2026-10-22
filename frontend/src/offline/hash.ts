/*
  SHA-256 of a file, as lowercase hex: the checksum `POST /uploads` announces and the media worker
  checks against what it stored (TRD §7.5).

  A file up to `MAX_IN_MEMORY` is hashed in one go by Web Crypto, which is native and fast. Larger
  ones (a phone video, up to 200 MB) are hashed in 8 MiB slices by `hashCore`, in a worker where
  the browser has one, so memory stays at one slice and the page stays responsive (finding F4).
*/

import { sha256Slices } from './hashCore'

export const MAX_IN_MEMORY = 16 * 1024 * 1024

export type Hasher = (file: Blob, signal?: AbortSignal) => Promise<string>

interface Answer {
  id: number
  hex?: string
  error?: string
  progress?: number
}

let nextId = 1

/** In a worker; null when the browser has none (or it cannot start), so the caller falls back. */
function inWorker (file: Blob, signal?: AbortSignal): Promise<string> | null {
  if (typeof Worker === 'undefined') {
    return null
  }
  let worker: Worker
  try {
    worker = new Worker(new URL('hash.worker.ts', import.meta.url), { type: 'module' })
  } catch {
    return null
  }
  const id = nextId++
  return new Promise<string>((resolve, reject) => {
    const stop = (): void => {
      signal?.removeEventListener('abort', onAbort)
      worker.terminate()
    }
    const onAbort = (): void => {
      stop()
      reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
    worker.addEventListener('message', (event: MessageEvent<Answer>) => {
      if (event.data.id !== id) {
        return
      }
      if (event.data.hex !== undefined) {
        stop()
        resolve(event.data.hex)
      } else if (event.data.error !== undefined) {
        stop()
        reject(new Error(event.data.error))
      }
    })
    worker.addEventListener('error', () => {
      stop()
      // A worker that cannot run (blocked, or the file's handle was lost): do it here instead
      sha256Slices(file, { signal, yieldNow }).then(resolve, reject)
    })
    worker.postMessage({ id, file })
  })
}

const yieldNow = (): Promise<void> => new Promise(resolve => setTimeout(resolve, 0))

export const sha256Hex: Hasher = async (file, signal) => {
  if (file.size <= MAX_IN_MEMORY) {
    const bytes = await file.arrayBuffer()
    signal?.throwIfAborted()
    const digest = await crypto.subtle.digest('SHA-256', bytes)
    return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('')
  }
  return inWorker(file, signal) ?? sha256Slices(file, { signal, yieldNow })
}
