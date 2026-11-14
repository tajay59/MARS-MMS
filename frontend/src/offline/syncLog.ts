import type { MmsDb } from './db'
import { db, getMeta, setMeta } from './db'

/*
  The sync log (W15-4): the last runs of the sync runner, kept on the phone so a technician can
  paste them into a message from "Copy report" when something goes wrong in the field. It holds what
  happened (when, why it ran, how it ended, counts and the name of an error), never what was
  recorded: no note, caption, file name, token or PIN. One list for each user, in `meta`, which a
  logout leaves alone; it holds nothing a second user could use.
*/

export const MAX_ENTRIES = 100

export interface SyncLogEntry {
  /** ISO time the run ended. */
  at: string
  /** What started it: `manual`, `online`, `visible`, `timer`, `start`, `change` or `login`. */
  trigger: string
  outcome: string
  sent: number
  applied: number
  conflicts: number
  refused: number
  /** The name of what was thrown (`TypeError`), if the run ended in an error. */
  error?: string
}

function key (userId: string): string {
  return `sync-log:${userId}`
}

/** Adds an entry, newest last, keeping the latest `MAX_ENTRIES`. Never throws: a log must not break a sync. */
export async function logSync (userId: string, entry: SyncLogEntry, store: MmsDb = db): Promise<void> {
  try {
    await store.transaction('rw', store.meta, async () => {
      const list = (await getMeta<SyncLogEntry[]>(key(userId), store)) ?? []
      list.push(entry)
      await setMeta(key(userId), list.slice(-MAX_ENTRIES), store)
    })
  } catch {
    // A full disk or a closed database: the sync itself matters more than its diary
  }
}

export async function readSyncLog (userId: string, store: MmsDb = db): Promise<SyncLogEntry[]> {
  return (await getMeta<SyncLogEntry[]>(key(userId), store)) ?? []
}

/** One line for the report: `2026-10-30 09:14:02Z manual done sent 12 applied 12 conflicts 0 refused 0`. */
export function formatEntry (entry: SyncLogEntry): string {
  const time = entry.at.replace('T', ' ').replace(/\.\d+Z$/, 'Z')
  const counts = `sent ${entry.sent} applied ${entry.applied} conflicts ${entry.conflicts} refused ${entry.refused}`
  return `${time} ${entry.trigger} ${entry.outcome} ${counts}${entry.error ? ` error ${entry.error}` : ''}`
}
