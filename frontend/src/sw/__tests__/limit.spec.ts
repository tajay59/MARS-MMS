import { describe, expect, it, vi } from 'vitest'
import { eachLimited, withRetry } from '../limit'

describe('eachLimited', () => {
  it('runs every item, never more than the limit at once', async () => {
    let running = 0
    let peak = 0
    const done: number[] = []
    await eachLimited([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 3, async item => {
      running++
      peak = Math.max(peak, running)
      await new Promise(resolve => setTimeout(resolve, 5))
      done.push(item)
      running--
    })
    expect(done).toHaveLength(10)
    expect(new Set(done)).toEqual(new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
    expect(peak).toBe(3)
  })

  it('rejects with the first failure and starts no new items after it', async () => {
    const started: number[] = []
    const run = eachLimited([1, 2, 3, 4, 5, 6], 2, async item => {
      started.push(item)
      if (item === 2) {
        throw new Error('fetch failed')
      }
      await new Promise(resolve => setTimeout(resolve, 5))
    })
    await expect(run).rejects.toThrow('fetch failed')
    expect(started).toEqual([1, 2])
  })

  it('finishes at once with nothing to do', async () => {
    const task = vi.fn(async () => {})
    await eachLimited([], 6, task)
    expect(task).not.toHaveBeenCalled()
  })
})

describe('withRetry', () => {
  it('returns once a try succeeds', async () => {
    const task = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce('ok')
    await expect(withRetry(task, 3, 1)).resolves.toBe('ok')
    expect(task).toHaveBeenCalledTimes(2)
  })

  it('gives up after the last attempt with its error', async () => {
    const task = vi.fn().mockRejectedValue(new Error('offline'))
    await expect(withRetry(task, 3, 1)).rejects.toThrow('offline')
    expect(task).toHaveBeenCalledTimes(3)
  })
})
