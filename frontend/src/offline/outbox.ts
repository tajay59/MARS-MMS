import type { MmsDb, OutboxOp } from './db'
import type { NewOp } from './ops'
import { db } from './db'

/*
  The outbox (TRD §7.1, §7.2; W14-9, W14-10): operations waiting to reach the server, in the order
  they were made. This module is the only place that writes it, and always with the change it
  belongs to, in one Dexie transaction (the device's twin of the server's outbox rule). Nothing
  here knows about the network; `sync.ts` sends what is waiting and brings the answers back.

  Status, by what must happen next:
    pending   waiting to be sent (maybe after `next_at`, a backoff)
    conflict  the server would not apply it; the phone keeps the person's copy for Export
    failed    the server refused it for good (bad data); the person must see it
  A visit with a conflict or a failed op sends nothing more until the person deals with it: later
  operations would only be skipped by the server, and the order must not be broken.
*/

/** The answer to one op, as `/sync` returns it. */
export interface Answer {
  op_id: string
  status: 'applied' | 'duplicate' | 'conflict' | 'error' | 'skipped'
  code?: string | null
  message?: string | null
  retryable?: boolean
  current?: unknown
  result?: unknown
}

export interface Counts {
  /** Operations waiting to be sent. */
  changes: number
  /** Files waiting to go up (blobs not yet on the server, test files excluded). */
  files: number
  /** Conflicts and refusals the person must look at. */
  attention: number
}

/** Writes a change and its operations together, or neither. Only Dexie calls in `write`. */
export async function enqueue (
  ops: readonly NewOp[], write?: () => Promise<void>, store: MmsDb = db,
): Promise<void> {
  await store.transaction('rw', [store.visits, store.outbox, store.blobs], async () => {
    await write?.()
    for (const op of ops) {
      await store.outbox.add(op)
    }
  })
}

/** 2 s doubling to 5 minutes, with jitter (W14-10). */
export function backoffMs (attempts: number, random: () => number = Math.random): number {
  const ceiling = Math.min(5 * 60_000, 2000 * 2 ** Math.max(0, attempts - 1))
  return Math.round(ceiling * (0.5 + (random() / 2)))
}

/** Visits this user has something stuck in: nothing more is sent for them until it is dealt with. */
export async function blockedVisits (userId: string, store: MmsDb = db): Promise<Set<string>> {
  const stuck = await store.outbox.where('user_id').equals(userId).filter(op => op.status !== 'pending').toArray()
  return new Set(stuck.map(op => op.visit_id))
}

/** What can be sent now, in the order it was made, grouped by visit. */
export async function sendable (
  userId: string, now: number, force = false, store: MmsDb = db,
): Promise<Map<string, OutboxOp[]>> {
  const blocked = await blockedVisits(userId, store)
  const waiting = await store.outbox.where('[user_id+status]').equals([userId, 'pending']).sortBy('seq')
  const byVisit = new Map<string, OutboxOp[]>()
  // A visit whose next op is still in its backoff sends nothing: the ones after it must not pass it
  const held = new Set<string>()
  for (const op of waiting) {
    if (blocked.has(op.visit_id) || held.has(op.visit_id)) {
      continue
    }
    if (!force && (op.next_at ?? 0) > now) {
      held.add(op.visit_id)
      continue
    }
    byVisit.set(op.visit_id, [...(byVisit.get(op.visit_id) ?? []), op])
  }
  return byVisit
}

/** What the badge and /sync show. */
export async function counts (userId: string, store: MmsDb = db): Promise<Counts> {
  const mine = await store.outbox.where('user_id').equals(userId).toArray()
  const blobs = await store.blobs.where('user_id').equals(userId).filter(b => b.state === 'pending' || b.state === 'uploading').count()
  return {
    changes: mine.filter(op => op.status === 'pending').length,
    files: blobs,
    attention: mine.filter(op => op.status !== 'pending').length,
  }
}

/**
 * Take the server's answers into the phone, one Dexie transaction. `applied` and `duplicate`
 * remove the op (the server holds it now); `onApplied` runs in the same transaction so the working
 * copy can take the server's version. A conflict or refusal stays, with its reason; a retryable
 * error waits for its backoff.
 */
export async function applyAnswers (
  sent: readonly OutboxOp[], answers: readonly Answer[], now: number,
  options: { random?: () => number, onApplied?: (op: OutboxOp, answer: Answer) => Promise<void>, store?: MmsDb } = {},
): Promise<void> {
  const store = options.store ?? db
  const byId = new Map(answers.map(a => [a.op_id, a]))
  // `onApplied` may let a finished visit go: its bundle and files are in the transaction too
  await store.transaction('rw', [store.outbox, store.visits, store.blobs, store.bundles, store.files], async () => {
    for (const op of sent) {
      const answer = byId.get(op.op_id)
      if (!op.seq) {
        continue
      }
      if (!answer) {
        await store.outbox.update(op.seq, { inflight: false })
        continue
      }
      switch (answer.status) {
        case 'applied':
        case 'duplicate': {
          await options.onApplied?.(op, answer)
          await store.outbox.delete(op.seq)
          break
        }
        case 'conflict': {
          await store.outbox.update(op.seq, {
            status: 'conflict', code: answer.code ?? undefined, message: answer.message ?? undefined,
            current: answer.current ?? undefined, inflight: false,
          })
          break
        }
        case 'error': {
          if (answer.retryable) {
            const attempts = op.attempts + 1
            await store.outbox.update(op.seq, {
              attempts, next_at: now + backoffMs(attempts, options.random), inflight: false,
              code: answer.code ?? undefined, message: answer.message ?? undefined,
            })
          } else {
            await store.outbox.update(op.seq, {
              status: 'failed', code: answer.code ?? undefined, message: answer.message ?? undefined, inflight: false,
            })
          }
          break
        }
        default: {
          // skipped: an earlier change for the visit did not apply; this one is sent again later
          await store.outbox.update(op.seq, { inflight: false })
          break
        }
      }
    }
  })
}

/** At the start of a run (the only runner holds the lock): nothing is in flight from a run that died. */
export async function clearInflight (userId: string, store: MmsDb = db): Promise<void> {
  await store.transaction('rw', store.outbox, async () => {
    const stale = await store.outbox.where('user_id').equals(userId).filter(op => op.inflight === true).toArray()
    for (const op of stale) {
      await store.outbox.update(op.seq!, { inflight: false })
    }
  })
}

/** The conflicts and refusals, oldest first, for Needs attention. */
export async function attention (userId: string, store: MmsDb = db): Promise<OutboxOp[]> {
  return store.outbox.where('user_id').equals(userId).filter(op => op.status !== 'pending').sortBy('seq')
}

/** After an admin restored a cancelled visit, or the person fixed something: send them again. */
export async function retryStuck (userId: string, visitId: string, store: MmsDb = db): Promise<void> {
  await store.transaction('rw', store.outbox, async () => {
    const stuck = await store.outbox.where('[user_id+visit_id]').equals([userId, visitId]).filter(op => op.status !== 'pending').toArray()
    for (const op of stuck) {
      await store.outbox.update(op.seq!, {
        status: 'pending', attempts: 0, next_at: undefined, code: undefined, message: undefined, current: undefined,
      })
    }
  })
}
