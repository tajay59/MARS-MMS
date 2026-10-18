// The media service's routes (TRD §3.3). Shapes come from openapi/media.json.
//
// The bytes of a file never pass through here: they go to the files host in 8 MiB parts with
// the presigned URLs `uploadsApi` hands out (see offline/upload.ts).

import type { MediaDetail, MediaPage, UploadIn, UploadOut } from './models'
import { api } from './http'

export const uploadsApi = {
  /** Start an upload, or pick one up again: idempotent by `media_id`. */
  create: (body: UploadIn, signal?: AbortSignal) => api.post<UploadOut>('/uploads', body, { signal }),
  /** Where the upload stands, with fresh URLs for the parts still missing. */
  parts: (mediaId: string, signal?: AbortSignal) => api.post<UploadOut>(`/uploads/${mediaId}/parts`, undefined, { signal }),
  /** Join the parts and queue the file for its checks. Safe to repeat. */
  complete: (mediaId: string, signal?: AbortSignal) => api.post<UploadOut>(`/uploads/${mediaId}/complete`, undefined, { signal }),
}

export const mediaApi = {
  get: (id: string, signal?: AbortSignal) => api.get<MediaDetail>(`/media/${id}`, { signal }),
  list: (ownerRef: string, signal?: AbortSignal) => api.get<MediaPage>('/media', { query: { owner_ref: ownerRef }, signal }),
  /** Remove an upload that did not finish or did not pass its checks. */
  remove: (id: string) => api.delete<void>(`/media/${id}`),
}
