import type { MediaDetail } from '@/api/models'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clock, forgetMedia, forgetMediaLinks, mediaDetail, onItsWay, openMedia } from '../mediaLinks'

function detail (status: string, urls: Record<string, string> = {}): MediaDetail {
  return { id: 'm1', status, urls } as MediaDetail
}

beforeEach(() => forgetMediaLinks())

describe('mediaDetail', () => {
  it('asks once however many ask, and keeps a ready file for a while', async () => {
    const fetcher = vi.fn(async () => detail('ready', { thumbnail: 'https://files/t' }))
    const [a, b] = await Promise.all([mediaDetail('m1', fetcher, 0), mediaDetail('m1', fetcher, 0)])
    expect(a).toBe(b)
    await mediaDetail('m1', fetcher, 7 * 60_000)
    expect(fetcher).toHaveBeenCalledTimes(1)
    // Before the links run out (ten minutes) it asks again
    await mediaDetail('m1', fetcher, 9 * 60_000)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('does not keep a file that is still being processed', async () => {
    const fetcher = vi.fn(async () => detail('processing'))
    await mediaDetail('m1', fetcher, 0)
    await mediaDetail('m1', fetcher, 1000)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('does not remember a failure', async () => {
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(detail('ready'))
    await expect(mediaDetail('m1', fetcher, 0)).rejects.toThrow('offline')
    await expect(mediaDetail('m1', fetcher, 0)).resolves.toMatchObject({ status: 'ready' })
  })

  it('forgets a file that was removed', async () => {
    const fetcher = vi.fn(async () => detail('ready'))
    await mediaDetail('m1', fetcher, 0)
    forgetMedia('m1')
    await mediaDetail('m1', fetcher, 0)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})

describe('onItsWay', () => {
  it('is true until the file is ready or has failed', () => {
    expect(['pending', 'uploaded', 'processing'].every(s => onItsWay(s))).toBe(true)
    expect(onItsWay('ready')).toBe(false)
    expect(onItsWay('failed')).toBe(false)
  })
})

describe('openMedia', () => {
  it('opens the tab in the click and points it at a fresh link', async () => {
    const tab = { opener: {}, location: { href: '' }, close: vi.fn() }
    const open = vi.spyOn(globalThis, 'open').mockReturnValue(tab as unknown as Window)
    await openMedia('m1', async () => detail('ready', { view: 'https://files/v' }))
    expect(open).toHaveBeenCalledWith('', '_blank')
    expect(tab.location.href).toBe('https://files/v')
    expect(tab.opener).toBeNull()
    open.mockRestore()
  })

  it('closes the tab when there is no link yet', async () => {
    const tab = { opener: {}, location: { href: '' }, close: vi.fn() }
    const open = vi.spyOn(globalThis, 'open').mockReturnValue(tab as unknown as Window)
    await expect(openMedia('m1', async () => detail('processing'))).rejects.toThrow()
    expect(tab.close).toHaveBeenCalled()
    open.mockRestore()
  })
})

describe('clock', () => {
  it('writes a length as m:ss', () => {
    expect(clock(40)).toBe('0:40')
    expect(clock(125.4)).toBe('2:05')
    expect(clock(null)).toBe('')
    expect(clock(-1)).toBe('')
  })
})
