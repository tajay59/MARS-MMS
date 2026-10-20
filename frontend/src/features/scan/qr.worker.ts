/// <reference lib="webworker" />

// Decodes camera frames off the main thread, so the video stays smooth while the phone looks for
// a code. Served from our own origin as a module worker (CSP `worker-src 'self'`).

import type { Frame } from './qrDecode'
import { decodeFrame } from './qrDecode'

interface Request extends Frame {
  id: number
}

self.addEventListener('message', (event: MessageEvent<Request>) => {
  const { id, data, width, height } = event.data
  let text: string | null = null
  try {
    text = decodeFrame({ data, width, height })
  } catch {
    // A frame that cannot be read is the same as one with no code in it
  }
  self.postMessage({ id, text })
})
