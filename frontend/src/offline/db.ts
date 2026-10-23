import type { EntityTable, Table } from 'dexie'
import Dexie from 'dexie'
import { newId } from '@/app/ids'

/*
  The phone's own store (TRD §7.1, W13-1): one IndexedDB database with the six tables of the
  offline design. Every row except the device's own is tagged with the `user_id` it belongs to, and
  every read filters by it (a shared phone, TRD §7.6).

  - bundles: a prepared visit as the server sent it (`ready` once the required files are stored)
  - files:   manuals, documents and the latest configuration files, as blobs. Never a URL: a
             presigned link expires (TRD §7.1)
  - visits:  the local working copy of a visit and its boards (W14)
  - outbox:  ordered operations, `seq` for strict local order and a unique `op_id` for idempotency
             (rule 9). Created now so W14 needs no schema change; nothing writes to it in W13
  - blobs:   captured media and Config files waiting for upload, and the storage check's files
  - meta:    the device ID, the offline profile and PIN verifier, the failure count

  This module has no Vue and no DOM beyond IndexedDB, so a later sync runner can use it from the
  service worker. Upgrades are forward-only and never touch `outbox` or `blobs` rows.
*/

export const DB_NAME = 'aws-mms'

export interface BundleRow {
  visit_id: string
  user_id: string
  /** `bundle_version` from the server; a newer app reads older ones, never a newer one. */
  bundle_version: number
  prepared_at: string
  /** True once the bundle and every required file are stored. */
  ready: boolean
  files_total: number
  files_done: number
  /** Media IDs of the optional files chosen when preparing; the required ones always come. */
  documents: string[]
  /** The JSON the server sent (`GET /visits/{id}/field-bundle`). */
  data: unknown
}

export interface LocalFile {
  media_id: string
  visit_id: string
  user_id: string
  station_id: string | null
  name: string
  size: number
  content_type: string
  required: boolean
  blob: Blob
  sha256?: string
}

export interface LocalVisit {
  /** An element's ID, or `visit:<id>` for the visit's own state (started, arrived, ended). */
  id: string
  user_id: string
  visit_id?: string
  station_id?: string
  /** The element as the board shows it, or the visit's moves; the server's copy once applied. */
  data: unknown
  /** Changed on the phone and not yet confirmed by the server. */
  dirty?: boolean
}

export type OutboxStatus = 'pending' | 'failed' | 'conflict'

export interface OutboxOp {
  seq?: number
  op_id: string
  /** Payload version (F8): an op queued by an older app still applies after an update. */
  v: number
  user_id: string
  visit_id: string
  type: string
  payload: unknown
  created_at: string
  attempts: number
  status: OutboxStatus
  /** The blob a `media_add` waits for: it is uploaded before the op is sent. */
  blob_id?: string
  /** In the runner's hands right now: the phone must not change it (a save folds into an op only before it is sent). */
  inflight?: boolean
  /** Not before this time (ms): the backoff after a retryable error. */
  next_at?: number
  /** Why the server did not apply it, for Needs attention. */
  code?: string
  message?: string
  /** The server's copy of an element that changed under the phone. */
  current?: unknown
}

/** `uploaded`: whole on the server, waiting for its `media_add`; `done` is not used before W14. */
export type BlobState = 'pending' | 'uploading' | 'uploaded' | 'done' | 'diagnostic'

export interface LocalBlob {
  media_id: string
  user_id: string
  owner_ref: string
  file: Blob
  size: number
  sha256: string
  upload_id?: string
  parts_done?: { part: number, etag: string }[]
  state: BlobState
  visit_id?: string
  name?: string
  /** Media's kind for it: `image`, `video` or `config`. */
  kind?: string
}

export interface MetaRow {
  key: string
  value: unknown
}

export class MmsDb extends Dexie {
  bundles!: EntityTable<BundleRow, 'visit_id'>
  /** The same document can sit in two prepared visits, so the key is the pair. */
  files!: Table<LocalFile, [string, string]>
  visits!: EntityTable<LocalVisit, 'id'>
  outbox!: EntityTable<OutboxOp, 'seq'>
  blobs!: EntityTable<LocalBlob, 'media_id'>
  meta!: EntityTable<MetaRow, 'key'>

  constructor (name: string = DB_NAME) {
    super(name)
    this.version(1).stores({
      bundles: 'visit_id, user_id',
      files: '[visit_id+media_id], media_id, user_id',
      visits: 'id, user_id',
      outbox: '++seq, &op_id, user_id, [user_id+visit_id], status',
      blobs: 'media_id, user_id, state',
      meta: 'key',
    })
    // Version 2 (W14-8): indexes for the board's working copy and the outbox's counts. Additive:
    // no row of `outbox` or `blobs` is touched, so work queued under version 1 survives
    this.version(2).stores({
      visits: 'id, user_id, visit_id, [visit_id+station_id]',
      outbox: '++seq, &op_id, user_id, [user_id+visit_id], [user_id+status], status',
    })
  }
}

export const db = new MmsDb()

type Listener = () => void
const versionListeners = new Set<Listener>()

/**
 Another tab opened the database at a newer schema: close this connection so the upgrade can go
 on, and tell the page to reload ("AWS-MMS was updated in another tab").
*/
export function onVersionChange (listener: Listener): () => void {
  versionListeners.add(listener)
  return () => versionListeners.delete(listener)
}

db.on('versionchange', () => {
  db.close()
  for (const listener of versionListeners) {
    listener()
  }
  return false
})

export async function getMeta<T> (key: string, store: MmsDb = db): Promise<T | undefined> {
  return (await store.meta.get(key))?.value as T | undefined
}

export async function setMeta (key: string, value: unknown, store: MmsDb = db): Promise<void> {
  await store.meta.put({ key, value })
}

/**
 This browser's ID, made once (UUIDv7) and sent with a field bundle so the server can say where a
 visit is prepared (W13-2). It names a browser profile, not a person: clearing site data makes a
 new one.
*/
export async function deviceId (store: MmsDb = db): Promise<string> {
  return store.transaction('rw', store.meta, async () => {
    const found = await store.meta.get('device')
    if (typeof found?.value === 'string') {
      return found.value
    }
    const id = newId()
    await store.meta.put({ key: 'device', value: id })
    return id
  })
}
