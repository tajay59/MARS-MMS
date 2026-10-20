import type { Ref } from 'vue'
import { onBeforeUnmount, ref, shallowRef } from 'vue'
import { guideRegion } from './scan'

/*
  The camera and the loop that reads codes from it (QR-2). Camera access is asked for only when
  `start()` is called, by the Scan page and never at start-up. The camera stops when the page is
  left, when the app goes to the background (iOS suspends it anyway) and when a code is found.
*/

export type ScannerState
  = | 'idle'
    | 'starting'
    | 'scanning'
    | 'found'
    | 'denied' // the person or the browser said no
    | 'unavailable' // no camera, in use by another app, or no secure context

const ANALYSE_EVERY_MS = 120
const MAX_ANALYSED_SIDE = 480

interface Detector {
  detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]>
}

declare const BarcodeDetector: (new (options: { formats: string[] }) => Detector) & {
  getSupportedFormats?: () => Promise<string[]>
} | undefined

async function nativeDetector (): Promise<Detector | null> {
  try {
    if (BarcodeDetector === undefined || !BarcodeDetector.getSupportedFormats) {
      return null
    }
    const formats = await BarcodeDetector.getSupportedFormats()
    return formats.includes('qr_code') ? new BarcodeDetector({ formats: ['qr_code'] }) : null
  } catch {
    return null
  }
}

/** How the browser answered the camera question before asking, when it can say (not Safari). */
export async function cameraPermission (): Promise<'granted' | 'denied' | 'prompt'> {
  try {
    const status = await navigator.permissions.query({ name: 'camera' as PermissionName })
    return status.state
  } catch {
    return 'prompt'
  }
}

export function useScanner (onFound: (text: string) => void): {
  video: Ref<HTMLVideoElement | null>
  state: Ref<ScannerState>
  torchAvailable: Ref<boolean>
  torchOn: Ref<boolean>
  start: () => Promise<void>
  stop: () => void
  toggleTorch: () => Promise<void>
} {
  const video = ref<HTMLVideoElement | null>(null)
  const state = ref<ScannerState>('idle')
  const torchAvailable = ref(false)
  const torchOn = ref(false)
  const track = shallowRef<MediaStreamTrack | null>(null)

  let stream: MediaStream | null = null
  let worker: Worker | null = null
  let detector: Detector | null = null
  let canvas: HTMLCanvasElement | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let session = 0 // each start() gets a number; a late answer from an older one is ignored
  let wanted = false // the person wants the camera, so it comes back when the app does
  let nextId = 0
  let waiting: { id: number, resolve: (text: string | null) => void } | null = null

  function release (): void {
    clearTimeout(timer)
    timer = undefined
    waiting?.resolve(null)
    waiting = null
    worker?.terminate()
    worker = null
    for (const t of stream?.getTracks() ?? []) {
      t.stop()
    }
    stream = null
    track.value = null
    torchAvailable.value = false
    torchOn.value = false
    if (video.value) {
      video.value.srcObject = null
    }
  }

  function stop (): void {
    wanted = false
    session++
    release()
    if (state.value === 'scanning' || state.value === 'starting') {
      state.value = 'idle'
    }
  }

  async function start (): Promise<void> {
    if (state.value === 'starting' || state.value === 'scanning') {
      return
    }
    const mine = ++session
    wanted = true
    state.value = 'starting'
    if (!navigator.mediaDevices?.getUserMedia) {
      state.value = 'unavailable'
      return
    }
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
      if (mine !== session || !video.value) {
        for (const t of media.getTracks()) {
          t.stop()
        }
        return
      }
      stream = media
      const [videoTrack] = media.getVideoTracks()
      track.value = videoTrack ?? null
      const capabilities = videoTrack?.getCapabilities?.() as { torch?: boolean } | undefined
      torchAvailable.value = capabilities?.torch === true

      // iOS needs these before it plays inline
      video.value.muted = true
      video.value.playsInline = true
      video.value.srcObject = media
      await video.value.play()
      if (mine !== session) {
        return
      }

      detector = await nativeDetector()
      if (!detector) {
        worker = new Worker(new URL('qr.worker.ts', import.meta.url), { type: 'module' })
        worker.addEventListener('message', (event: MessageEvent<{ id: number, text: string | null }>) => {
          if (waiting?.id === event.data.id) {
            waiting.resolve(event.data.text)
            waiting = null
          }
        })
      }
      state.value = 'scanning'
      schedule(mine)
    } catch (error) {
      if (mine !== session) {
        return
      }
      release()
      const name = error instanceof DOMException ? error.name : ''
      state.value = name === 'NotAllowedError' || name === 'SecurityError' ? 'denied' : 'unavailable'
    }
  }

  function schedule (mine: number): void {
    timer = setTimeout(() => void analyse(mine), ANALYSE_EVERY_MS)
  }

  async function analyse (mine: number): Promise<void> {
    const el = video.value
    if (mine !== session || !el || el.readyState < 2 || el.videoWidth === 0) {
      if (mine === session) {
        schedule(mine)
      }
      return
    }
    let text: string | null = null
    try {
      text = await read(el)
    } catch {
      // One bad frame: try the next
    }
    if (mine !== session) {
      return
    }
    if (text) {
      state.value = 'found'
      release()
      try {
        navigator.vibrate?.(50)
      } catch {
        // Not every phone vibrates
      }
      onFound(text)
      return
    }
    schedule(mine)
  }

  /** Reads the middle square of the frame, shrunk to a size a phone decodes quickly. */
  async function read (el: HTMLVideoElement): Promise<string | null> {
    const region = guideRegion(el.videoWidth, el.videoHeight)
    const side = Math.min(region.size, MAX_ANALYSED_SIDE)
    canvas ??= document.createElement('canvas')
    canvas.width = side
    canvas.height = side
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) {
      return null
    }
    context.drawImage(el, region.x, region.y, region.size, region.size, 0, 0, side, side)
    if (detector) {
      const [code] = await detector.detect(canvas)
      return code?.rawValue ?? null
    }
    if (!worker) {
      return null
    }
    const image = context.getImageData(0, 0, side, side)
    const id = nextId++
    const answer = new Promise<string | null>(resolve => {
      waiting = { id, resolve }
    })
    worker.postMessage({ id, data: image.data, width: side, height: side }, [image.data.buffer])
    return answer
  }

  async function toggleTorch (): Promise<void> {
    const t = track.value
    if (!t || !torchAvailable.value) {
      return
    }
    try {
      await t.applyConstraints({ advanced: [{ torch: !torchOn.value } as MediaTrackConstraintSet] })
      torchOn.value = !torchOn.value
    } catch {
      torchAvailable.value = false // the phone said no: hide the button
    }
  }

  // The app goes to the background: stop the camera, and bring it back with the app
  function onVisibility (): void {
    if (document.hidden) {
      if (state.value === 'scanning' || state.value === 'starting') {
        session++
        release()
        state.value = 'idle'
      }
    } else if (wanted && state.value === 'idle') {
      void start()
    }
  }
  document.addEventListener('visibilitychange', onVisibility)

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisibility)
    stop()
  })

  return { video, state, torchAvailable, torchOn, start, stop, toggleTorch }
}
