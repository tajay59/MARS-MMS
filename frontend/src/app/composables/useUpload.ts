import type { MediaDetail } from '@/api/models'
import type { Phase, UploadApi, UploadDeps } from '@/offline/upload'
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { mediaApi, uploadsApi } from '@/api/media'
import { ApiError, NetworkError } from '@/api/problem'
import { uploadFailure } from '@/features/stations/documents'
import { TooLargeToHash } from '@/offline/hash'
import { UploadError, uploadFile, waitUntilChecked } from '@/offline/upload'

/*
  One file on its way to the media service, as Vue state (PRD OFF-6; TRD §7.3). The engine in
  offline/upload.ts does the work; this keeps its progress where a dialog can show it and lets the
  person cancel. In week 6 uploads happen online at a desk: nothing is stored on the device, and a
  closed tab is picked up again by choosing the same file (the server joins it by size and checksum).
*/

export const mediaUploadApi: UploadApi = {
  create: (body, signal) => uploadsApi.create(body, signal),
  parts: (id, signal) => uploadsApi.parts(id, signal),
  complete: (id, signal) => uploadsApi.complete(id, signal),
  get: (id, signal) => mediaApi.get(id, signal),
}

export type UploadState = 'idle' | 'running' | 'arrived' | 'checking' | 'ready' | 'failed' | 'cancelled'

export interface UploadOptions {
  ownerRef: string
  /** Media's kind for this file: `pdf`, `document` or `config`. */
  kind: string
  /** Wait for media's checks as well as the bytes (configuration files must have passed). */
  untilChecked?: boolean
  deps?: Partial<UploadDeps>
}

function wording (error: unknown): string {
  if (error instanceof UploadError) {
    if (error.kind === 'busy') {
      return 'This file is already being uploaded in another tab.'
    }
    if (error.kind === 'stalled') {
      return 'The connection kept failing. Try again when you have signal.'
    }
    return uploadFailure(error.reason, error.message)
  }
  if (error instanceof TooLargeToHash) {
    return 'This file is too large to check on this device.'
  }
  if (error instanceof NetworkError) {
    return 'This needs a connection. Try again when you have signal.'
  }
  if (error instanceof ApiError) {
    return error.detail
  }
  return 'The upload did not finish. Try again.'
}

export function createUpload (file: File, options: UploadOptions) {
  const state = ref<UploadState>('idle')
  const phase = ref<Phase>('hashing')
  const sent = ref(0)
  const waiting = ref<'network' | 'retry' | null>(null)
  const mediaId = ref<string | null>(null)
  const error = ref<string | null>(null)
  const detail = ref<MediaDetail | null>(null)

  let controller: AbortController | null = null
  let wakeLock: { release: () => Promise<void> } | null = null

  const total = file.size
  const busy = computed(() => state.value === 'running' || state.value === 'checking')

  function leaving (event: BeforeUnloadEvent): void {
    event.preventDefault()
  }

  async function hold (): Promise<void> {
    globalThis.addEventListener('beforeunload', leaving)
    try {
      // Phones dim and lock the screen, which suspends the page (iOS 16.4+ and Chrome have this)
      const lock = (navigator as Navigator & { wakeLock?: { request: (type: 'screen') => Promise<{ release: () => Promise<void> }> } }).wakeLock
      wakeLock = (await lock?.request('screen')) ?? null
    } catch {
      wakeLock = null
    }
  }

  function release (): void {
    globalThis.removeEventListener('beforeunload', leaving)
    void wakeLock?.release().catch(() => {})
    wakeLock = null
  }

  /** Send the file; resolves true when the server holds it (and, with `untilChecked`, when it passed). */
  async function start (): Promise<boolean> {
    controller = new AbortController()
    const { signal } = controller
    const deps: UploadDeps = { api: mediaUploadApi, ...options.deps }
    state.value = 'running'
    error.value = null
    await hold()
    try {
      const arrived = await uploadFile(
        { file, ownerRef: options.ownerRef, kind: options.kind, mediaId: mediaId.value ?? undefined },
        deps,
        signal,
        p => {
          phase.value = p.phase
          sent.value = p.sent
          waiting.value = p.waiting
          mediaId.value = p.mediaId ?? mediaId.value
        },
      )
      mediaId.value = arrived.media_id
      sent.value = total
      state.value = 'arrived'
      if (options.untilChecked) {
        state.value = 'checking'
        detail.value = await waitUntilChecked(arrived.media_id, deps, signal)
        state.value = 'ready'
      }
      return true
    } catch (error_) {
      if (signal.aborted) {
        state.value = 'cancelled'
        return false
      }
      error.value = wording(error_)
      state.value = 'failed'
      return false
    } finally {
      waiting.value = null
      release()
    }
  }

  /** Stop. With `discard`, the half-sent file is also removed from the server. */
  async function cancel (discard = true): Promise<void> {
    controller?.abort()
    state.value = 'cancelled'
    release()
    if (discard && mediaId.value) {
      try {
        await mediaApi.remove(mediaId.value)
      } catch {
        // Already gone, or already part of something: the stale-upload job tidies the rest
      }
    }
  }

  /** A failed try that can be started again, keeping the server's upload so only the rest is sent. */
  function reset (): void {
    state.value = 'idle'
    error.value = null
    sent.value = 0
    waiting.value = null
  }

  /** Stop for good without telling the server (the page is going away). */
  function dispose (): void {
    controller?.abort()
    release()
  }

  // Reactive, so a template reads `upload.sent` and not `upload.sent.value`
  return reactive({ file, state, phase, sent, total, waiting, mediaId, error, detail, busy, start, cancel, reset, dispose })
}

export type Upload = ReturnType<typeof createUpload>

/** Uploads made by a component, stopped when it goes away. */
export function useUploads () {
  const made: Upload[] = []
  onBeforeUnmount(() => {
    for (const upload of made) {
      upload.dispose()
    }
  })
  return {
    add (file: File, options: UploadOptions): Upload {
      const upload = createUpload(file, options)
      made.push(upload)
      return upload
    },
    /** Forget uploads that are finished with, so a long-open dialog doesn't keep them. */
    drop (upload: Upload): void {
      upload.dispose()
      const i = made.indexOf(upload)
      if (i !== -1) {
        made.splice(i, 1)
      }
    },
  }
}
