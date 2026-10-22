import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { endSession, resetForTests, startSession } from '@/app/auth/session'

const made: Array<{ items: Array<{ state: string }>, dispose: ReturnType<typeof vi.fn> }> = []

vi.mock('@/app/composables/useVisitMedia', () => ({
  useVisitMedia: vi.fn(() => {
    const queue = { items: reactive<Array<{ state: string }>>([]), dispose: vi.fn() }
    made.push(queue)
    return queue
  }),
}))

const { boardQueue, disposeQueues, uploadsLabel, uploadsOnTheirWay } = await import('../uploadQueues')

const VISIT = { id: 'v1', stations: [] }

function signIn (): void {
  startSession({
    access_token: 't', expires_in: 900, refresh_expires_at: '2099-01-01T00:00:00Z',
    user: { id: 'u1', name: 'Tech', email: 'tech@example.org', roles: ['technician'] },
  } as never)
}

beforeEach(() => {
  made.length = 0
  signIn()
})

afterEach(() => {
  disposeQueues()
  resetForTests()
})

describe('uploadQueues', () => {
  it('keeps one queue for a visit and hands it out again', () => {
    expect(boardQueue(VISIT)).toBe(boardQueue(VISIT))
    expect(made).toHaveLength(1)
  })

  it('is not stopped by anything a page does: only the session ending (or disposeQueues) stops it', () => {
    const queue = boardQueue(VISIT)
    expect(queue).toBe(boardQueue({ id: 'v1', stations: [] }))
    expect(made[0]!.dispose).not.toHaveBeenCalled()
  })

  it('stops every queue and starts afresh when the session ends', () => {
    boardQueue(VISIT)
    boardQueue({ id: 'v2', stations: [] })
    endSession('logged_out')
    expect(made.map(q => q.dispose.mock.calls.length)).toEqual([1, 1])
    // The next person gets new, empty queues
    signIn()
    boardQueue(VISIT)
    expect(made).toHaveLength(3)
  })

  it('counts files on their way across visits, and says so in words', () => {
    expect(uploadsLabel.value).toBeNull()
    boardQueue(VISIT)
    boardQueue({ id: 'v2', stations: [] })
    made[0]!.items.push({ state: 'uploading' })
    expect(uploadsLabel.value).toBe('1 file uploading')
    made[1]!.items.push({ state: 'waiting' }, { state: 'failed' })
    expect(uploadsOnTheirWay.value).toEqual({ sending: 2, failed: 1 })
    expect(uploadsLabel.value).toBe('2 files uploading')
  })

  it('names failed files when nothing else is going up', () => {
    boardQueue(VISIT)
    made[0]!.items.push({ state: 'failed' })
    expect(uploadsLabel.value).toBe('1 file did not upload')
  })
})
