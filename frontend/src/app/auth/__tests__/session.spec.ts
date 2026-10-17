import type * as SessionApi from '../session'
import type { TokenResponse } from '@/api/models'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/*
  The refresh lock (TP "Frontend unit"; TRD §6.1). Each `import()` after resetModules is a
  separate tab: its own memory, sharing the Web Lock, the BroadcastChannel and the server.
*/

type SessionModule = typeof SessionApi

function tokenBody (n: number): TokenResponse {
  return {
    access_token: `access-${n}`,
    token_type: 'Bearer',
    expires_in: 900,
    refresh_expires_at: '2026-11-16T12:00:00Z',
    user: {
      id: '01920000-0000-7000-8000-000000000001',
      email: 'tech1@example.org',
      name: 'Devon Brown',
      phone: null,
      roles: ['technician'],
      org_id: null,
      time_zone: null,
      theme: 'system',
      status: 'active',
    },
  }
}

function json (status: number, body: unknown): Response {
  return Response.json(body, { status, headers: { 'Content-Type': 'application/json' } })
}

/** A Web Lock: one holder at a time, the rest queue (navigator.locks.request). */
function fakeLocks () {
  let tail: Promise<unknown> = Promise.resolve()
  return {
    request: (_name: string, callback: () => Promise<unknown>) => {
      const run = tail.then(() => callback())
      tail = run.catch(() => undefined)
      return run
    },
  }
}

async function tab (): Promise<SessionModule> {
  vi.resetModules()
  return import('../session')
}

let inFlight = 0
let maxInFlight = 0
let calls = 0

beforeEach(() => {
  inFlight = 0
  maxInFlight = 0
  calls = 0
  vi.stubGlobal('navigator', { ...navigator, locks: fakeLocks() })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function serverRotates (delayMs = 20) {
  vi.stubGlobal('fetch', vi.fn(async () => {
    calls += 1
    inFlight += 1
    maxInFlight = Math.max(maxInFlight, inFlight)
    await new Promise(resolve => setTimeout(resolve, delayMs))
    inFlight -= 1
    return json(200, tokenBody(calls))
  }))
}

describe('refreshSession', () => {
  it('sends one request for concurrent calls in a tab', async () => {
    serverRotates()
    const a = await tab()
    const [first, second] = await Promise.all([a.refreshSession(), a.refreshSession()])
    expect(calls).toBe(1)
    expect(first).toEqual(second)
    expect(a.accessToken()).toBe('access-1')
  })

  it('never lets two tabs use the refresh cookie at the same time', async () => {
    serverRotates()
    const a = await tab()
    const b = await tab()
    const results = await Promise.all([a.refreshSession(), b.refreshSession(), a.refreshSession()])
    expect(maxInFlight).toBe(1)
    expect(results.every(r => r.kind === 'ok')).toBe(true)
    expect(a.accessToken()).toMatch(/^access-\d$/)
    expect(b.accessToken()).toMatch(/^access-\d$/)
  })

  it('shares a new session with the other tabs', async () => {
    serverRotates(0)
    const a = await tab()
    const b = await tab()
    await a.refreshSession()
    await vi.waitFor(() => expect(b.accessToken()).toBe('access-1'))
  })

  it('ends the session with the server reason on a 401', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(401, { status: 401, code: 'unauthenticated', reason: 'account_blocked' })))
    const a = await tab()
    const ended = vi.fn()
    a.onSessionChange(ended)
    expect(await a.refreshSession()).toEqual({ kind: 'ended', reason: 'account_blocked' })
    expect(a.accessToken()).toBeNull()
    expect(ended).toHaveBeenCalledWith(null, 'account_blocked')
  })

  it('keeps a session that arrived while its own refresh failed', async () => {
    const a = await tab()
    vi.stubGlobal('fetch', vi.fn(async () => {
      // Another tab logs in while this request is out.
      a.startSession(tokenBody(7))
      return json(401, { status: 401, reason: 'no_session' })
    }))
    expect(await a.refreshSession()).toMatchObject({ kind: 'ok' })
    expect(a.accessToken()).toBe('access-7')
  })

  it('reports offline and keeps the session when the network fails', async () => {
    const a = await tab()
    a.startSession(tokenBody(3))
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))
    expect(await a.refreshSession()).toEqual({ kind: 'offline' })
    expect(a.accessToken()).toBe('access-3')
  })

  it('treats a 5xx as offline, not as the end of the session', async () => {
    const a = await tab()
    a.startSession(tokenBody(4))
    vi.stubGlobal('fetch', vi.fn(async () => json(503, { status: 503, code: 'unavailable' })))
    expect(await a.refreshSession()).toEqual({ kind: 'offline' })
    expect(a.accessToken()).toBe('access-4')
  })
})

describe('endSession', () => {
  it('logs out every tab', async () => {
    const a = await tab()
    const b = await tab()
    a.startSession(tokenBody(1))
    await vi.waitFor(() => expect(b.accessToken()).toBe('access-1'))
    a.endSession('logged_out')
    expect(a.accessToken()).toBeNull()
    await vi.waitFor(() => expect(b.accessToken()).toBeNull())
  })

  it('never stores the token', async () => {
    const a = await tab()
    a.startSession(tokenBody(1))
    expect(JSON.stringify({ ...localStorage })).not.toContain('access-1')
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('access-1')
    expect(document.cookie).not.toContain('access-1')
  })
})
