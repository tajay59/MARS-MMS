// What the browser does to a photo before it uploads (TRD §7.5, decision W11-12): read the capture
// time from the original, then shrink it to at most 2560 px as JPEG 0.85. The server makes the 2048 px
// WebP and strips EXIF and GPS from what it shows; this only saves the technician's mobile data.
// No Vue imports here.

import type { CaptureTime } from './exif'
import { EXIF_HEAD_BYTES, parseCaptureTime } from './exif'

export const MAX_SIDE = 2560
export const JPEG_QUALITY = 0.85

export interface PreparedImage {
  file: File
  captured: CaptureTime | null
  /** True when the picture was redrawn smaller or re-encoded. */
  resized: boolean
}

/** A file picker's image types the canvas can draw. HEIC is left to the server (Safari converts it already). */
export function isResizable (file: Blob): boolean {
  return ['image/jpeg', 'image/png', 'image/webp'].includes(file.type)
}

export function fitWithin (width: number, height: number, max = MAX_SIDE): { width: number, height: number } {
  const longest = Math.max(width, height)
  if (longest <= max) {
    return { width, height }
  }
  const scale = max / longest
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) }
}

export async function readCaptureTime (file: Blob): Promise<CaptureTime | null> {
  if (file.type !== 'image/jpeg') {
    return null
  }
  try {
    return parseCaptureTime(new Uint8Array(await file.slice(0, EXIF_HEAD_BYTES).arrayBuffer()))
  } catch {
    return null
  }
}

export interface PrepareOptions {
  maxSide?: number
  quality?: number
  signal?: AbortSignal
}

/**
 * Returns the file to upload. A picture that is already small enough, a type the canvas cannot draw
 * (HEIC, video) or a browser without `createImageBitmap` goes through unchanged: preparing is an
 * optimization and never a reason to refuse a photo.
 */
export async function prepareImage (file: File, options: PrepareOptions = {}): Promise<PreparedImage> {
  const captured = await readCaptureTime(file)
  const unchanged = { file, captured, resized: false }
  const max = options.maxSide ?? MAX_SIDE
  if (!isResizable(file) || typeof createImageBitmap !== 'function') {
    return unchanged
  }
  let bitmap: ImageBitmap
  try {
    // 'from-image' applies the EXIF orientation, which the redrawn JPEG no longer carries
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    return unchanged
  }
  try {
    options.signal?.throwIfAborted()
    const size = fitWithin(bitmap.width, bitmap.height, max)
    if (size.width === bitmap.width && size.height === bitmap.height && file.type === 'image/jpeg') {
      return unchanged // small enough and already a JPEG: keep the camera's bytes
    }
    const blob = await draw(bitmap, size, options.quality ?? JPEG_QUALITY)
    if (!blob || (blob.size >= file.size && file.type === 'image/jpeg')) {
      return unchanged
    }
    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    return { file: new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified }), captured, resized: true }
  } finally {
    bitmap.close()
  }
}

async function draw (bitmap: ImageBitmap, size: { width: number, height: number }, quality: number): Promise<Blob | null> {
  if (typeof OffscreenCanvas === 'function') {
    const canvas = new OffscreenCanvas(size.width, size.height)
    const context = canvas.getContext('2d')
    if (!context) {
      return null
    }
    // A PNG with transparency has no JPEG equivalent: put it on white, not black
    context.fillStyle = '#fff'
    context.fillRect(0, 0, size.width, size.height)
    context.drawImage(bitmap, 0, 0, size.width, size.height)
    return canvas.convertToBlob({ type: 'image/jpeg', quality })
  }
  const canvas = document.createElement('canvas')
  canvas.width = size.width
  canvas.height = size.height
  const context = canvas.getContext('2d')
  if (!context) {
    return null
  }
  context.fillStyle = '#fff'
  context.fillRect(0, 0, size.width, size.height)
  context.drawImage(bitmap, 0, 0, size.width, size.height)
  return new Promise(resolve => {
    canvas.toBlob(resolve, 'image/jpeg', quality)
  })
}
