import type { LocalBlob } from './db'
import type { Deps, SyncRequest } from './sync'
import type { UploadApi } from './upload'
import { api } from '@/api/http'
import { mediaApi, uploadsApi } from '@/api/media'
import { ApiError, NetworkError } from '@/api/problem'
import { currentSession, refreshSession } from '@/app/auth/session'
import { deviceId } from './db'
import { FileRefused } from './sync'
import { UploadError, uploadFile } from './upload'

/*
  What the runner uses in the app: the real session, the real `/sync` and the real upload engine
  (W14-10, W14-12). Kept apart from `sync.ts`, which knows nothing about any of them.
*/

export const uploadApi: UploadApi = {
  create: (body, signal) => uploadsApi.create(body, signal),
  parts: (id, signal) => uploadsApi.parts(id, signal),
  complete: (id, signal) => uploadsApi.complete(id, signal),
  get: (id, signal) => mediaApi.get(id, signal),
}

/** No waiting for signal inside a sync: with none, say so and let the next trigger try again. */
const failFast = {
  ready: async (): Promise<void> => {
    if (!navigator.onLine) {
      throw new NetworkError(undefined)
    }
  },
}

/** A file kept on the phone, as a `File` the upload engine reads in parts. */
function asFile (blob: LocalBlob): File {
  return blob.file instanceof File
    ? blob.file
    : new File([blob.file], blob.name ?? 'file', { type: blob.file.type })
}

export const appDeps: Deps = {
  session: async () => {
    const live = currentSession()
    // Seconds of life left on the token are not enough to finish a batch: refresh early
    if (live && live.expiresAt - Date.now() > 60_000) {
      return { kind: 'ok' }
    }
    const result = await refreshSession()
    switch (result.kind) {
      case 'ok': {
        return { kind: 'ok' }
      }
      case 'offline': {
        return { kind: 'offline' }
      }
      default: {
        return { kind: 'login' }
      }
    }
  },

  send: (body: SyncRequest) => api.post('/sync', body),

  upload: async blob => {
    try {
      await uploadFile({
        file: asFile(blob),
        ownerRef: blob.owner_ref,
        kind: blob.kind ?? 'image',
        mediaId: blob.media_id,
      }, {
        api: uploadApi,
        // The fingerprint was taken when the file was captured: do not read it all again
        hash: async () => blob.sha256,
        network: failFast,
      }, new AbortController().signal)
    } catch (error) {
      if (error instanceof UploadError && error.kind === 'failed') {
        throw new FileRefused(error.message, error.reason)
      }
      if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 429 && error.status !== 408) {
        // The owner check or the type check said no, for this file and every retry
        throw new FileRefused(error.detail, error.reason)
      }
      throw error
    }
  },

  deviceId: () => deviceId(),
}
