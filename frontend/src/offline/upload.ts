/*
  Resumable uploads of one file to the files host (TRD §3.3, §7.3; PRD OFF-6).

      hash → POST /uploads → PUT the missing 8 MiB parts → POST /uploads/{id}/complete → poll

  The store is the truth about which parts have arrived: after any failure the engine asks
  `POST /uploads/{id}/parts` and carries on from what the store holds, so a dropped connection, a
  closed tab or a lost response never starts a file over and never duplicates one. Every step is
  safe to repeat: `create` and `complete` are idempotent on the server, and a part sent twice
  replaces itself.

  Where it stands today (Phase 2, W6): staff upload documents and configuration files from a desk,
  online. Nothing is written to IndexedDB, so a reload loses the `File` handle: the person picks the
  file again, and the server joins it to the open upload by size and checksum (`resumed: true`).
  Phase 5 (offline visits) keeps the blob in Dexie and drives this same engine from the outbox, so
  it takes everything from `UploadDeps` and imports no Vue, Pinia or router.

  iOS suspends scripts in the background: a part that fails while the page is hidden waits for it
  to come back (`Network.ready`) instead of burning its retries.
*/

import type { MediaDetail, UploadIn, UploadOut } from '@/api/models'
import { ApiError, NetworkError } from '@/api/problem'
import { newId } from '@/app/ids'
import { type Hasher, sha256Hex } from './hash'
import { browserNetwork, type Network, PartError, type SendPart, sendPartXhr, sleep, withUploadLock } from './transport'

export interface UploadApi {
  create: (body: UploadIn, signal?: AbortSignal) => Promise<UploadOut>
  parts: (mediaId: string, signal?: AbortSignal) => Promise<UploadOut>
  complete: (mediaId: string, signal?: AbortSignal) => Promise<UploadOut>
  get: (mediaId: string, signal?: AbortSignal) => Promise<MediaDetail>
}

export type Phase = 'hashing' | 'starting' | 'sending' | 'finishing' | 'checking' | 'done'

export interface Progress {
  phase: Phase
  /** Bytes of the file the store holds, plus those on their way */
  sent: number
  total: number
  /** Known after `POST /uploads`; can differ from the one asked for when an open upload was joined */
  mediaId: string | null
  /** Why nothing is moving: no connection or page hidden, or backing off after an error */
  waiting: 'network' | 'retry' | null
}

/** `failed`: the file can't be uploaded as it is (`reason` says why); `stalled`: out of retries,
 *  trying again from the start is safe; `busy`: another tab is already uploading this file. */
export class UploadError extends Error {
  readonly kind: 'failed' | 'stalled' | 'busy'
  readonly reason: string | undefined
  constructor (kind: UploadError['kind'], message: string, reason?: string) {
    super(message)
    this.name = 'UploadError'
    this.kind = kind
    this.reason = reason
  }
}

export interface UploadDeps {
  api: UploadApi
  hash?: Hasher
  sendPart?: SendPart
  network?: Network
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>
  random?: () => number
  newId?: () => string
  lock?: <T>(name: string, run: () => Promise<T>) => Promise<T | null>
  /** Parts in flight at once. Each is 8 MiB, so three keeps an iPhone's memory in check. */
  concurrency?: number
  /** Tries per part (and per API call) before `stalled` */
  attempts?: number
  /** Give up waiting for the checks after this long */
  checkTimeoutMs?: number
}

export interface UploadRequest {
  file: File
  ownerRef: string
  kind: string
  /** Re-use the ID of an earlier try, so the server finds the same upload */
  mediaId?: string
}

const BACKOFF_BASE_MS = 1000
const BACKOFF_CAP_MS = 30_000

type Resolved = Required<Omit<UploadDeps, 'api'>> & { api: UploadApi }

function resolve (deps: UploadDeps): Resolved {
  return {
    api: deps.api,
    hash: deps.hash ?? sha256Hex,
    sendPart: deps.sendPart ?? sendPartXhr,
    network: deps.network ?? browserNetwork,
    sleep: deps.sleep ?? sleep,
    random: deps.random ?? Math.random,
    newId: deps.newId ?? newId,
    lock: deps.lock ?? withUploadLock,
    concurrency: deps.concurrency ?? 3,
    attempts: deps.attempts ?? 8,
    checkTimeoutMs: deps.checkTimeoutMs ?? 5 * 60 * 1000,
  }
}

function isAbort (error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

/** Full jitter: a random wait up to the backoff, never under a quarter second. */
function backoff (d: Resolved, attempt: number): number {
  return Math.max(250, Math.floor(d.random() * Math.min(BACKOFF_CAP_MS, BACKOFF_BASE_MS * 2 ** attempt)))
}

/** An API call that rides out a bad connection or a busy server (5xx), and no more: a 4xx is
 *  an answer, and goes to the caller. */
async function retrying<T> (d: Resolved, signal: AbortSignal, onWait: (w: Progress['waiting']) => void, call: () => Promise<T>): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await call()
    } catch (error) {
      const transient = error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)
      if (!transient || attempt + 1 >= d.attempts) {
        if (transient) {
          throw new UploadError('stalled', 'The connection kept failing')
        }
        throw error
      }
      onWait('network')
      await d.network.ready(signal)
      onWait('retry')
      await d.sleep(backoff(d, attempt), signal)
      onWait(null)
    }
  }
}

/**
 * Upload `request.file` until the server holds it whole (status `uploaded` or later), resuming
 * wherever an earlier try stopped. Resolves with the server's last answer. The checks (size,
 * type, checksum, virus scan) come after: see `waitUntilChecked`.
 */
export async function uploadFile (
  request: UploadRequest,
  deps: UploadDeps,
  signal: AbortSignal,
  onProgress: (p: Progress) => void = () => {},
): Promise<UploadOut> {
  const d = resolve(deps)
  const total = request.file.size
  const progress: Progress = { phase: 'hashing', sent: 0, total, mediaId: null, waiting: null }
  const emit = (change: Partial<Progress> = {}) => {
    Object.assign(progress, change)
    onProgress({ ...progress })
  }
  const wait = (waiting: Progress['waiting']) => emit({ waiting })
  emit()

  const sha256 = await d.hash(request.file, signal)
  const ran = await d.lock(`mms-upload:${request.ownerRef}:${sha256}`, async () => {
    emit({ phase: 'starting' })
    let state = await retrying(d, signal, wait, () => d.api.create({
      media_id: request.mediaId ?? d.newId(),
      owner_ref: request.ownerRef,
      kind: request.kind,
      filename: request.file.name,
      size_bytes: total,
      sha256,
    }, signal))
    emit({ mediaId: state.media_id })

    for (let round = 0; round < 6; round++) {
      if (state.status !== 'pending') {
        break
      }
      emit({ phase: 'sending' })
      await sendMissing(d, state, request.file, signal, emit, wait)
      emit({ phase: 'finishing', sent: total })
      try {
        state = await retrying(d, signal, wait, () => d.api.complete(state.media_id, signal))
        break
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          if (error.reason === 'incomplete_upload') {
            // Some parts never arrived: ask the store which, and send those
            state = await retrying(d, signal, wait, () => d.api.parts(state.media_id, signal))
            continue
          }
          throw new UploadError('failed', error.detail, error.reason)
        }
        throw error
      }
    }
    if (state.status === 'pending') {
      throw new UploadError('stalled', 'The upload did not finish')
    }
    emit({ phase: 'done', sent: total })
    return state
  })
  if (ran === null) {
    throw new UploadError('busy', 'This file is already being uploaded in another tab')
  }
  return ran
}

async function sendMissing (
  d: Resolved, state: UploadOut, file: File, signal: AbortSignal,
  emit: (change?: Partial<Progress>) => void, wait: (w: Progress['waiting']) => void,
): Promise<void> {
  const size = state.part_size
  const partBytes = (n: number) => (n < state.part_count ? size : file.size - size * (state.part_count - 1))
  const urls = new Map(state.urls.map(u => [u.part_number, u.url]))
  const stored = new Set(state.parts_done)
  const inFlight = new Map<number, number>()
  const report = () => {
    let sent = 0
    for (const n of stored) {
      sent += partBytes(n)
    }
    for (const loaded of inFlight.values()) {
      sent += loaded
    }
    emit({ sent: Math.min(sent, file.size) })
  }
  report()

  // One refresh at a time, whichever parts ask: URLs last an hour, and a slow link can outlast them
  let refreshing: Promise<void> | null = null
  const refresh = () => {
    refreshing ??= (async () => {
      try {
        const fresh = await retrying(d, signal, wait, () => d.api.parts(state.media_id, signal))
        for (const n of fresh.parts_done) {
          stored.add(n)
        }
        for (const u of fresh.urls) {
          urls.set(u.part_number, u.url)
        }
      } finally {
        refreshing = null
      }
    })()
    return refreshing
  }

  const todo = [...urls.keys()].filter(n => !stored.has(n)).toSorted((a, b) => a - b)
  async function sendOne (n: number): Promise<void> {
    for (let attempt = 0; ; attempt++) {
      if (stored.has(n)) {
        return
      }
      const url = urls.get(n)
      try {
        if (!url) {
          throw new PartError(403) // no URL: ask for fresh ones
        }
        const start = (n - 1) * size
        await d.sendPart(url, file.slice(start, start + partBytes(n)), signal, loaded => {
          inFlight.set(n, loaded)
          report()
        })
        inFlight.delete(n)
        stored.add(n)
        report()
        return
      } catch (error) {
        inFlight.delete(n)
        if (isAbort(error) || signal.aborted) {
          throw error
        }
        if (!(error instanceof PartError)) {
          throw error
        }
        if (error.status === 403 || error.status === 401) {
          // Expired or refused signature: fresh URLs, and the store may already have this part
          await refresh()
        } else if (error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429) {
          throw new UploadError('failed', 'The store refused the file', 'store_refused')
        }
        if (attempt + 1 >= d.attempts) {
          throw new UploadError('stalled', 'The connection kept failing')
        }
        wait('network')
        await d.network.ready(signal)
        wait('retry')
        await d.sleep(backoff(d, attempt), signal)
        wait(null)
      }
    }
  }

  let next = 0
  const workers = Array.from({ length: Math.min(d.concurrency, todo.length) }, async () => {
    while (next < todo.length) {
      const n = todo[next++]
      if (n !== undefined) {
        await sendOne(n)
      }
    }
  })
  // The first failure stops the others from starting new parts (those in flight finish)
  await Promise.all(workers.map(w => w.catch((error: unknown) => {
    next = todo.length
    throw error
  })))
}

/**
 * Wait for media's checks on a file the server holds (size, type, checksum, virus scan). Resolves
 * with the file's record when it is `ready`, and throws `failed` with the reason when it is not
 * (`infected`, `checksum_mismatch`, `bad_type`...). Normally a few seconds.
 */
export async function waitUntilChecked (
  mediaId: string,
  deps: UploadDeps,
  signal: AbortSignal,
  onProgress: (p: Progress) => void = () => {},
): Promise<MediaDetail> {
  const d = resolve(deps)
  const started = Date.now()
  const progress: Progress = { phase: 'checking', sent: 0, total: 0, mediaId, waiting: null }
  onProgress({ ...progress })
  for (let i = 0; ; i++) {
    let detail: MediaDetail
    try {
      detail = await d.api.get(mediaId, signal)
    } catch (error) {
      if (!(error instanceof NetworkError || (error instanceof ApiError && error.status >= 500))) {
        throw error
      }
      await d.network.ready(signal)
      await d.sleep(backoff(d, Math.min(i, 4)), signal)
      continue
    }
    if (detail.status === 'ready') {
      onProgress({ ...progress, phase: 'done' })
      return detail
    }
    if (detail.status === 'failed' || detail.status === 'deleted') {
      throw new UploadError('failed', 'The file did not pass its checks', detail.error ?? detail.status)
    }
    if (Date.now() - started > d.checkTimeoutMs) {
      throw new UploadError('stalled', 'The checks are taking longer than expected')
    }
    await d.sleep(Math.min(3000, 800 + i * 400), signal)
  }
}
