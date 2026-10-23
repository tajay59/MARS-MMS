import type { LocalBlob, MmsDb, OutboxOp } from './db'
import type { Answer } from './outbox'
import { NetworkError } from '@/api/problem'
import { db, setMeta } from './db'
import { wire } from './ops'
import { applyAnswers, clearInflight, sendable } from './outbox'
import { logSync } from './syncLog'

/*
  The sync runner (TRD §7.3; PRD OFF-5 to OFF-8; W14-10, W14-11). It takes what is waiting in the
  outbox and brings it to the server:

      for each visit, in the order the ops were made:
        upload the files its next ops need (each is whole on the server before its op is sent)
        POST /sync up to 100 ops, and keep what the server answered

  One runner at a time, across tabs: the Web Lock `mms-sync` with `ifAvailable` (finding F11). The
  runner takes everything from `Deps` and imports no Vue, Pinia or router, so the service worker
  could run it from a Background Sync event later. A failed request is "offline", whatever
  `navigator.onLine` says: the ops stay as they were and the next trigger tries again.
*/

export const LOCK = 'mms-sync'
export const BATCH = 100

export type Session = { kind: 'ok' } | { kind: 'offline' } | { kind: 'login' }

export interface SyncRequest {
  device_id: string
  ops: ReturnType<typeof wire>[]
}

export interface Deps {
  /** A usable session (the access token is in memory), refreshed under its lock when it is not. */
  session: () => Promise<Session>
  /** `POST /api/v1/sync`. Throws `NetworkError` when the server cannot be reached. */
  send: (body: SyncRequest) => Promise<{ answers: Answer[] }>
  /** Makes the file whole on the server (resumable). Throws `FileRefused` or `NetworkError`. */
  upload: (blob: LocalBlob) => Promise<void>
  deviceId: () => Promise<string>
  now?: () => number
  random?: () => number
  store?: MmsDb
  /** Runs for each op the server applied, in the same Dexie transaction as its removal. */
  onApplied?: (op: OutboxOp, answer: Answer) => Promise<void>
  lock?: <T>(run: () => Promise<T>) => Promise<T | null>
}

/** A file the server will not take (too big, a type media does not know): do not retry it. */
export class FileRefused extends Error {
  constructor (message: string, readonly reason?: string) {
    super(message)
    this.name = 'FileRefused'
  }
}

export type Outcome = 'nothing' | 'done' | 'offline' | 'login' | 'busy'

export interface Result {
  outcome: Outcome
  sent: number
  applied: number
  conflicts: number
  refused: number
}

export interface Options {
  /** Ignore the backoff: "Sync now". */
  force?: boolean
  /** What started this run, for the sync log. */
  trigger?: string
}

let running = false

async function underLock<T> (run: () => Promise<T>): Promise<T | null> {
  if (typeof navigator !== 'undefined' && navigator.locks) {
    return navigator.locks.request(LOCK, { ifAvailable: true }, lock => (lock ? run() : null))
  }
  // No Web Locks: one runner in this tab at least
  if (running) {
    return null
  }
  running = true
  try {
    return await run()
  } finally {
    running = false
  }
}

export async function runSync (userId: string, deps: Deps, options: Options = {}): Promise<Result> {
  const result: Result = { outcome: 'nothing', sent: 0, applied: 0, conflicts: 0, refused: 0 }
  let ran: unknown
  try {
    ran = await (deps.lock ?? underLock)(() => work(userId, deps, options, result))
  } catch (error) {
    await remember(userId, deps, options, result, error instanceof Error ? error.name : 'Error')
    throw error
  }
  if (ran === null) {
    return { ...result, outcome: 'busy' }
  }
  await remember(userId, deps, options, result)
  return result
}

/** The run goes in the sync log (W15-4), unless it found nothing to do. */
async function remember (userId: string, deps: Deps, options: Options, result: Result, error?: string): Promise<void> {
  if (!error && result.outcome === 'nothing') {
    return
  }
  const now = deps.now ?? Date.now
  await logSync(userId, {
    at: new Date(now()).toISOString(),
    trigger: options.trigger ?? (options.force ? 'manual' : 'auto'),
    outcome: error ? 'error' : result.outcome,
    sent: result.sent,
    applied: result.applied,
    conflicts: result.conflicts,
    refused: result.refused,
    error,
  }, deps.store ?? db)
}

async function work (userId: string, deps: Deps, options: Options, result: Result): Promise<void> {
  const store = deps.store ?? db
  const now = deps.now ?? Date.now
  await clearInflight(userId, store)
  const visits = await sendable(userId, now(), options.force, store)
  if (visits.size === 0) {
    return
  }
  const session = await deps.session()
  if (session.kind !== 'ok') {
    result.outcome = session.kind
    return
  }
  const deviceId = await deps.deviceId()
  result.outcome = 'done'

  for (const ops of visits.values()) {
    for (let at = 0; at < ops.length; at += BATCH) {
      const chunk = await withUploads(ops.slice(at, at + BATCH), deps, store, result)
      if (chunk === 'offline') {
        result.outcome = 'offline'
        return
      }
      if (chunk.ops.length > 0) {
        await markInflight(chunk.ops, true, store)
        let reply: { answers: Answer[] }
        try {
          reply = await deps.send({ device_id: deviceId, ops: chunk.ops.map(op => wire(op)) })
        } catch (error) {
          await markInflight(chunk.ops, false, store)
          if (error instanceof NetworkError) {
            result.outcome = 'offline'
            return
          }
          throw error
        }
        await applyAnswers(chunk.ops, reply.answers, now(), { random: deps.random, onApplied: deps.onApplied, store })
        result.sent += chunk.ops.length
        for (const answer of reply.answers) {
          if (answer.status === 'applied' || answer.status === 'duplicate') {
            result.applied += 1
          } else if (answer.status === 'conflict') {
            result.conflicts += 1
          } else if (answer.status === 'error' && !answer.retryable) {
            result.refused += 1
          }
        }
        if (reply.answers.some(a => a.status !== 'applied' && a.status !== 'duplicate')) {
          break // the server skipped the rest of this visit's batch; so do we
        }
      }
      if (chunk.stopped) {
        break
      }
    }
  }
  await setMeta('sync-last', now(), store)
}

async function markInflight (ops: readonly OutboxOp[], on: boolean, store: MmsDb): Promise<void> {
  await store.transaction('rw', store.outbox, async () => {
    for (const op of ops) {
      await store.outbox.update(op.seq!, { inflight: on })
    }
  })
}

/**
 * Make each op's file whole on the server before the op goes. The chunk is cut at the first op
 * whose file cannot go yet, because the ops after it must not pass it.
 */
async function withUploads (
  ops: OutboxOp[], deps: Deps, store: MmsDb, result: Result,
): Promise<'offline' | { ops: OutboxOp[], stopped: boolean }> {
  const ready: OutboxOp[] = []
  for (const op of ops) {
    if (op.blob_id) {
      const blob = await store.blobs.get(op.blob_id)
      if (blob && blob.state !== 'uploaded') {
        try {
          await store.blobs.update(blob.media_id, { state: 'uploading' })
          await deps.upload(blob)
          await store.blobs.update(blob.media_id, { state: 'uploaded' })
        } catch (error) {
          await store.blobs.update(blob.media_id, { state: 'pending' })
          if (error instanceof NetworkError) {
            return 'offline'
          }
          if (error instanceof FileRefused) {
            // The server will never take this file: the op is stuck for good and the person sees it
            await store.outbox.update(op.seq!, { status: 'failed', code: error.reason ?? 'file_refused', message: error.message })
            result.refused += 1
          } else {
            // Out of retries or something unexpected: ask again at the next trigger
            const attempts = op.attempts + 1
            await store.outbox.update(op.seq!, { attempts })
          }
          return { ops: ready, stopped: true }
        }
      }
    }
    ready.push(op)
  }
  return { ops: ready, stopped: false }
}
