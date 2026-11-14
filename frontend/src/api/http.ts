/*
  The one way the app calls the API. Adds the access token, refreshes once on a 401 and retries,
  and turns problem details into ApiError. Responses are never cached here or by the service
  worker (TRD §7.6, §13.3).
*/

import { accessToken, refreshSession } from '@/app/auth/session'
import { NetworkError, toApiError } from './problem'

export const API_BASE = '/api/v1'

export interface RequestOptions {
  /** JSON body; sent with Content-Type application/json. */
  body?: unknown
  /** Query parameters; undefined and null values are left out. */
  query?: Record<string, string | number | boolean | undefined | null>
  /** false for the public auth routes (login, register, reset): no token, no refresh. */
  auth?: boolean
  signal?: AbortSignal
  /** The Accept header; JSON unless a route sends a file. */
  accept?: string
}

export async function request<T> (method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const { auth = true } = options
  let response = await send(method, path, options, auth ? accessToken() : null)
  if (response.status === 401 && auth) {
    // The token expired or was revoked (AUTH-11): one refresh, then one retry.
    const result = await refreshSession()
    if (result.kind === 'ok') {
      response = await send(method, path, options, result.session.accessToken)
    }
  }
  if (!response.ok) {
    throw await toApiError(response)
  }
  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T
  }
  return await response.json() as T
}

/**
  A file the API sends (a CSV export): the access token goes in the header, so a plain link cannot
  fetch it. Kept in memory for the moment it takes to save, never stored (TRD §7.6).
*/
export async function download (path: string, options: RequestOptions = {}): Promise<{ blob: Blob, filename: string | null }> {
  const opts = { ...options, accept: options.accept ?? 'text/csv' }
  let response = await send('GET', path, opts, accessToken())
  if (response.status === 401) {
    const result = await refreshSession()
    if (result.kind === 'ok') {
      response = await send('GET', path, opts, result.session.accessToken)
    }
  }
  if (!response.ok) {
    throw await toApiError(response)
  }
  const named = /filename="?([^";]+)"?/.exec(response.headers.get('content-disposition') ?? '')
  return { blob: await response.blob(), filename: named?.[1] ?? null }
}

async function send (method: string, path: string, options: RequestOptions, token: string | null): Promise<Response> {
  const headers: Record<string, string> = { Accept: options.accept ?? 'application/json' }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  try {
    return await fetch(url(path, options.query), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: 'same-origin',
      cache: 'no-store',
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new NetworkError(error)
  }
}

function url (path: string, query?: RequestOptions['query']): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  const qs = params.toString()
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>('GET', path, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('POST', path, { ...options, body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('PATCH', path, { ...options, body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('PUT', path, { ...options, body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>('DELETE', path, options),
}

export { ApiError, NetworkError } from './problem'
