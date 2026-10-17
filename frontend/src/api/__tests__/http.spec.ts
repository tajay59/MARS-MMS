import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { startSession } from '@/app/auth/session'
import { api } from '../http'
import { ApiError, NetworkError } from '../problem'

function json (status: number, body: unknown): Response {
  return Response.json(body, { status, headers: { 'Content-Type': 'application/problem+json' } })
}

const user = {
  id: '01920000-0000-7000-8000-000000000002',
  email: 'admin@example.org',
  name: 'Andrea Campbell',
  phone: null,
  roles: ['admin'],
  org_id: null,
  time_zone: null,
  theme: 'system',
  status: 'active',
}

function auth (header: unknown): string | undefined {
  return (header as { headers?: Record<string, string> } | undefined)?.headers?.Authorization
}

beforeEach(() => {
  startSession({ access_token: 'old', token_type: 'Bearer', expires_in: 900, refresh_expires_at: '2026-11-16T00:00:00Z', user })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api', () => {
  it('sends the access token and never caches', async () => {
    const fetch = vi.fn(async () => json(200, { ok: true }))
    vi.stubGlobal('fetch', fetch)
    await api.get('/auth/me')
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/auth/me')
    expect(auth(init)).toBe('Bearer old')
    expect(init.cache).toBe('no-store')
  })

  it('refreshes once on a 401 and retries with the new token', async () => {
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/refresh')) {
        return json(200, { access_token: 'new', token_type: 'Bearer', expires_in: 900, refresh_expires_at: '2026-11-16T00:00:00Z', user })
      }
      return auth(init) === 'Bearer new' ? json(200, { id: 'x' }) : json(401, { status: 401, code: 'unauthenticated' })
    })
    vi.stubGlobal('fetch', fetch)
    await expect(api.get('/users')).resolves.toEqual({ id: 'x' })
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('leaves out empty query values', async () => {
    const fetch = vi.fn(async () => json(200, { items: [] }))
    vi.stubGlobal('fetch', fetch)
    await api.get('/users', { query: { status: 'pending', q: '', after: undefined, limit: 50 } })
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe('/api/v1/users?status=pending&limit=50')
  })

  it('turns problem details into ApiError with field errors', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(422, {
      status: 422,
      code: 'validation_failed',
      detail: 'Validation failed',
      errors: [{ loc: ['body', 'password'], msg: 'Use at least 10 characters', code: 'password_too_short' }],
    })))
    const error = await api.post('/auth/register', {}, { auth: false }).catch((error_: unknown) => error_)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).fieldErrors()).toEqual({ password: 'Use at least 10 characters' })
    expect((error as ApiError).fieldCode('password')).toBe('password_too_short')
  })

  it('does not refresh for the public auth routes', async () => {
    const fetch = vi.fn(async () => json(401, { status: 401, code: 'unauthenticated', detail: 'Email or password is incorrect' }))
    vi.stubGlobal('fetch', fetch)
    await expect(api.post('/auth/login', {}, { auth: false })).rejects.toMatchObject({ status: 401 })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('reports a failed network as NetworkError', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))
    await expect(api.get('/auth/me')).rejects.toBeInstanceOf(NetworkError)
  })
})
