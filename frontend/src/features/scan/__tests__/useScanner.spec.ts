import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { useScanner } from '../useScanner'

/*
  The camera loop with a fake camera and a fake detector: what the page is told, and what the
  scanner does with the answer. A code the page refuses (not one of our labels) must leave the
  camera running and the state "scanning", so the page can say so and the person can try another.
*/

function setup (reads: (string | null)[], accept: (text: string) => boolean, capabilities: () => object = () => ({})) {
  const stopped = vi.fn()
  const stream = { getTracks: () => [{ stop: stopped }], getVideoTracks: () => [{ getCapabilities: capabilities }] }
  vi.stubGlobal('navigator', { ...navigator, mediaDevices: { getUserMedia: vi.fn(async () => stream) }, vibrate: vi.fn() })
  const detect = vi.fn(async () => {
    const next = reads.length > 0 ? reads.shift() : null
    return next ? [{ rawValue: next }] : []
  })
  vi.stubGlobal('BarcodeDetector', Object.assign(vi.fn(function () {
    return { detect }
  }), { getSupportedFormats: async () => ['qr_code'] }))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D)

  const onFound = vi.fn(accept)
  let scanner!: ReturnType<typeof useScanner>
  const wrapper = mount(defineComponent({
    setup () {
      scanner = useScanner(onFound)
      return () => h('video', { ref: scanner.video })
    },
  }), { attachTo: document.body })
  const el = wrapper.element as HTMLVideoElement
  Object.defineProperties(el, {
    readyState: { value: 4 },
    videoWidth: { value: 640 },
    videoHeight: { value: 480 },
  })
  el.play = vi.fn(async () => {})
  return { scanner, onFound, stopped, wrapper }
}

describe('useScanner', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('stops the camera and reports found when the page accepts the code', async () => {
    const { scanner, onFound, stopped, wrapper } = setup(['https://x.test/s/abc'], () => true)
    await scanner.start()
    expect(scanner.state.value).toBe('scanning')
    await vi.advanceTimersByTimeAsync(200)
    expect(onFound).toHaveBeenCalledWith('https://x.test/s/abc')
    expect(scanner.state.value).toBe('found')
    expect(stopped).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps scanning when the page refuses the code, and does not ask again at once', async () => {
    const { scanner, onFound, stopped, wrapper } = setup(['https://shop.test/menu', 'https://shop.test/menu', 'https://x.test/s/abc'], text => text.includes('/s/'))
    await scanner.start()
    await vi.advanceTimersByTimeAsync(200)
    expect(onFound).toHaveBeenCalledTimes(1)
    expect(scanner.state.value).toBe('scanning') // not "found": the page can show its message
    expect(stopped).not.toHaveBeenCalled() // the camera stays on

    await vi.advanceTimersByTimeAsync(1000) // still inside the pause
    expect(onFound).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1500) // the second read of the same code, then the label
    await nextTick()
    expect(onFound).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(2000)
    expect(onFound).toHaveBeenLastCalledWith('https://x.test/s/abc')
    expect(scanner.state.value).toBe('found')
    wrapper.unmount()
  })

  it('offers the torch when the camera reports it', async () => {
    const { scanner, wrapper } = setup([], () => true, () => ({ torch: true }))
    await scanner.start()
    await vi.advanceTimersByTimeAsync(10)
    expect(scanner.torchAvailable.value).toBe(true)
    wrapper.unmount()
  })

  it('offers the torch when the phone reports it only after the picture is live', async () => {
    let calls = 0
    const { scanner, wrapper } = setup([], () => true, () => (++calls > 2 ? { torch: true } : {}))
    await scanner.start()
    await vi.advanceTimersByTimeAsync(10)
    expect(scanner.torchAvailable.value).toBe(false)
    await vi.advanceTimersByTimeAsync(1700) // the checks come at 0, 400 and 1,600 ms
    expect(scanner.torchAvailable.value).toBe(true)
    wrapper.unmount()
  })

  it('offers the torch when only the photo capabilities list a flash', async () => {
    vi.stubGlobal('ImageCapture', vi.fn(function () {
      return { getPhotoCapabilities: async () => ({ fillLightMode: ['off', 'flash'] }) }
    }))
    const { scanner, wrapper } = setup([], () => true)
    await scanner.start()
    await vi.advanceTimersByTimeAsync(10)
    expect(scanner.torchAvailable.value).toBe(true)
    wrapper.unmount()
  })

  it('shows no torch button when the camera has none', async () => {
    const { scanner, wrapper } = setup([], () => true)
    await scanner.start()
    await vi.advanceTimersByTimeAsync(3000)
    expect(scanner.torchAvailable.value).toBe(false)
    wrapper.unmount()
  })
})
