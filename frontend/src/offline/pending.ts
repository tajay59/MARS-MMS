import type { MmsDb } from './db'
import type { FieldBundle } from '@/api/models'
import { db } from './db'

/*
  What is waiting on this phone, visit by visit (AFD §3 /sync). No Vue and no network: the page and
  the badge ask IndexedDB, so the numbers are right with no signal. Diagnostic test files are not
  work and are never counted.
*/

export interface VisitPending {
  visit_id: string
  ref: string
  title: string
  /** Operations that will be sent. */
  changes: number
  /** Files that have not reached the server yet. */
  files: number
  /** Bytes of those files. */
  bytes: number
}

/** Pending work for each visit that has some, oldest first. Conflicts are not counted here: they are Needs attention. */
export async function pendingByVisit (userId: string, store: MmsDb = db): Promise<VisitPending[]> {
  const ops = await store.outbox.where('user_id').equals(userId).filter(op => op.status === 'pending').toArray()
  const blobs = await store.blobs.where('user_id').equals(userId).filter(b => b.state === 'pending' || b.state === 'uploading').toArray()
  const found = new Map<string, VisitPending>()
  const entry = async (visitId: string): Promise<VisitPending> => {
    const known = found.get(visitId)
    if (known) {
      return known
    }
    const bundle = (await store.bundles.get(visitId))?.data as FieldBundle | undefined
    const created = {
      visit_id: visitId, ref: bundle?.visit.ref ?? 'Visit', title: bundle?.visit.request_title ?? '', changes: 0, files: 0, bytes: 0,
    }
    found.set(visitId, created)
    return created
  }
  for (const op of ops) {
    (await entry(op.visit_id)).changes++
  }
  for (const blob of blobs) {
    if (blob.visit_id) {
      const item = await entry(blob.visit_id)
      item.files++
      item.bytes += blob.size
    }
  }
  return [...found.values()]
}

export interface Totals {
  changes: number
  files: number
  bytes: number
  attention: number
}

export function totalsOf (visits: VisitPending[], attention: number): Totals {
  return {
    changes: visits.reduce((sum, v) => sum + v.changes, 0),
    files: visits.reduce((sum, v) => sum + v.files, 0),
    bytes: visits.reduce((sum, v) => sum + v.bytes, 0),
    attention,
  }
}
