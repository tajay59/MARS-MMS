/*
  The signed-in session, without Vue or Pinia, so the service worker’s sync can use it later
  (pwa skill §3; TRD §6.1, §7.3).

  - The access token lives in this module’s memory only: never in storage, a URL or a cache.
  - The refresh token is an httpOnly cookie on /api/v1/auth that JavaScript never sees.
  - One refresh at a time across tabs: the holder of the Web Lock `mms-auth-refresh` calls
    /refresh and shares the result on the BroadcastChannel `mms-auth`. A tab that waited for the
    lock and received a fresh session meanwhile uses it instead of refreshing again.
*/

import type { Me, TokenResponse } from '@/api/models'
import { type ApiError, toApiError } from '@/api/problem'

export const REFRESH_LOCK = 'mms-auth-refresh'
export const AUTH_CHANNEL = 'mms-auth'
const REFRESH_URL = '/api/v1/auth/refresh'
/** Refresh this long before the access token expires (it lives 15 minutes). */
const EARLY_MS = 60_000

export interface Session {
  accessToken: string
  user: Me
  /** When the access token expires (ms since epoch). */
  expiresAt: number
  /** When the refresh cookie expires: the offline PIN session's `offline_until` (TRD §6.1). */
  refreshExpiresAt: string
}

/** Why a refresh ended the session: the /login banner (AFD §5.2, §6). */
export type EndReason = 'session_expired' | 'session_revoked' | 'account_blocked' | 'no_session' | 'logged_out'

export type RefreshResult
  = | { kind: 'ok', session: Session }
    | { kind: 'ended', reason: EndReason }
    | { kind: 'offline' }

type Message
  = | { type: 'session', session: Session }
    | { type: 'ended', reason: EndReason }

type Listener = (session: Session | null, reason?: EndReason) => void

let current: Session | null = null
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
let inflight: Promise<RefreshResult> | null = null
const listeners = new Set<Listener>()

const channel: BroadcastChannel | null = typeof BroadcastChannel === 'undefined'
  ? null
  : new BroadcastChannel(AUTH_CHANNEL)

channel?.addEventListener('message', (event: MessageEvent<unknown>) => {
  const msg = event.data as Partial<Message> | null
  // Same-origin only, but check the shape before acting (pwa skill security.md §6).
  if (msg?.type === 'session' && msg.session && typeof msg.session.accessToken === 'string') {
    apply(msg.session)
  } else if (msg?.type === 'ended' && typeof msg.reason === 'string') {
    end(msg.reason, false)
  }
})

export function currentSession (): Session | null {
  return current
}

export function accessToken (): string | null {
  return current?.accessToken ?? null
}

/** Called with the new session, or with null and a reason when it ends. Returns an unsubscribe. */
export function onSessionChange (listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function fromTokenResponse (body: TokenResponse, now = Date.now()): Session {
  return {
    accessToken: body.access_token,
    user: body.user,
    expiresAt: now + body.expires_in * 1000,
    refreshExpiresAt: body.refresh_expires_at,
  }
}

/** Start a session from /login or /invitations/accept, and tell the other tabs. */
export function startSession (body: TokenResponse): Session {
  const session = fromTokenResponse(body)
  apply(session)
  channel?.postMessage({ type: 'session', session } satisfies Message)
  return session
}

/** Replace the cached profile after PATCH /me, keeping the token. */
export function updateUser (user: Me): void {
  if (current) {
    apply({ ...current, user })
  }
}

/** Forget the session here and in every tab: the user logged out. */
export function endSession (reason: EndReason): void {
  end(reason, true)
}

/**
 * Get a fresh access token from the refresh cookie. Concurrent calls in one tab share one
 * request; other tabs wait on the Web Lock. Never throws: the caller decides what an ended or
 * offline result means for the page.
 */
export function refreshSession (): Promise<RefreshResult> {
  inflight ??= underLock(refreshOnce).finally(() => {
    inflight = null
  })
  return inflight
}

async function underLock (work: (seen: number) => Promise<RefreshResult>): Promise<RefreshResult> {
  const seen = generation
  // Web Locks are in every browser AWS-MMS supports (iOS 15.4+); without them, the server's
  // 30-second grace window still makes a parallel refresh safe (TRD §6.1).
  if (typeof navigator !== 'undefined' && navigator.locks) {
    return navigator.locks.request(REFRESH_LOCK, () => work(seen))
  }
  return work(seen)
}

async function refreshOnce (seen: number): Promise<RefreshResult> {
  // Another tab refreshed while this one waited for the lock: use its session.
  if (generation !== seen && current && current.expiresAt - Date.now() > EARLY_MS) {
    return { kind: 'ok', session: current }
  }
  let response: Response
  try {
    response = await fetch(REFRESH_URL, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
  } catch {
    return { kind: 'offline' }
  }
  if (response.ok) {
    return { kind: 'ok', session: startSession(await response.json() as TokenResponse) }
  }
  const error = await toApiError(response)
  if (response.status === 401) {
    // A login in another tab arrived while this request was out: that session stands.
    if (generation !== seen && current) {
      return { kind: 'ok', session: current }
    }
    // Only this tab: the others find out on their own refresh, and a stale answer here must
    // never sign out a tab that has just logged in.
    const reason = endReason(error)
    end(reason, false)
    return { kind: 'ended', reason }
  }
  // 5xx or a gateway answer while a service restarts: keep the session, try again later.
  return { kind: 'offline' }
}

function endReason (error: ApiError): EndReason {
  switch (error.reason) {
    case 'session_revoked':
    case 'account_blocked':
    case 'no_session': {
      return error.reason
    }
    default: {
      return 'session_expired'
    }
  }
}

function apply (session: Session): void {
  current = session
  generation += 1
  schedule(session)
  for (const listener of listeners) {
    listener(session)
  }
}

function end (reason: EndReason, broadcast: boolean): void {
  current = null
  generation += 1
  clearTimeout(timer)
  if (broadcast) {
    channel?.postMessage({ type: 'ended', reason } satisfies Message)
  }
  for (const listener of listeners) {
    listener(null, reason)
  }
}

function schedule (session: Session): void {
  clearTimeout(timer)
  const wait = Math.max(session.expiresAt - Date.now() - EARLY_MS, 5000)
  timer = setTimeout(() => {
    void refreshSession()
  }, wait)
}

/** For tests: forget everything without telling anyone. */
export function resetForTests (): void {
  current = null
  generation = 0
  inflight = null
  clearTimeout(timer)
  listeners.clear()
}
