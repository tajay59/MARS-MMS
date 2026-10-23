import type { Answer } from '../outbox'
import type { SyncLogEntry } from '../syncLog'
import { afterEach, describe, expect, it } from 'vitest'
import { NetworkError } from '@/api/problem'
import { forgetUser } from '../cleanup'
import { MmsDb } from '../db'
import { startOp } from '../ops'
import { enqueue } from '../outbox'
import { formatReport, pinWords, type ReportData } from '../report'
import { runSync } from '../sync'
import { formatEntry, logSync, MAX_ENTRIES, readSyncLog } from '../syncLog'

// The sync log and the phone report (W15-4): what the runner did, kept small, per user, and free of
// anything the person recorded.

const opened: MmsDb[] = []
let n = 0
function open (): MmsDb {
  const store = new MmsDb(`log-${n++}`)
  opened.push(store)
  return store
}
afterEach(async () => {
  for (const store of opened.splice(0)) {
    store.close()
    await store.delete()
  }
})

function entry (over: Partial<SyncLogEntry> = {}): SyncLogEntry {
  return {
    at: '2026-10-30T09:14:02.123Z', trigger: 'manual', outcome: 'done', sent: 3, applied: 3, conflicts: 0, refused: 0, ...over,
  }
}

describe('the log', () => {
  it('keeps the latest hundred entries, oldest first', async () => {
    const store = open()
    for (let i = 0; i < MAX_ENTRIES + 5; i++) {
      await logSync('u1', entry({ sent: i }), store)
    }
    const log = await readSyncLog('u1', store)
    expect(log).toHaveLength(MAX_ENTRIES)
    expect(log[0]!.sent).toBe(5)
    expect(log.at(-1)!.sent).toBe(MAX_ENTRIES + 4)
  })

  it('is kept for each user and survives a logout', async () => {
    const store = open()
    await logSync('u1', entry(), store)
    await logSync('u2', entry({ outcome: 'offline' }), store)
    await forgetUser('u1', store)
    expect(await readSyncLog('u1', store)).toHaveLength(1)
    expect((await readSyncLog('u2', store))[0]!.outcome).toBe('offline')
  })

  it('writes one line per entry', () => {
    expect(formatEntry(entry())).toBe('2026-10-30 09:14:02Z manual done sent 3 applied 3 conflicts 0 refused 0')
    expect(formatEntry(entry({ error: 'TypeError', outcome: 'error' }))).toContain('error TypeError')
  })

  it('never throws, even when the database is closed', async () => {
    const store = open()
    store.close()
    await expect(logSync('u1', entry(), store)).resolves.toBeUndefined()
  })
})

describe('the runner writes it', () => {
  function deps (store: MmsDb, send: () => Promise<{ answers: Answer[] }>) {
    return {
      session: async () => ({ kind: 'ok' as const }),
      send,
      upload: async () => undefined,
      deviceId: async () => 'device-1',
      now: () => Date.parse('2026-10-30T09:14:02Z'),
      random: () => 1,
      lock: async <T>(run: () => Promise<T>) => run(),
      store,
    }
  }
  const ctx = { userId: 'u1', visitId: 'v1' }

  it('records a run with its trigger and counts, and nothing for a run with nothing to do', async () => {
    const store = open()
    await runSync('u1', deps(store, async () => ({ answers: [] })), { trigger: 'timer' })
    expect(await readSyncLog('u1', store)).toEqual([])

    const op = startOp(ctx, '2026-10-30T09:00:00Z')
    await enqueue([op], undefined, store)
    await runSync('u1', deps(store, async () => ({ answers: [{ op_id: op.op_id, status: 'applied' }] })), { trigger: 'online' })
    const log = await readSyncLog('u1', store)
    expect(log).toHaveLength(1)
    expect(log[0]).toMatchObject({ trigger: 'online', outcome: 'done', sent: 1, applied: 1, at: '2026-10-30T09:14:02.000Z' })
  })

  it('records an unreachable server as offline and an unexpected error by its name only', async () => {
    const store = open()
    await enqueue([startOp(ctx, '2026-10-30T09:00:00Z')], undefined, store)
    await runSync('u1', deps(store, async () => {
      throw new NetworkError('down')
    }), { force: true })
    expect((await readSyncLog('u1', store))[0]).toMatchObject({ outcome: 'offline', trigger: 'manual' })

    await expect(runSync('u1', deps(store, async () => {
      throw new TypeError('secret note text')
    }), { force: true })).rejects.toThrow(TypeError)
    const last = (await readSyncLog('u1', store)).at(-1)!
    expect(last).toMatchObject({ outcome: 'error', error: 'TypeError' })
    expect(JSON.stringify(last)).not.toContain('secret')
  })
})

describe('the report', () => {
  const data: ReportData = {
    time: '2026-10-30T09:20:00.000Z',
    version: '0.5.0',
    phone: 'Android 15, Chrome',
    installed: true,
    online: false,
    worker: true,
    storage: { used: 300 * 1024 ** 2, quota: 40 * 1024 ** 3, free: 0, percent: 1, persisted: true },
    pin: 'set, valid to 2026-11-29',
    device: '0192…ab12',
    prepared: { visits: 1, files: 4 },
    queue: { pending: 12, conflict: 1, failed: 0, files: 18, bytes: 52 * 1024 ** 2 },
    caches: { names: ['workbox-precache-v2'], apiUrls: 0 },
    log: [entry(), entry({ outcome: 'offline', sent: 0, applied: 0 })],
  }

  it('lists the facts a developer needs, in plain text', () => {
    const text = formatReport(data)
    expect(text).toContain('App: version 0.5.0, installed')
    expect(text).toContain('Waiting: 12 changes, 18 files (52 MB)')
    expect(text).toContain('Needs attention: 1 conflicts, 0 refused')
    expect(text).toContain('API URLs cached: 0')
    expect(text).toContain('Sync log (last 2 of 2, oldest first):')
    expect(text).toContain('manual offline sent 0')
  })

  it('shows only the newest fifty log lines', () => {
    const many = Array.from({ length: 80 }, (_, i) => entry({ sent: i }))
    const text = formatReport({ ...data, log: many })
    expect(text).toContain('Sync log (last 50 of 80')
    expect(text).toContain('sent 79 ')
    expect(text).not.toContain('sent 29 ')
  })

  it('says so when there is nothing to show', () => {
    expect(formatReport({ ...data, log: [], storage: null, caches: null })).toMatch(/Storage: not reported[\s\S]*\(no runs yet\)/)
  })

  it('describes the PIN without saying anything secret', () => {
    expect(pinWords({ kind: 'none' })).toBe('not set')
    expect(pinWords({ kind: 'disabled' })).toBe('turned off after wrong tries')
    expect(pinWords(null)).toBe('unknown')
  })
})
