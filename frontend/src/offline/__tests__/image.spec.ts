import { afterEach, describe, expect, it, vi } from 'vitest'
import { fitWithin, isResizable, prepareImage, readCaptureTime } from '../image'

describe('fitWithin', () => {
  it('keeps a picture that already fits', () => {
    expect(fitWithin(1600, 1200)).toEqual({ width: 1600, height: 1200 })
    expect(fitWithin(2560, 100)).toEqual({ width: 2560, height: 100 })
  })

  it('scales the longest side to the limit and keeps the proportions', () => {
    expect(fitWithin(4032, 3024)).toEqual({ width: 2560, height: 1920 })
    expect(fitWithin(3024, 4032)).toEqual({ width: 1920, height: 2560 })
    expect(fitWithin(10_000, 1)).toEqual({ width: 2560, height: 1 })
  })
})

describe('isResizable', () => {
  it('draws the types a canvas can draw and leaves HEIC and video alone', () => {
    expect(isResizable(new Blob([], { type: 'image/jpeg' }))).toBe(true)
    expect(isResizable(new Blob([], { type: 'image/png' }))).toBe(true)
    expect(isResizable(new Blob([], { type: 'image/heic' }))).toBe(false)
    expect(isResizable(new Blob([], { type: 'video/mp4' }))).toBe(false)
  })
})

describe('prepareImage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends a type it cannot draw unchanged', async () => {
    const file = new File(['x'], 'IMG_1.heic', { type: 'image/heic' })
    const got = await prepareImage(file)
    expect(got.file).toBe(file)
    expect(got.resized).toBe(false)
  })

  it('sends the file unchanged when the browser cannot decode it', async () => {
    vi.stubGlobal('createImageBitmap', async () => {
      throw new Error('bad image')
    })
    const file = new File(['x'], 'broken.png', { type: 'image/png' })
    expect((await prepareImage(file)).file).toBe(file)
  })

  it('redraws a big picture as a smaller JPEG with the same modified time', async () => {
    const close = vi.fn()
    vi.stubGlobal('createImageBitmap', async () => ({ width: 4000, height: 3000, close }))
    const drawn: number[][] = []
    class Canvas {
      constructor (width: number, height: number) {
        drawn.push([width, height])
      }

      getContext () {
        return { fillRect: vi.fn(), drawImage: vi.fn(), fillStyle: '' }
      }

      async convertToBlob (o: { type: string, quality: number }) {
        expect(o).toEqual({ type: 'image/jpeg', quality: 0.85 })
        return new Blob(['small'], { type: 'image/jpeg' })
      }
    }
    vi.stubGlobal('OffscreenCanvas', Canvas)
    const file = new File([new Uint8Array(100_000)], 'IMG_0042.JPG', { type: 'image/jpeg', lastModified: 1_700_000_000_000 })
    const got = await prepareImage(file)
    expect(drawn).toEqual([[2560, 1920]])
    expect(got.resized).toBe(true)
    expect(got.file.name).toBe('IMG_0042.jpg')
    expect(got.file.type).toBe('image/jpeg')
    expect(got.file.lastModified).toBe(1_700_000_000_000)
    expect(close).toHaveBeenCalledOnce()
  })

  it('keeps a small JPEG exactly as the camera wrote it', async () => {
    const close = vi.fn()
    vi.stubGlobal('createImageBitmap', async () => ({ width: 1200, height: 900, close }))
    const file = new File(['jpeg'], 'a.jpg', { type: 'image/jpeg' })
    const got = await prepareImage(file)
    expect(got.file).toBe(file)
    expect(close).toHaveBeenCalledOnce()
  })

  it('stops when it is aborted', async () => {
    const close = vi.fn()
    vi.stubGlobal('createImageBitmap', async () => ({ width: 4000, height: 3000, close }))
    const controller = new AbortController()
    controller.abort()
    await expect(prepareImage(new File(['x'], 'a.png', { type: 'image/png' }), { signal: controller.signal })).rejects.toThrow()
    expect(close).toHaveBeenCalledOnce()
  })
})

describe('readCaptureTime', () => {
  it('answers null for anything that is not a JPEG', async () => {
    expect(await readCaptureTime(new Blob(['x'], { type: 'image/png' }))).toBeNull()
    expect(await readCaptureTime(new Blob(['not exif'], { type: 'image/jpeg' }))).toBeNull()
  })
})
