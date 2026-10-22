import { afterEach, describe, expect, it, vi } from 'vitest'
import { newId, UUID7 } from '@/app/ids'
import { sha256Hex } from '../hash'
import { browserNetwork, PartError, sendPartXhr, sleep, withUploadLock } from '../transport'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('ids', () => {
  it('makes UUIDv7s that sort by time', () => {
    const a = newId(1_700_000_000_000)
    const b = newId(1_700_000_000_001)
    expect(a).toMatch(UUID7)
    expect(b).toMatch(UUID7)
    expect(a < b).toBe(true)
    expect(new Set(Array.from({ length: 200 }, () => newId())).size).toBe(200)
  })
})

describe('sha256Hex', () => {
  it('matches the known digest', async () => {
    const hex = await sha256Hex(new Blob(['abc']))
    expect(hex).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  })
})

class Listeners {
  private readonly handlers = new Map<string, Array<(e: unknown) => void>>()

  addEventListener (type: string, handler: (e: unknown) => void) {
    this.handlers.set(type, [...(this.handlers.get(type) ?? []), handler])
  }

  fire (type: string, event: unknown = {}) {
    for (const handler of this.handlers.get(type) ?? []) {
      handler(event)
    }
  }
}

class FakeXhr extends Listeners {
  static last: FakeXhr
  status = 0
  timeout = 0
  method = ''
  url = ''
  sent: Blob | null = null
  upload = new Listeners()
  constructor () {
    super()
    FakeXhr.last = this
  }

  open (method: string, url: string) {
    this.method = method
    this.url = url
  }

  send (body: Blob) {
    this.sent = body
  }

  abort () {
    this.fire('abort')
  }
}

describe('sendPartXhr', () => {
  it('PUTs the part, reports progress, and resolves on 2xx', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const progress: number[] = []
    const body = new Blob(['12345'])
    const done = sendPartXhr('https://files.test/p', body, new AbortController().signal, n => progress.push(n))
    const xhr = FakeXhr.last
    xhr.upload.fire('progress', { loaded: 2 })
    xhr.status = 200
    xhr.fire('load')
    await done
    expect(xhr.method).toBe('PUT')
    expect(xhr.url).toBe('https://files.test/p')
    expect(xhr.sent).toBe(body)
    expect(progress).toEqual([2, 5])
  })

  it('rejects with the status on a refusal and with 0 when there is no answer', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const refused = sendPartXhr('u', new Blob(['x']), new AbortController().signal, () => {})
    FakeXhr.last.status = 403
    FakeXhr.last.fire('load')
    await expect(refused).rejects.toMatchObject({ status: 403 })
    const lost = sendPartXhr('u', new Blob(['x']), new AbortController().signal, () => {})
    FakeXhr.last.fire('error')
    await expect(lost).rejects.toBeInstanceOf(PartError)
    await expect(lost).rejects.toMatchObject({ status: 0 })
  })

  it('stops the request when the caller aborts', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const controller = new AbortController()
    const pending = sendPartXhr('u', new Blob(['x']), controller.signal, () => {})
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('browserNetwork', () => {
  it('is ready at once when online and in the foreground', async () => {
    await expect(browserNetwork.ready(new AbortController().signal)).resolves.toBeUndefined()
  })

  it('waits for the connection to come back', async () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    let settled = false
    const waiting = browserNetwork.ready(new AbortController().signal).then(() => {
      settled = true
    })
    await Promise.resolve()
    expect(settled).toBe(false)
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
    window.dispatchEvent(new Event('online'))
    await waiting
    expect(settled).toBe(true)
  })

  it('waits for the page to come back to the foreground (iOS suspends it)', async () => {
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    let settled = false
    const waiting = browserNetwork.ready(new AbortController().signal).then(() => {
      settled = true
    })
    await Promise.resolve()
    expect(settled).toBe(false)
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    await waiting
    expect(settled).toBe(true)
  })

  it('stops waiting when aborted', async () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    const controller = new AbortController()
    const waiting = browserNetwork.ready(controller.signal)
    controller.abort()
    await expect(waiting).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('withUploadLock', () => {
  it('runs unguarded where Web Locks do not exist', async () => {
    vi.stubGlobal('navigator', { ...navigator })
    Object.defineProperty(navigator, 'locks', { value: undefined, configurable: true })
    expect(await withUploadLock('x', async () => 7)).toBe(7)
  })

  it('returns null when another tab holds the lock', async () => {
    const request = vi.fn(async (_name: string, _opts: unknown, cb: (lock: unknown) => Promise<unknown>) => cb(null))
    vi.stubGlobal('navigator', { locks: { request } })
    expect(await withUploadLock('x', async () => 7)).toBeNull()
    expect(request).toHaveBeenCalledWith('x', { ifAvailable: true }, expect.any(Function))
  })
})

describe('sleep', () => {
  it('resolves after the delay and rejects when aborted', async () => {
    vi.useFakeTimers()
    const done = sleep(1000)
    await vi.advanceTimersByTimeAsync(1000)
    await expect(done).resolves.toBeUndefined()
    const controller = new AbortController()
    const aborted = sleep(1000, controller.signal)
    controller.abort()
    await expect(aborted).rejects.toMatchObject({ name: 'AbortError' })
    vi.useRealTimers()
  })
})
