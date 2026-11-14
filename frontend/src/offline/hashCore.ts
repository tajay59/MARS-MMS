/*
  SHA-256 of a Blob in slices, with nothing larger than one slice in memory (finding F4).

  Web Crypto's `digest` takes the whole file at once, which a 200 MB video on an iPhone cannot
  afford, and a WebAssembly hasher is ruled out by the CSP (no `wasm-unsafe-eval`). `@noble/hashes`
  is plain JavaScript with an incremental interface, so the file is read 8 MiB at a time with
  `Blob.slice()` and fed to it. No Vue and no DOM here: the same function runs in the hashing
  worker and, where workers are missing, on the main thread.
*/

import { sha256 } from '@noble/hashes/sha2'
import { bytesToHex } from '@noble/hashes/utils'

export const SLICE = 8 * 1024 * 1024

export interface HashOptions {
  slice?: number
  signal?: AbortSignal
  /** Bytes hashed so far, after each slice */
  onProgress?: (done: number, total: number) => void
  /** Called between slices on the main thread, so the page can paint and respond */
  yieldNow?: () => Promise<void>
}

export async function sha256Slices (blob: Blob, options: HashOptions = {}): Promise<string> {
  const slice = options.slice ?? SLICE
  const hash = sha256.create()
  for (let at = 0; at < blob.size; at += slice) {
    options.signal?.throwIfAborted()
    hash.update(new Uint8Array(await blob.slice(at, at + slice).arrayBuffer()))
    options.onProgress?.(Math.min(at + slice, blob.size), blob.size)
    if (options.yieldNow) {
      await options.yieldNow()
    }
  }
  return bytesToHex(hash.digest())
}
