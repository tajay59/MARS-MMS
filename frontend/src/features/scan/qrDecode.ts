import jsQR from 'jsqr'

/*
  Reading a QR code from a camera frame. Chrome on Android reads codes natively (BarcodeDetector);
  Safari on iPhone does not, so every other browser decodes here with jsQR, in a worker of our own
  (qr.worker.ts), the only file that imports this one: the library stays out of the app chunk. The library behind `qr-scanner` builds its worker from a `blob:` URL, which the
  CSP (`worker-src 'self'`, TRD §15) refuses, so it is not used (finding F16).
*/

export interface Frame {
  data: Uint8ClampedArray
  width: number
  height: number
}

/** The text of the code in the frame, or null when there is none. */
export function decodeFrame (frame: Frame): string | null {
  const found = jsQR(frame.data, frame.width, frame.height, { inversionAttempts: 'attemptBoth' })
  return found?.data ?? null
}
