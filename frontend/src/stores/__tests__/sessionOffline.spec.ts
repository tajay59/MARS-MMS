import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { db } from '@/offline/db'
import { setPin } from '@/offline/session'

// The offline start (AUTH-12, W13-6, W13-7): no signal and a PIN waiting locks the app, the right
// PIN signs the cached profile in with no token, and signal brings the real session back.

const refresh = vi.hoisted(() => vi.fn())
const listeners = vi.hoisted(() => new Set<(session: unknown, reason?: string) => void>())

vi.mock('@/app/auth/session', () => ({
  currentSession: () => null,
  endSession: vi.fn(),
  onSessionChange: (listener: (session: unknown, reason?: string) => void) => {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  refreshSession: refresh,
  startSession: vi.fn(),
  updateUser: vi.fn(),
}))

const { useSessionStore } = await import('../session')

const DAY = 24 * 60 * 60 * 1000
const profile = {
  user_id: 'u1',
  name: 'Devon Brown',
  roles: ['technician'],
  org_id: null,
  theme: 'dark',
  offline_until: Date.now() + (30 * DAY),
}

beforeEach(async () => {
  setActivePinia(createPinia())
  refresh.mockReset()
  listeners.clear()
  await Promise.all(db.tables.map(table => table.clear()))
})

describe('starting the app', () => {
  it('asks for the PIN when the server cannot be reached and the phone has an offline session', async () => {
    await setPin(profile, '4729', { iterations: 1000 })
    refresh.mockResolvedValue({ kind: 'offline' })
    const session = useSessionStore()
    await session.bootstrap()
    expect(session.locked).toBe(true)
    expect(session.unlockState).toBe('ready')
    expect(session.lockedProfile?.name).toBe('Devon Brown')
    expect(session.user).toBeNull()
  })

  it('is signed out when the phone has no offline session', async () => {
    refresh.mockResolvedValue({ kind: 'offline' })
    const session = useSessionStore()
    await session.bootstrap()
    expect(session.locked).toBe(false)
    expect(session.user).toBeNull()
  })

  it('is signed out, not locked, when the server refused the cookie', async () => {
    await setPin(profile, '4729', { iterations: 1000 })
    refresh.mockResolvedValue({ kind: 'ended', reason: 'session_expired' })
    const session = useSessionStore()
    await session.bootstrap()
    expect(session.locked).toBe(false)
  })

  it('says offline unlock is off when the lockout or the end date applies', async () => {
    await setPin({ ...profile, offline_until: Date.now() - 1000 }, '4729', { iterations: 1000 })
    refresh.mockResolvedValue({ kind: 'offline' })
    const session = useSessionStore()
    await session.bootstrap()
    expect(session.locked).toBe(true)
    expect(session.unlockState).toBe('expired')
    expect(session.lockedProfile).toBeNull()
  })
})

describe('unlocking', () => {
  async function locked () {
    await setPin(profile, '4729', { iterations: 1000 })
    refresh.mockResolvedValue({ kind: 'offline' })
    const session = useSessionStore()
    await session.bootstrap()
    refresh.mockClear()
    return session
  }

  it('signs the cached profile in with no token, and the roles come from it', async () => {
    const session = await locked()
    session.unlockOffline(profile)
    expect(session.locked).toBe(false)
    expect(session.offline).toBe(true)
    expect(session.user?.name).toBe('Devon Brown')
    expect(session.isStaff).toBe(true)
    expect(session.isAdmin).toBe(false)
    expect(session.hasAnyRole(['technician'])).toBe(true)
  })

  it('tries to sign in for real when it unlocks and when signal comes back', async () => {
    const session = await locked()
    refresh.mockResolvedValue({ kind: 'offline' })
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
    session.unlockOffline(profile)
    await vi.waitFor(() => expect(refresh).toHaveBeenCalledTimes(1))
    await session.reconnect()
    expect(refresh).toHaveBeenCalledTimes(2)
    expect(session.offline).toBe(true)
  })

  it('leaves the offline state when a real session arrives', async () => {
    const session = await locked()
    session.unlockOffline(profile)
    const real = { accessToken: 't', expiresAt: 0, refreshExpiresAt: '2026-11-20T00:00:00Z', user: { ...profile, id: 'u1', email: 'a@b.c', roles: ['technician'], theme: 'dark' } }
    for (const listener of listeners) {
      listener(real)
    }
    expect(session.offline).toBe(false)
    expect(session.user?.email).toBe('a@b.c')
  })

  it('turns unlock off after the fifth wrong PIN and keeps the app locked', async () => {
    const session = await locked()
    session.disableUnlock()
    expect(session.locked).toBe(true)
    expect(session.unlockState).toBe('disabled')
    expect(session.lockedProfile).toBeNull()
  })

  it('does not look for signal when it is neither locked nor unlocked offline', async () => {
    refresh.mockResolvedValue({ kind: 'ended', reason: 'no_session' })
    const session = useSessionStore()
    await session.bootstrap()
    refresh.mockClear()
    await session.reconnect()
    expect(refresh).not.toHaveBeenCalled()
  })
})
