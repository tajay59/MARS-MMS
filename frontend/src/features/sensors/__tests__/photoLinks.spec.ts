import { afterEach, describe, expect, it, vi } from 'vitest'
import { forgetPhotoLinks, photoUrl } from '../photoLinks'

const link = (url: string, expires: string) => ({ url, expires_at: expires })

describe('photo links', () => {
  afterEach(forgetPhotoLinks)

  it('asks once however many ask, and keeps the link until just before it expires', async () => {
    const fetcher = vi.fn().mockResolvedValue(link('https://files.test/a', '2026-10-20T12:10:00Z'))
    const t0 = Date.parse('2026-10-20T12:00:00Z')
    const [one, two] = await Promise.all([photoUrl('p1', fetcher, t0), photoUrl('p1', fetcher, t0)])
    expect(one).toBe('https://files.test/a')
    expect(two).toBe('https://files.test/a')
    await photoUrl('p1', fetcher, t0 + 8 * 60_000)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await photoUrl('p1', fetcher, t0 + 9.5 * 60_000)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('does not remember a failure', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(link('https://files.test/b', '2026-10-20T12:10:00Z'))
    await expect(photoUrl('p2', fetcher)).rejects.toThrow('offline')
    await expect(photoUrl('p2', fetcher)).resolves.toBe('https://files.test/b')
  })

  it('forgets everything on request', async () => {
    const fetcher = vi.fn().mockResolvedValue(link('https://files.test/c', '2999-01-01T00:00:00Z'))
    await photoUrl('p3', fetcher)
    forgetPhotoLinks()
    await photoUrl('p3', fetcher)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})
