/*
  Hashes a large file off the main thread. The page sends `{ id, file }`; the worker answers
  `{ id, progress }` as it goes and `{ id, hex }` or `{ id, error }` at the end. Served from our
  own origin (`worker-src 'self'`), so the CSP is untouched. No Vue here.
*/

import { sha256Slices } from './hashCore'

interface Request {
  id: number
  file: Blob
}

self.addEventListener('message', (event: MessageEvent<Request>) => {
  const { id, file } = event.data
  sha256Slices(file, {
    onProgress: (done, total) => self.postMessage({ id, progress: done / total }),
  }).then(
    hex => self.postMessage({ id, hex }),
    (error: unknown) => self.postMessage({ id, error: error instanceof Error ? error.message : String(error) }),
  )
})
