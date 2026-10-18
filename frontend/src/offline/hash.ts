/*
  SHA-256 of a file, as lowercase hex: the checksum `POST /uploads` announces and the media worker
  checks against what it stored (TRD §7.5).

  Web Crypto's `digest` takes the whole file in memory, which is fine for a document (50 MB at the
  most, MED-6) but not for a 200 MB video on an iPhone, and a WebAssembly hasher is ruled out by
  the CSP (no `wasm-unsafe-eval`). So files over `MAX_IN_MEMORY` are refused here until the
  incremental hasher for video exists (finding F4, decided before Phase 4).
*/

export const MAX_IN_MEMORY = 64 * 1024 * 1024

export class TooLargeToHash extends Error {
  constructor (size: number) {
    super(`A ${size}-byte file needs the incremental hasher (finding F4)`)
    this.name = 'TooLargeToHash'
  }
}

export type Hasher = (file: Blob, signal?: AbortSignal) => Promise<string>

export const sha256Hex: Hasher = async (file, signal) => {
  if (file.size > MAX_IN_MEMORY) {
    throw new TooLargeToHash(file.size)
  }
  const bytes = await file.arrayBuffer()
  signal?.throwIfAborted()
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('')
}
