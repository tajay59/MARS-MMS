import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import { MAX_IN_MEMORY, sha256Hex } from '../hash'
import { sha256Slices, SLICE } from '../hashCore'

// SHA-256 of large files in slices (finding F4): the same answer as the whole file at once, with
// nothing bigger than a slice read at a time.

function bytes (n: number): Uint8Array<ArrayBuffer> {
  // Not all one value, so a slice taken from the wrong place changes the digest
  const out = new Uint8Array(n)
  for (let i = 0; i < n; i++) {
    out[i] = (i * 31 + (i >> 8)) & 0xFF
  }
  return out
}

function node (data: Uint8Array): string {
  return createHash('sha256').update(data).digest('hex')
}

describe('sha256Slices', () => {
  it('matches the known digests', async () => {
    expect(await sha256Slices(new Blob(['abc']))).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    expect(await sha256Slices(new Blob([]))).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
  })

  it('gives the same digest however the file is cut', async () => {
    const data = bytes(1_000_003)
    const want = node(data)
    for (const slice of [1, 7, 4096, 65_536, 999_999, 1_000_003, 5_000_000]) {
      expect(await sha256Slices(new Blob([data]), { slice })).toBe(want)
    }
  })

  it('hashes a file larger than the in-memory limit in 8 MiB slices, to the same digest', async () => {
    const data = bytes(MAX_IN_MEMORY + SLICE + 12_345)
    const seen: number[] = []
    const hex = await sha256Slices(new Blob([data]), { onProgress: done => seen.push(done) })
    expect(hex).toBe(node(data))
    expect(seen.length).toBe(Math.ceil(data.length / SLICE))
    expect(seen.at(-1)).toBe(data.length)
    expect(seen).toEqual(seen.toSorted((a, b) => a - b))
  })

  it('never reads more than one slice at a time', async () => {
    const data = bytes(3 * 1024 + 5)
    const real = new Blob([data])
    const reads: number[] = []
    const spy = {
      size: real.size,
      slice: (from: number, to: number) => {
        const part = real.slice(from, to)
        reads.push(part.size)
        return part
      },
    } as unknown as Blob
    expect(await sha256Slices(spy, { slice: 1024 })).toBe(node(data))
    expect(Math.max(...reads)).toBeLessThanOrEqual(1024)
    expect(reads).toHaveLength(4)
  })

  it('stops between slices when it is aborted', async () => {
    const controller = new AbortController()
    const data = bytes(10_000)
    let slices = 0
    await expect(sha256Slices(new Blob([data]), {
      slice: 1000,
      signal: controller.signal,
      onProgress: () => {
        if (++slices === 3) {
          controller.abort()
        }
      },
    })).rejects.toThrow()
    expect(slices).toBe(3)
  })

  it('lets the page breathe between slices when asked to', async () => {
    let breaths = 0
    await sha256Slices(new Blob([bytes(5000)]), {
      slice: 1000,
      yieldNow: async () => {
        breaths++
      },
    })
    expect(breaths).toBe(5)
  })
})

describe('sha256Hex', () => {
  it('uses Web Crypto up to the limit and slices above it, with the same answer', async () => {
    const small = bytes(100_000)
    expect(await sha256Hex(new Blob([small]))).toBe(node(small))
    const big = bytes(MAX_IN_MEMORY + 1)
    expect(await sha256Hex(new Blob([big]))).toBe(node(big)) // no Worker here: the main-thread path
  })

  it('stops when it is aborted before it starts', async () => {
    const controller = new AbortController()
    controller.abort()
    await expect(sha256Hex(new Blob([bytes(1000)]), controller.signal)).rejects.toThrow()
  })
})
