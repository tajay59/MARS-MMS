import type { Upload, UploadOptions } from './useUpload'
import type { VisitOut } from '@/api/models'
import type { MediaKind, Phase } from '@/features/visits/media'
import { reactive } from 'vue'
import { visitsApi } from '@/api/operations'
import { ApiError, NetworkError } from '@/api/problem'
import { capturedAt, kindOf, mediaRefusal, ownerRef } from '@/features/visits/media'
import { prepareImage } from '@/offline/image'
import { createUpload } from './useUpload'

/*
  Photos and video on their way to a station of a visit (PRD VIS-5; W11-10, W11-12). One item is:
  prepare (a photo is shrunk, its capture time read) → upload to the media service (the engine in
  offline/upload.ts, resumable) → put it on the station. Every step is safe to repeat, so "Try
  again" carries on from the step that failed. Nothing is stored on the device in week 11 (OFF-10):
  a reload loses the pending items and the person chooses the files again.
*/

export type PendingState = 'waiting' | 'preparing' | 'uploading' | 'saving' | 'failed'

export interface PendingMedia {
  key: string
  stationId: string
  phase: Phase
  name: string
  kind: MediaKind
  size: number
  state: PendingState
  /** 0 to 1 of the bytes sent. */
  progress: number
  error: string | null
}

export interface VisitMediaDeps {
  prepare: typeof prepareImage
  upload: (file: File, options: UploadOptions) => Upload
  addMedia: typeof visitsApi.addMedia
}

export interface VisitMediaOptions {
  visit: () => Pick<VisitOut, 'id' | 'stations'>
  /** The visit as the server holds it after an item was put on a station. */
  onVisit: (visit: VisitOut) => void
  /** Files at a time. Two keeps a video from starving the photos behind it on a phone. */
  concurrency?: number
  deps?: Partial<VisitMediaDeps>
}

interface Work {
  item: PendingMedia
  source: File
  /** What is sent: the source, or the shrunk photo once prepared. */
  file: File | null
  captured: string | null
  upload: Upload | null
  mediaId: string | null
}

function wording (error: unknown): string {
  if (error instanceof NetworkError) {
    return 'This needs a connection. Try again when you have signal.'
  }
  if (error instanceof ApiError) {
    return mediaRefusal(error.code) ?? error.detail
  }
  return 'That did not work. Try again.'
}

export function useVisitMedia (options: VisitMediaOptions) {
  const deps: VisitMediaDeps = {
    prepare: prepareImage,
    upload: createUpload,
    addMedia: visitsApi.addMedia,
    ...options.deps,
  }
  const limit = options.concurrency ?? 2
  const items = reactive<PendingMedia[]>([])
  const work = new Map<string, Work>()
  const queue: string[] = []
  let running = 0
  let counter = 0

  function zoneOf (stationId: string): string | null {
    return options.visit().stations.find(s => s.station_id === stationId)?.time_zone ?? null
  }

  async function prepare (job: Work): Promise<void> {
    if (job.file) {
      return
    }
    job.item.state = 'preparing'
    if (job.item.kind === 'image') {
      const prepared = await deps.prepare(job.source)
      job.file = prepared.file
      job.captured = capturedAt(job.source, prepared.captured, zoneOf(job.item.stationId))
    } else {
      job.file = job.source
      job.captured = capturedAt(job.source, null, zoneOf(job.item.stationId))
    }
    job.item.size = job.file.size
  }

  async function send (job: Work): Promise<boolean> {
    if (job.mediaId) {
      return true
    }
    job.item.state = 'uploading'
    job.upload ??= deps.upload(job.file!, {
      ownerRef: ownerRef(options.visit().id, job.item.stationId, job.item.phase),
      kind: job.item.kind,
    })
    const upload = job.upload
    const watch = setInterval(() => {
      job.item.progress = upload.total > 0 ? Math.min(1, upload.sent / upload.total) : 0
    }, 150)
    try {
      const ok = await upload.start()
      if (!ok) {
        job.item.error = upload.error ?? 'The upload did not finish. Try again.'
        upload.reset()
        return false
      }
      job.mediaId = upload.mediaId
      job.item.progress = 1
      return true
    } finally {
      clearInterval(watch)
    }
  }

  async function run (job: Work): Promise<void> {
    job.item.error = null
    try {
      await prepare(job)
      if (!(await send(job))) {
        job.item.state = 'failed'
        return
      }
      job.item.state = 'saving'
      const visit = await deps.addMedia(options.visit().id, job.item.stationId, {
        media_id: job.mediaId!, phase: job.item.phase, captured_at: job.captured,
      })
      options.onVisit(visit)
      work.delete(job.item.key)
      const at = items.indexOf(job.item)
      if (at !== -1) {
        items.splice(at, 1)
      }
    } catch (error) {
      job.item.error = wording(error)
      job.item.state = 'failed'
    }
  }

  function pump (): void {
    while (running < limit && queue.length > 0) {
      const job = work.get(queue.shift()!)
      if (!job) {
        continue
      }
      running++
      void run(job).finally(() => {
        running--
        pump()
      })
    }
  }

  /** Choose files for a phase of a station. Returns the names it could not take. */
  function add (stationId: string, phase: Phase, files: Iterable<File>): string[] {
    const refused: string[] = []
    for (const file of files) {
      const kind = kindOf(file)
      if (!kind) {
        refused.push(file.name)
        continue
      }
      const item = reactive<PendingMedia>({
        key: `pending-${++counter}`, stationId, phase, name: file.name, kind, size: file.size,
        state: 'waiting', progress: 0, error: null,
      })
      items.push(item)
      work.set(item.key, { item, source: file, file: null, captured: null, upload: null, mediaId: null })
      queue.push(item.key)
    }
    pump()
    return refused
  }

  /** Try a failed item again, from the step that failed. */
  function retry (key: string): void {
    const job = work.get(key)
    if (!job || job.item.state !== 'failed') {
      return
    }
    job.item.state = 'waiting'
    queue.push(key)
    pump()
  }

  /** Give up on an item. A half-sent upload is removed from the server. */
  async function discard (key: string): Promise<void> {
    const job = work.get(key)
    if (!job) {
      return
    }
    work.delete(key)
    const at = items.indexOf(job.item)
    if (at !== -1) {
      items.splice(at, 1)
    }
    await job.upload?.cancel(true)
  }

  function forStation (stationId: string, phase?: Phase): PendingMedia[] {
    return items.filter(i => i.stationId === stationId && (!phase || i.phase === phase))
  }

  /** The page is going away: stop sending without telling the server. */
  function dispose (): void {
    queue.length = 0
    for (const job of work.values()) {
      job.upload?.dispose()
    }
  }

  return { items, add, retry, discard, forStation, dispose }
}
