import type { MmsDb } from './db'
import type { BundleFile, FieldBundle } from '@/api/models'
import { db } from './db'
import { sha256Hex } from './hash'

/*
  Prepare for field (OFF-1, AFD J5 step 4, W13-9 to W13-11): download a visit to the phone. The
  server sends one JSON bundle; the files in it (the latest configuration files, and the documents
  the person ticked) are fetched one at a time through the server's ten-minute links and kept as
  blobs. Never a link: it expires (TRD §7.1).

  - Interrupted-safe: a file already stored with the right size is skipped, so running it again
    after a dropped connection fetches only what is missing.
  - A visit is `ready` only when the bundle is stored and every required file is.
  - No Vue and no API client here: the app passes in what talks to the server.
*/

/** The newest bundle shape this app can read; a newer one asks for an update (W13-9). */
export const SUPPORTED_BUNDLE_VERSION = 1

export class BundleTooNew extends Error {
  constructor () {
    super('Update the app, then prepare again')
    this.name = 'BundleTooNew'
  }
}

export interface Progress {
  filesDone: number
  filesTotal: number
  bytesDone: number
  bytesTotal: number
  /** The file being fetched, for the line under the bar. */
  current: string | null
}

export interface Outcome {
  ready: boolean
  /** Files that did not come: documents the person can fetch again or do without. */
  missing: BundleFile[]
  /** Whether a required (configuration) file is among them. */
  requiredMissing: boolean
}

export interface Source {
  bundle: (visitId: string, deviceId: string, signal?: AbortSignal) => Promise<FieldBundle>
  /** A ten-minute link for one file. */
  link: (file: BundleFile, signal?: AbortSignal) => Promise<string>
  /** The bytes behind a link, reporting how many have arrived. */
  download: (url: string, onBytes: (n: number) => void, signal?: AbortSignal) => Promise<Blob>
}

export interface Request {
  visitId: string
  userId: string
  deviceId: string
  /** Media IDs of the optional files to keep; required files are always fetched. */
  documents: ReadonlySet<string>
  signal?: AbortSignal
  onProgress?: (progress: Progress) => void
  store?: MmsDb
}

function wanted (bundle: FieldBundle, documents: ReadonlySet<string>): BundleFile[] {
  return bundle.files.filter(file => file.required || documents.has(file.media_id))
}

/** Reads a response body in pieces so progress can show; falls back to one read. */
export async function readBlob (response: Response, onBytes: (n: number) => void): Promise<Blob> {
  const type = response.headers.get('content-type') ?? ''
  if (!response.body) {
    const blob = await response.blob()
    onBytes(blob.size)
    return blob
  }
  const reader = response.body.getReader()
  const chunks: Uint8Array<ArrayBuffer>[] = []
  for (;;) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    chunks.push(value as Uint8Array<ArrayBuffer>)
    onBytes(value.byteLength)
  }
  return new Blob(chunks, { type })
}

export async function prepareVisit (source: Source, request: Request): Promise<Outcome> {
  const store = request.store ?? db
  const { visitId, userId, signal } = request

  const bundle = await source.bundle(visitId, request.deviceId, signal)
  if (bundle.bundle_version > SUPPORTED_BUNDLE_VERSION) {
    throw new BundleTooNew()
  }
  const files = wanted(bundle, request.documents)

  // What is already here from an earlier run, by media ID and size
  const have = new Map<string, number>()
  for (const row of await store.files.where('media_id').anyOf(files.map(f => f.media_id)).toArray()) {
    if (row.visit_id === visitId && row.user_id === userId) {
      have.set(row.media_id, row.size)
    }
  }
  const todo = files.filter(file => have.get(file.media_id) !== file.size)

  const progress: Progress = {
    filesDone: files.length - todo.length,
    filesTotal: files.length,
    bytesDone: 0,
    bytesTotal: todo.reduce((sum, f) => sum + f.size, 0),
    current: null,
  }
  const report = (): void => request.onProgress?.({ ...progress })

  // The bundle is stored first, not ready, so a dropped connection leaves something to resume
  await store.bundles.put({
    visit_id: visitId,
    user_id: userId,
    bundle_version: bundle.bundle_version,
    prepared_at: bundle.prepared_at,
    ready: false,
    files_total: files.length,
    files_done: progress.filesDone,
    documents: [...request.documents],
    data: bundle,
  })
  report()

  const missing: BundleFile[] = []
  for (const file of todo) {
    signal?.throwIfAborted()
    progress.current = file.name
    report()
    const before = progress.bytesDone
    try {
      const url = await source.link(file, signal)
      const blob = await source.download(url, n => {
        progress.bytesDone += n
        report()
      }, signal)
      if (blob.size !== file.size) {
        throw new Error(`${file.name} arrived with the wrong size`)
      }
      if (file.sha256 && await sha256Hex(blob) !== file.sha256) {
        throw new Error(`${file.name} did not match its checksum`)
      }
      // One write: the file and the count together
      await store.transaction('rw', store.files, store.bundles, async () => {
        await store.files.put({
          media_id: file.media_id,
          visit_id: visitId,
          user_id: userId,
          station_id: file.station_id,
          name: file.name,
          size: file.size,
          content_type: blob.type || 'application/octet-stream',
          required: file.required,
          blob,
          sha256: file.sha256 ?? undefined,
        })
        progress.filesDone += 1
        await store.bundles.update(visitId, { files_done: progress.filesDone })
      })
    } catch (error) {
      if (signal?.aborted || (error instanceof DOMException && error.name === 'QuotaExceededError')) {
        // Stopped by the person, or the phone is full: not a file problem, so say so
        throw error
      }
      // This file only: the others carry on, and the person can try it again
      console.warn(`Prepare: ${file.name} did not download`, error)
      progress.bytesDone = before
      missing.push(file)
    }
  }

  const requiredMissing = missing.some(f => f.required)
  const ready = !requiredMissing
  await store.bundles.update(visitId, { ready, files_done: progress.filesDone })
  progress.current = null
  report()
  return { ready, missing, requiredMissing }
}
