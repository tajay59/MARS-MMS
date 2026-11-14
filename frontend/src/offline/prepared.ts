import type { BundleRow, LocalFile, MmsDb } from './db'
import type { BundleStation, FieldBundle } from '@/api/models'
import Dexie from 'dexie'
import { db } from './db'

/*
  Reading what Prepare left on the phone (QR-5, CFG-4, OFF-2; W13-13). No Vue and no network: the
  offline pages and the scanner ask these questions of IndexedDB. Every read is for one user, the
  one signed in; another user's rows are never looked at (TRD §7.6).
*/

export interface Prepared {
  row: BundleRow
  bundle: FieldBundle
}

export interface PreparedStation {
  prepared: Prepared
  station: BundleStation
}

function asPrepared (row: BundleRow): Prepared {
  return { row, bundle: row.data as FieldBundle }
}

/** Every visit prepared on this phone by this user, newest first. */
export async function preparedVisits (userId: string, store: MmsDb = db): Promise<Prepared[]> {
  const rows = await store.bundles.where('user_id').equals(userId).toArray()
  return rows.toSorted((a, b) => b.prepared_at.localeCompare(a.prepared_at)).map(row => asPrepared(row))
}

export async function preparedVisit (userId: string, visitId: string, store: MmsDb = db): Promise<Prepared | null> {
  const row = await store.bundles.get(visitId)
  return row && row.user_id === userId ? asPrepared(row) : null
}

/** A station as the newest prepared visit that includes it describes it. */
export async function preparedStation (userId: string, stationId: string, store: MmsDb = db): Promise<PreparedStation | null> {
  for (const prepared of await preparedVisits(userId, store)) {
    const station = prepared.bundle.stations.find(s => s.station.id === stationId)
    if (station) {
      return { prepared, station }
    }
  }
  return null
}

/** The station a scanned label belongs to, if a prepared visit includes it (QR-5). */
export async function stationByToken (userId: string, token: string, store: MmsDb = db): Promise<PreparedStation | null> {
  for (const prepared of await preparedVisits(userId, store)) {
    const station = prepared.bundle.stations.find(s => s.station.qr_token === token)
    if (station) {
      return { prepared, station }
    }
  }
  return null
}

/** The files stored for one visit, by media ID. */
export async function storedFiles (userId: string, visitId: string, store: MmsDb = db): Promise<Map<string, LocalFile>> {
  const rows = await store.files.where('[visit_id+media_id]').between([visitId, Dexie.minKey], [visitId, Dexie.maxKey]).filter(f => f.user_id === userId).toArray()
  return new Map(rows.map(f => [f.media_id, f]))
}
